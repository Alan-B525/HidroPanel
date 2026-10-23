"""
backend/ina_service.py
Servicio de integración y sincronización de tramos fluviales del Instituto Nacional del Agua (INA - SIyAH).
Abarca la Cuenca del Plata completa con todos los tramos oficiales monitoreados:
- Río Iguazú (Andresito a desembocadura en Paraná)
- Río Paraná (Puerto Iguazú, Yacyretá, Corrientes, Barranqueras, Goya, La Paz, Santa Fe, Rosario hasta Delta)
- Río Paraguay (Puerto Pilcomayo, Formosa hasta Confluencia)
- Río Uruguay (El Soberbio, San Javier, Santo Tomé, Paso de los Libres, Salto Grande, Concordia hasta Estuario)
"""

import os
import json
import time
import logging
import urllib.request
from typing import Dict, Any, Optional

from .config import DATA_DIR

logger = logging.getLogger("hidropanel.ina")

INA_WFS_URL = (
    "https://alerta.ina.gob.ar/geoserver/wfs?"
    "request=GetFeature&service=WFS&version=1.0.0&"
    "typeName=public2:tramos_condicion_params&outputFormat=application/json"
)

CACHE_FILE = os.path.join(DATA_DIR, "ina_tramos_cache.json")
CACHE_TTL_SECONDS = 900  # 15 minutos

# Mapeo de ríos oficiales
RIO_NAMES = {
    "IGUAZU": "Río Iguazú",
    "PARANAMED": "Río Paraná Medio",
    "PARANAINF": "Río Paraná Inferior",
    "PARAGUAY": "Río Paraguay",
    "URUGUAY": "Río Uruguay"
}

# Espectro de color hidrológico intuitivo:
# Aguas Bajas (Estiaje) -> Lila / Violeta suave
# Aguas Medias Bajas -> Azul celeste verdoso / Cian
# Aguas Medias -> Celeste / Sky
# Aguas Medias Altas -> Azul real / Deep Sky
# Aguas Altas -> Naranja / Ámbar (hacia el rojo)
# Alerta -> Naranja rojizo vivo
# Evacuación -> Rojo intenso
STATUS_COLORS = {
    "aguas bajas": "#a855f7",        # Lila / Violeta
    "aguas medias bajas": "#06b6d4", # Cian
    "aguas medias": "#38bdf8",       # Celeste
    "aguas medias altas": "#2563eb", # Azul
    "aguas altas": "#f97316",        # Naranja vivo (hacia el rojo)
    "alerta": "#ea580c",             # Naranja rojizo
    "evacuacion": "#dc2626"          # Rojo alerta máxima
}

_MEMORY_CACHE: Optional[Dict[str, Any]] = None
_LAST_FETCH_TIME: float = 0.0


def _load_file_cache() -> Optional[Dict[str, Any]]:
    """Carga los tramos cacheados desde disco si existen."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data and "features" in data:
                    return data
        except Exception as e:
            logger.warning(f"Error leyendo caché de tramos INA en disco: {e}")
    return None


def _save_file_cache(data: Dict[str, Any]):
    """Guarda los tramos en disco para persistencia y tolerancia a fallas."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Error guardando caché de tramos INA en disco: {e}")


