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
    """Obtiene la lista ordenada de fechas de mapas SIMEPAR descargados."""
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
    """Lee y devuelve los bytes de un archivo PNG de mapa SIMEPAR."""
    if not filename.endswith(".png"):
        filename += ".png"
    file_path = os.path.join(SIMEPAR_MAPS_DIR, filename)

    if not os.path.exists(file_path):
        # Fallback al mapa más reciente
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
    """Descarga de inmediato el mapa SIMEPAR actual."""
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


def start_simepar_daily_scheduler():
    """Inicia el planificador en segundo plano que descarga el mapa SIMEPAR todos los días a las 07:00 AM."""
    global _SCHEDULER_RUNNING

    with _LOCK:
        if _SCHEDULER_RUNNING:
            return
        _SCHEDULER_RUNNING = True

    def scheduler_loop():
        logger.info(f"Planificador de SIMEPAR activo: descarga programada a las {SIMEPAR_DOWNLOAD_HOUR:02d}:{SIMEPAR_DOWNLOAD_MINUTE:02d} AM.")
        while True:
            now = datetime.now()
            yesterday = (now - timedelta(days=1)).date()
            yesterday_str = yesterday.strftime("%Y-%m-%d")
            yesterday_file = os.path.join(SIMEPAR_MAPS_DIR, f"{yesterday_str}.png")

            # Si ya pasaron las 07:00 y no existe el mapa de ayer, descargarlo de inmediato
            if now.hour >= SIMEPAR_DOWNLOAD_HOUR and not os.path.exists(yesterday_file):
                try:
                    logger.info(f"[SIMEPAR] Descargando mapa pendiente de ayer ({yesterday_str})...")
                    descargar_mapa_simepar.download_simepar_map(yesterday)
                except Exception as e:
                    logger.error(f"[SIMEPAR] Error descargando mapa pendiente de ayer: {e}")

            # Calcular la próxima ejecución
            target = now.replace(hour=SIMEPAR_DOWNLOAD_HOUR, minute=SIMEPAR_DOWNLOAD_MINUTE, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)

            wait_seconds = max(5, (target - datetime.now()).total_seconds())
            logger.info(f"[SIMEPAR] Próxima descarga programada: {target.strftime('%Y-%m-%d %H:%M:%S')} (en {int(wait_seconds)} s)")
            time.sleep(wait_seconds)

            try:
                target_date = (datetime.now() - timedelta(days=1)).date()
                logger.info(f"[SIMEPAR] Ejecutando descarga programada diaria (fecha de ayer: {target_date})...")
                descargar_mapa_simepar.download_simepar_map(target_date)
            except Exception as e:
                logger.error(f"[SIMEPAR] Error en descarga programada: {e}")

            time.sleep(120)

    t = threading.Thread(target=scheduler_loop, daemon=True, name="SimeparScheduler")
    t.start()
