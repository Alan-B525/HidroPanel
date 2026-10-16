"""
backend/routes.py
Despachador central de rutas REST API de HidroPanel.
"""

import json
import logging
from urllib.parse import parse_qs, urlparse
from typing import Dict, Any, Tuple, Optional

from .services import station_service, sync_service, simepar_service, represas_service, prefectura_service
from . import thresholds

logger = logging.getLogger("hidropanel.routes")


def handle_get(path: str, query_params: Dict[str, list]) -> Tuple[int, str, Any]:
    """
    Despacha peticiones GET.
    Retorna: (status_code, content_type, response_body)
    """
    try:
        if path == "/api/estaciones":
            data = {"success": True, "estaciones": station_service.get_all_stations()}
            return 200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False)

        elif path == "/api/situacion":
            data = station_service.get_situation_overview()
            return 200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False)

        elif path == "/api/caudales":
            data = represas_service.get_hydraulic_summary()
            return 200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False)

        elif path == "/api/mediciones":
            st_id_str = query_params.get("estacion_id", [None])[0]
            rango = query_params.get("rango", ["24h"])[0]

            if not st_id_str:
                return 400, "application/json; charset=utf-8", json.dumps({"success": False, "error": "Falta parámetro estacion_id"})

            try:
                st_id = int(st_id_str)
            except ValueError:
                return 400, "application/json; charset=utf-8", json.dumps({"success": False, "error": "ID de estación inválido"})

            res = station_service.get_station_measurements(st_id, rango)
            if not res:
                return 404, "application/json; charset=utf-8", json.dumps({"success": False, "error": "Estación no encontrada"})

            return 200, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        elif path == "/api/status_sync":
            data = sync_service.get_sync_status()
            return 200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False)

        elif path == "/api/export":
            st_id_str = query_params.get("estacion_id", [None])[0]
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

        elif path == "/api/mapa_simepar":
            data = simepar_service.get_available_maps()
            return 200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False)

        elif path.startswith("/api/mapa_simepar/"):
            filename = path.replace("/api/mapa_simepar/", "").strip()
            img_bytes = simepar_service.get_map_image_bytes(filename)
            if img_bytes is None:
                return 404, "text/plain", "Mapa no encontrado"
            return 200, "image/png", img_bytes

        elif path == "/api/umbrales":
            codigo = query_params.get("codigo", [None])[0]
            if codigo:
                norm = codigo.upper().strip()
                res = {"success": True, "codigo": norm, "umbrales": thresholds.get_station_thresholds(norm)}
            else:
                res = {"success": True, "umbrales": thresholds.get_all_thresholds_dict()}
            return 200, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        elif path == "/api/sync_prefectura":
            res = prefectura_service.sync_prefectura_all()
            code = 200 if res.get("success") else 500
            return code, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        return 404, "application/json; charset=utf-8", json.dumps({"success": False, "error": "Ruta no encontrada"})

    except Exception as e:
        logger.exception(f"Error procesando GET {path}: {e}")
        return 500, "application/json; charset=utf-8", json.dumps({"success": False, "error": str(e)})


def handle_post(path: str, body_bytes: bytes) -> Tuple[int, str, str]:
    """
    Despacha peticiones POST.
    Retorna: (status_code, content_type, response_body)
    """
    try:
        body_text = body_bytes.decode("utf-8") if body_bytes else "{}"
        try:
            payload = json.loads(body_text) if body_text else {}
        except Exception:
            payload = {}

        if path == "/api/sync":
            all_st = bool(payload.get("all"))
            freq = payload.get("frequency")
            st_id = payload.get("estacion_id")

            res = sync_service.trigger_sync(station_id=st_id, all_stations=all_st, frequency=freq)
            code = 200 if res.get("success") else 400
            return code, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        elif path == "/api/sync_all":
            st_res = sync_service.trigger_sync(all_stations=True)
            rep_res = represas_service.sync_ons_represas()
            pref_res = prefectura_service.sync_prefectura_all(force_history=False)
            combined = {
                "success": True,
                "estaciones": st_res,
                "represas": rep_res,
                "prefectura": pref_res
            }
            return 200, "application/json; charset=utf-8", json.dumps(combined, ensure_ascii=False)

        elif path == "/api/sync_mapa_simepar":
            res = simepar_service.download_on_demand()
            code = 200 if res.get("success") else 500
            return code, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        elif path == "/api/sync_represas":
            res = represas_service.sync_ons_represas()
            code = 200 if res.get("success") else 500
            return code, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        elif path == "/api/sync_prefectura":
            force_h = bool(payload.get("history", False))
            res = prefectura_service.sync_prefectura_all(force_history=force_h)
            code = 200 if res.get("success") else 500
            return code, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        elif path == "/api/umbrales":
            codigo = payload.get("codigo")
            if not codigo:
                return 400, "application/json; charset=utf-8", json.dumps({"success": False, "error": "Falta parámetro codigo"})

            reset = payload.get("reset", False)
            if reset:
                res = thresholds.reset_station_thresholds(codigo)
            else:
                alerta = payload.get("alerta")
                evac = payload.get("evacuacion")
                alertas_activas = payload.get("alertas_activas")
                res = thresholds.save_station_thresholds(codigo, alerta=alerta, evacuacion=evac, alertas_activas=alertas_activas)

            code = 200 if res.get("success") else 400
            return code, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False)

        return 404, "application/json; charset=utf-8", json.dumps({"success": False, "error": "Endpoint POST no encontrado"})

    except Exception as e:
        logger.exception(f"Error procesando POST {path}: {e}")
        return 500, "application/json; charset=utf-8", json.dumps({"success": False, "error": str(e)})
