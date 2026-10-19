"""
backend/services/simepar_service.py
Gestión de mapas de precipitación acumulada de SIMEPAR y su descarga programada.
"""

import os
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from ..config import SIMEPAR_MAPS_DIR, SIMEPAR_DOWNLOAD_HOUR, SIMEPAR_DOWNLOAD_MINUTE
import descargar_mapa_simepar

logger = logging.getLogger("hidropanel.simepar_service")

_SCHEDULER_RUNNING = False
_LOCK = threading.Lock()


def get_available_maps() -> Dict[str, Any]:
    os.makedirs(SIMEPAR_MAPS_DIR, exist_ok=True)
    archivos = [f for f in os.listdir(SIMEPAR_MAPS_DIR) if f.endswith(".png")]
    fechas = sorted([f[:-4] for f in archivos], reverse=True)
    ultima = fechas[0] if fechas else None
    return {
        "success": True,
        "fechas": fechas,
        "ultima_fecha": ultima,
        "url": f"/api/mapa_simepar/{ultima}.png" if ultima else None
    }


def get_map_image_bytes(filename: str) -> Optional[bytes]:
    if not filename.endswith(".png"):
        filename += ".png"
    file_path = os.path.join(SIMEPAR_MAPS_DIR, filename)

    if not os.path.exists(file_path):
        archivos = sorted([f for f in os.listdir(SIMEPAR_MAPS_DIR) if f.endswith(".png")], reverse=True)
        if archivos:
            file_path = os.path.join(SIMEPAR_MAPS_DIR, archivos[0])
        else:
            return None

    try:
        with open(file_path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error leyendo archivo de mapa {file_path}: {e}")
        return None


def download_on_demand() -> Dict[str, Any]:
    logger.info("Descargando mapa SIMEPAR bajo demanda...")
    filepath = descargar_mapa_simepar.download_simepar_map()
    if filepath:
        filename = os.path.basename(filepath)
        fecha = filename[:-4]
        return {
            "success": True,
            "fecha": fecha,
            "filename": filename,
            "url": f"/api/mapa_simepar/{filename}"
        }
    return {"success": False, "error": "Fallo al descargar mapa de SIMEPAR"}


def get_simepar_dto() -> List[Dict[str, Any]]:
    """
    Retorna la entrada DTO representativa de la red de precipitación SIMEPAR.
    """
    avail = get_available_maps()
    ultima_fecha = avail.get("ultima_fecha")
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    measured_iso = f"{ultima_fecha}T07:00:00" if ultima_fecha else now_iso

    return [{
        "station_id": "SIMEPAR_PREC_IGUAZU",
        "station_name": "SIMEPAR - Precipitación Cuenca Iguazú",
        "river": "Iguazú",
        "source": "COPEL",
        "measured_at": measured_iso,
        "fetched_at": now_iso,
        "level_m": None,
        "variation_m": None,
        "flow_in_m3s": None,
        "flow_out_m3s": None,
        "flow_turbined_m3s": None,
        "flow_spilled_m3s": None,
        "rain_mm": None,
        "trend": None,
        "raw_status": "MAPA_DISPONIBLE" if ultima_fecha else "SIN_MAPA"
    }]


def start_simepar_daily_scheduler():
    global _SCHEDULER_RUNNING

    with _LOCK:
        if _SCHEDULER_RUNNING:
            return
        _SCHEDULER_RUNNING = True

    def scheduler_loop():
        logger.info(f"Planificador de SIMEPAR activo a las {SIMEPAR_DOWNLOAD_HOUR:02d}:{SIMEPAR_DOWNLOAD_MINUTE:02d} AM.")
        while True:
            now = datetime.now()
            yesterday = (now - timedelta(days=1)).date()
            yesterday_str = yesterday.strftime("%Y-%m-%d")
            yesterday_file = os.path.join(SIMEPAR_MAPS_DIR, f"{yesterday_str}.png")

            if now.hour >= SIMEPAR_DOWNLOAD_HOUR and not os.path.exists(yesterday_file):
                try:
                    descargar_mapa_simepar.download_simepar_map(yesterday)
                except Exception as e:
                    logger.error(f"[SIMEPAR] Error descargando mapa pendiente de ayer: {e}")

            target = now.replace(hour=SIMEPAR_DOWNLOAD_HOUR, minute=SIMEPAR_DOWNLOAD_MINUTE, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)

            wait_seconds = max(5, (target - datetime.now()).total_seconds())
            time.sleep(wait_seconds)

            try:
                target_date = (datetime.now() - timedelta(days=1)).date()
                descargar_mapa_simepar.download_simepar_map(target_date)
            except Exception as e:
                logger.error(f"[SIMEPAR] Error en descarga programada: {e}")

            time.sleep(120)

    t = threading.Thread(target=scheduler_loop, daemon=True, name="SimeparScheduler")
    t.start()