def _process_wfs_features(raw_features: list) -> list:
    """Procesa, desduplica y normaliza todos los tramos de la Cuenca del Plata."""
    features_by_unid = {}
    for f in raw_features:
        p = f.get("properties", {})
        unid = p.get("unid")
        if not unid:
            continue
        
        # Si un tramo aparece más de una vez (ej: Caudal y Altura), priorizamos aquel que tenga condición informada
        if unid not in features_by_unid:
            features_by_unid[unid] = f
        else:
            prev_cond = (features_by_unid[unid]["properties"].get("condicion") or "").strip().lower()
            new_cond = (p.get("condicion") or "").strip().lower()
            if not prev_cond and new_cond:
                features_by_unid[unid] = f
            elif new_cond in STATUS_COLORS and prev_cond not in STATUS_COLORS:
                features_by_unid[unid] = f

    processed_features = []
    # Ordenamiento lógico por unid
    for unid, f in sorted(features_by_unid.items(), key=lambda x: x[0]):
        p = f.get("properties", {})
        geom = p.get("geom_tramo") or f.get("geometry")
        if not geom:
            continue

        raw_cond = (p.get("condicion") or "aguas medias").strip().lower()
        color = STATUS_COLORS.get(raw_cond, "#38bdf8")

        raw_rio = (p.get("rio") or "").strip().upper()
        nombre_rio = RIO_NAMES.get(raw_rio, p.get("rio") or "Río de Cuenca del Plata")

        clean_feature = {
            "type": "Feature",
            "id": f"tramo-{unid}",
            "geometry": geom,
            "properties": {
                "unid": unid,
                "nombre": p.get("nombre") or f"Tramo {unid}",
                "rio": nombre_rio,
                "condicion": raw_cond,
                "condicion_label": raw_cond.title(),
                "color": color,
                "valor": p.get("valor"),
                "tendencia": p.get("tendencia") or "estacionario",
                "variable": p.get("variable") or "Nivel / Caudal",
                "fecha": p.get("fecha"),
                "fuente": "INA - SIyAH"
            }
        }
        processed_features.append(clean_feature)

    return processed_features


def fetch_corridor_tramos_from_ina() -> Optional[Dict[str, Any]]:
    """Descarga todos los tramos de la Cuenca del Plata desde el GeoServer WFS del INA."""
    req = urllib.request.Request(
        INA_WFS_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HidroPanel/2.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=9.0) as res:
            if res.status != 200:
                logger.warning(f"Respuesta no exitosa del GeoServer INA: {res.status}")
                return None
            data = json.loads(res.read().decode("utf-8", errors="ignore"))
            raw_features = data.get("features", [])
            all_features = _process_wfs_features(raw_features)

            if all_features:
                result = {
                    "type": "FeatureCollection",
                    "features": all_features,
                    "total": len(all_features),
                    "actualizado_en": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "fuente": "Instituto Nacional del Agua (alerta.ina.gob.ar)"
                }
                return result
    except Exception as e:
        logger.warning(f"Error consultando GeoServer INA WFS: {e}")
    return None


def get_corridor_tramos(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Retorna el FeatureCollection GeoJSON de los tramos de la Cuenca del Plata.
    Usa estrategia de caché en memoria y archivo local para tolerancia absoluta a fallas.
    """
    global _MEMORY_CACHE, _LAST_FETCH_TIME
    now = time.time()

    # 1. Caché en memoria vigente
    if not force_refresh and _MEMORY_CACHE and (now - _LAST_FETCH_TIME < CACHE_TTL_SECONDS):
        return _MEMORY_CACHE

    # 2. Intentar refrescar desde el GeoServer de INA
    fresh_data = fetch_corridor_tramos_from_ina()
    if fresh_data and fresh_data.get("features"):
        _MEMORY_CACHE = fresh_data
        _LAST_FETCH_TIME = now
        _save_file_cache(fresh_data)
        logger.info(f"Tramos de río INA actualizados exitosamente ({len(fresh_data['features'])} tramos en Cuenca del Plata).")
        return _MEMORY_CACHE

    # 3. Fallback: archivo en disco
    file_cache = _load_file_cache()
    if file_cache and file_cache.get("features"):
        _MEMORY_CACHE = file_cache
        _LAST_FETCH_TIME = now
        logger.info("Usando tramos INA desde caché de disco local.")
        return _MEMORY_CACHE

    # 4. Fallback si el caché en memoria existía previamente
    if _MEMORY_CACHE:
        return _MEMORY_CACHE

    # Si todo falla, estructura vacía estándar
    return {
        "type": "FeatureCollection",
        "features": [],
        "total": 0,
        "error": "No se pudieron obtener tramos de la cuenca hidrológica"
    }
