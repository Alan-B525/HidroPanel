"""
backend/routes.py
Despachador central de rutas REST API de HidroPanel.
Lecturas instantáneas en < 30 ms exclusivamente desde SQLite o memoria,
inyección de umbrales oficiales y bloque sources_status en respuestas principales.
"""

import json
import time
import logging
from urllib.parse import parse_qs, urlparse
from typing import Dict, Any, Tuple, Optional

from .services import station_service, sync_service, simepar_service, represas_service, prefectura_service
from . import thresholds

logger = logging.getLogger("hidropanel.routes")

# Caché en memoria para respuestas GET ultrarrápidas (< 2 ms)
_GET_ROUTE_CACHE: Dict[str, Tuple[float, int, str, Any]] = {}
ROUTE_CACHE_TTL = 3.0  # 3 segundos


def invalidate_routes_cache():
    """Invalida el caché en memoria tras una sincronización o actualización de umbrales."""
    global _GET_ROUTE_CACHE
    _GET_ROUTE_CACHE.clear()


def handle_get(path: str, query_params: Dict[str, list]) -> Tuple[int, str, Any]:
    """
    Despacha peticiones GET.
    Ningún endpoint GET ejecuta scrapers en vivo; responden exclusivamente
    desde SQLite o caché en memoria en < 30 ms.
    Retorna: (status_code, content_type, response_body)
    """
    can_cache = not (path == "/api/export" or path.startswith("/api/mapa_simepar/") or path.startswith("/api/simepar/"))
    cache_key = None
    if can_cache:
        cache_key = f"{path}:{sorted(query_params.items())}"
        if cache_key in _GET_ROUTE_CACHE:
            cached_time, st, ct, body = _GET_ROUTE_CACHE[cache_key]
            if time.time() - cached_time < ROUTE_CACHE_TTL:
                return st, ct, body

    def _respond(code: int, ct: str, body: Any) -> Tuple[int, str, Any]:
        if can_cache and cache_key and code == 200:
            _GET_ROUTE_CACHE[cache_key] = (time.time(), code, ct, body)
        return code, ct, body

    try:
        # 1. Catálogo de estaciones (y alias /api/stations)
        if path in ("/api/estaciones", "/api/stations"):
            estaciones = station_service.get_all_stations()
            for est in estaciones:
                thresholds.inject_thresholds(est, code_key="codigo", height_key="ultima_altura")

            data = {
                "success": True,
                "estaciones": estaciones,
                "total": len(estaciones),
                "sources_status": sync_service.get_sources_status_dict()
            }
            return _respond(200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False))

        # 2. Resumen consolidado de situación hidrológica de la cuenca
        elif path == "/api/situacion":
            data = station_service.get_situation_overview()
            for item in data.get("alertas_activas", []):
                thresholds.inject_thresholds(item, code_key="codigo", height_key="altura")
            for item in data.get("estaciones_clave", []):
                thresholds.inject_thresholds(item, code_key="codigo", height_key="ultima_altura")
            for item in data.get("estaciones_falla_reporte", []):
                thresholds.inject_thresholds(item, code_key="codigo", height_key="ultima_altura")

            data["sources_status"] = sync_service.get_sources_status_dict()
            return _respond(200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False))

        # 3. Balance hidráulico y caudales de represas (y alias /api/represas)
        elif path in ("/api/caudales", "/api/represas"):
            data = represas_service.get_hydraulic_summary()
            if isinstance(data, dict):
                for dam in data.get("centrales_lista", []):
                    thresholds.inject_thresholds(dam, code_key="codigo", height_key="cota")
                if "itaipu" in data and isinstance(data["itaipu"], dict):
                    thresholds.inject_thresholds(data["itaipu"], code_key="codigo", height_key="cota")
                if "iguazu" in data and isinstance(data["iguazu"], dict):
                    thresholds.inject_thresholds(data["iguazu"], code_key="codigo", height_key="baixo_iguazu_cota")

                data["sources_status"] = sync_service.get_sources_status_dict()
            return _respond(200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False))

        # 4. Mediciones históricas (y alias /api/history y /api/history/<station_id>)
        elif path == "/api/mediciones" or path == "/api/history" or path.startswith("/api/history/"):
            st_id_str = query_params.get("estacion_id", [None])[0] or query_params.get("station_id", [None])[0]
            if not st_id_str and path.startswith("/api/history/"):
                parts = path.strip("/").split("/")
                if len(parts) >= 3 and parts[2].isdigit():
                    st_id_str = parts[2]

            rango = query_params.get("rango", ["24h"])[0]

            if not st_id_str:
                return 400, "application/json; charset=utf-8", json.dumps({
                    "success": False, 
                    "error": "Falta parámetro estacion_id",
                    "sources_status": sync_service.get_sources_status_dict()
                })

            try:
                st_id = int(st_id_str)
            except ValueError:
                return 400, "application/json; charset=utf-8", json.dumps({
                    "success": False, 
                    "error": "ID de estación inválido",
                    "sources_status": sync_service.get_sources_status_dict()
                })

            res = station_service.get_station_measurements(st_id, rango)
            if not res:
                return 404, "application/json; charset=utf-8", json.dumps({
                    "success": False, 
                    "error": "Estación no encontrada",
                    "sources_status": sync_service.get_sources_status_dict()
                })

            if "estacion" in res and isinstance(res["estacion"], dict):
                thresholds.inject_thresholds(res["estacion"], code_key="codigo", height_key="ultima_altura")

            res["sources_status"] = sync_service.get_sources_status_dict()
            return _respond(200, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False))

        # 5. Estado de sincronización de todas las fuentes (y alias /api/status)
        elif path in ("/api/status_sync", "/api/status"):
            data = sync_service.get_sync_status()
            return _respond(200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False))

        # 6. Exportación CSV de datos históricos
        elif path == "/api/export":
            st_id_str = query_params.get("estacion_id", [None])[0] or query_params.get("station_id", [None])[0]
            rango = query_params.get("rango", ["todo"])[0]
            is_cota = query_params.get("cota", ["0"])[0] == "1"
            try:
                offset = float(query_params.get("offset", ["0.0"])[0])
            except Exception:
                offset = 0.0

            if not st_id_str:
                return 400, "text/plain; charset=utf-8", "Falta parámetro estacion_id"

            csv_res = station_service.export_station_csv(int(st_id_str), rango, is_cota, offset)
            if not csv_res:
                return 404, "text/plain; charset=utf-8", "Estación no encontrada"

            return 200, f"text/csv; charset=utf-8; filename={csv_res['filename']}", csv_res["content"]

        # 7. Mapas de lluvia SIMEPAR (y alias /api/simepar)
        elif path in ("/api/mapa_simepar", "/api/simepar"):
            data = simepar_service.get_available_maps()
            data["sources_status"] = sync_service.get_sources_status_dict()
            return _respond(200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False))

        # 8. Archivo binario de imagen del mapa SIMEPAR
        elif path.startswith("/api/mapa_simepar/") or path.startswith("/api/simepar/"):
            prefix = "/api/mapa_simepar/" if path.startswith("/api/mapa_simepar/") else "/api/simepar/"
            filename = path.replace(prefix, "").strip()
            img_bytes = simepar_service.get_map_image_bytes(filename)
            if img_bytes is None:
                return 404, "text/plain", "Mapa no encontrado"
            return 200, "image/png", img_bytes

        # 9. Consulta de umbrales
        elif path == "/api/umbrales":
            codigo = query_params.get("codigo", [None])[0]
            if codigo:
                norm = codigo.upper().strip()
                res = {
                    "success": True, 
                    "codigo": norm, 
                    "umbrales": thresholds.get_station_thresholds(norm),
                    "alert_info": thresholds.get_station_alert_info(norm),
                    "sources_status": sync_service.get_sources_status_dict()
                }
            else:
                res = {
                    "success": True, 
                    "umbrales": thresholds.get_all_thresholds_dict(),
                    "sources_status": sync_service.get_sources_status_dict()
                }
            return _respond(200, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False))

        # 10. Consulta de sincronización de Prefectura (GET sin scraper)
        elif path == "/api/sync_prefectura":
            sources = sync_service.get_sources_status_dict()
            return _respond(200, "application/json; charset=utf-8", json.dumps({
                "success": True,
                "message": "Use POST /api/sync_prefectura para sincronizar bajo demanda.",
                "prefectura": sources.get("prefectura"),
                "sources_status": sources
            }, ensure_ascii=False))

        return 404, "application/json; charset=utf-8", json.dumps({
            "success": False, 
            "error": "Ruta no encontrada",
            "sources_status": sync_service.get_sources_status_dict()
        })

    except Exception as e:
        logger.exception(f"Error procesando GET {path}: {e}")
        return 500, "application/json; charset=utf-8", json.dumps({
            "success": False, 
            "error": str(e),
            "sources_status": sync_service.get_sources_status_dict()
        })


def handle_post(path: str, body_bytes: bytes) -> Tuple[int, str, str]:
    """
    Despacha peticiones POST para acciones de sincronización y configuración de umbrales.
    Retorna: (status_code, content_type, response_body)
    """
    try:
        body_text = body_bytes.decode("utf-8") if body_bytes else "{}"
        try:
            payload = json.loads(body_text) if body_text else {}
        except Exception:
            payload = {}

        # 1. Sincronización bajo demanda (estaciones o general)
        if path == "/api/sync":
            all_st = bool(payload.get("all"))
            freq = payload.get("frequency")
            st_id = payload.get("estacion_id")

            if all_st:
                res = sync_service.sync_all_sources_parallel(is_manual=True)
            elif st_id is not None:
                res = sync_service.trigger_sync(station_id=int(st_id))
            elif freq is not None:
                res = sync_service.trigger_sync(frequency=int(freq))
            else:
                res = sync_service.sync_all_sources_parallel(is_manual=True)

            invalidate_routes_cache()
            code = 200 if (res.get("success") or res.get("cooldown")) else 400
            return code, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        # 2. Sincronización paralela de todas las fuentes
        elif path == "/api/sync_all":
            res = sync_service.sync_all_sources_parallel(is_manual=True)
            invalidate_routes_cache()
            code = 200 if (res.get("success") or res.get("cooldown")) else 400
            return code, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        # 3. Sincronización bajo demanda de represas ONS
        elif path in ("/api/sync_represas", "/api/sync_caudales"):
            res = sync_service.sync_single_source("represas", is_manual=True)
            invalidate_routes_cache()
            code = 200 if (res.get("success") or res.get("cooldown")) else 400
            return code, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        # 4. Sincronización bajo demanda de Prefectura
        elif path == "/api/sync_prefectura":
            force_h = bool(payload.get("history", False))
            res = sync_service.sync_single_source("prefectura", is_manual=True)
            invalidate_routes_cache()
            code = 200 if (res.get("success") or res.get("cooldown")) else 400
            return code, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        # 5. Sincronización bajo demanda de SIMEPAR
        elif path in ("/api/sync_mapa_simepar", "/api/sync_simepar"):
            res = sync_service.sync_single_source("simepar", is_manual=True)
            invalidate_routes_cache()
            code = 200 if (res.get("success") or res.get("cooldown")) else 400
            return code, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        # 6. Configuración de umbrales oficiales y personalizados
        elif path == "/api/umbrales":
            codigo = payload.get("codigo")
            if not codigo:
                return 400, "application/json; charset=utf-8", json.dumps({
                    "success": False, 
                    "error": "Falta parámetro codigo",
                    "sources_status": sync_service.get_sources_status_dict()
                })

            reset = payload.get("reset", False)
            if reset:
                res = thresholds.reset_station_thresholds(codigo)
            else:
                alerta = payload.get("alerta")
                evac = payload.get("evacuacion")
                alertas_activas = payload.get("alertas_activas")
                res = thresholds.save_station_thresholds(codigo, alerta=alerta, evacuacion=evac, alertas_activas=alertas_activas)

            invalidate_routes_cache()
            res["sources_status"] = sync_service.get_sources_status_dict()
            code = 200 if res.get("success") else 400
            return code, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        return 404, "application/json; charset=utf-8", json.dumps({
            "success": False, 
            "error": "Endpoint POST no encontrado",
            "sources_status": sync_service.get_sources_status_dict()
        })

    except Exception as e:
        logger.exception(f"Error procesando POST {path}: {e}")
        return 500, "application/json; charset=utf-8", json.dumps({
            "success": False, 
            "error": str(e),
            "sources_status": sync_service.get_sources_status_dict()
        })
