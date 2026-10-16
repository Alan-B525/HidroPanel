"""
backend/services/sync_service.py
Gestión de sincronización de telemetría y planificador programado en segundo plano.
"""

import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from ..config import DB_PATH, AUTO_SYNC_MINUTES, ONS_REPRESAS_SYNC_MINUTES
from ..database import get_db
import sync_estaciones

logger = logging.getLogger("hidropanel.sync_service")

# Estado global de sincronización automática
LAST_AUTO_SYNC_TIME: Optional[str] = None
NEXT_AUTO_SYNC_TIME: Optional[str] = None
LAST_ONS_SYNC_TIME: Optional[str] = None
NEXT_ONS_SYNC_TIME: Optional[str] = None
LAST_PNA_SYNC_TIME: Optional[str] = None
NEXT_PNA_SYNC_TIME: Optional[str] = None
_SCHEDULER_RUNNING = False
_LOCK = threading.Lock()


def get_sync_status() -> Dict[str, Any]:
    """Retorna el estado actual del sincronizador automático."""
    with _LOCK:
        return {
            "success": True,
            "last_auto_sync": LAST_AUTO_SYNC_TIME,
            "next_auto_sync": NEXT_AUTO_SYNC_TIME,
            "last_ons_sync": LAST_ONS_SYNC_TIME,
            "next_ons_sync": NEXT_ONS_SYNC_TIME,
            "last_pna_sync": LAST_PNA_SYNC_TIME,
            "next_pna_sync": NEXT_PNA_SYNC_TIME
        }


def trigger_sync(station_id: Optional[int] = None, all_stations: bool = False, frequency: Optional[int] = None) -> Dict[str, Any]:
    """
    Ejecuta sincronización bajo demanda (para una estación o para todas/por frecuencia).
    """
    if all_stations:
        with get_db() as conn:
            cursor = conn.cursor()
            if frequency:
                cursor.execute("SELECT url, codigo FROM estaciones WHERE frecuencia_minutos = ?", (frequency,))
            else:
                cursor.execute("SELECT url, codigo FROM estaciones")
            urls = [r["url"] for r in cursor.fetchall()]

        logger.info(f"Sincronizando {len(urls)} estaciones bajo demanda...")
        results = sync_estaciones.run_sync(urls, db_path=DB_PATH, workers=6)
        total_new = sum(r.get("new_records", 0) for r in results if r.get("status") == "OK")

        return {
            "success": True,
            "total_new_records": total_new,
            "results": results
        }

    elif station_id is not None:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url, codigo, nombre FROM estaciones WHERE id = ?", (station_id,))
            row = cursor.fetchone()

        if not row:
            return {"success": False, "error": "Estación no encontrada"}

        logger.info(f"Sincronizando estación {row['nombre']} ({row['codigo']}) bajo demanda...")
        res = sync_estaciones.sync_station({"url": row["url"], "code": row["codigo"]}, db_path=DB_PATH)

        return {
            "success": res.get("status") == "OK",
            "results": [res],
            "error": res.get("error")
        }

    return {"success": False, "error": "Parámetro inválido para sincronización"}


def start_background_scheduler():
    """
    Inicia el hilo programador inteligente:
    - xx:10 -> Sincronización completa (55 estaciones).
    - xx:30 -> Solo estaciones rápidas de 20 minutos (33 estaciones).
    - xx:50 -> Solo estaciones rápidas de 20 minutos (33 estaciones).
    """
    global _SCHEDULER_RUNNING, LAST_AUTO_SYNC_TIME, NEXT_AUTO_SYNC_TIME

    with _LOCK:
        if _SCHEDULER_RUNNING:
            return
        _SCHEDULER_RUNNING = True

    def scheduler_loop():
        global LAST_AUTO_SYNC_TIME, NEXT_AUTO_SYNC_TIME
        logger.info(f"Planificador de telemetría activo en minutos {AUTO_SYNC_MINUTES}.")

        while True:
            now = datetime.now()
            candidates = []
            for tm in AUTO_SYNC_MINUTES:
                target_dt = now.replace(minute=tm, second=0, microsecond=0)
                if target_dt <= now:
                    target_dt += timedelta(hours=1)
                candidates.append((target_dt, tm))

            next_sync_time, scheduled_min = min(candidates, key=lambda x: x[0])
            with _LOCK:
                NEXT_AUTO_SYNC_TIME = next_sync_time.strftime("%H:%M:%S")

            sleep_seconds = max(1, (next_sync_time - now).total_seconds())
            tipo_desc = "COMPLETA (55 estaciones)" if scheduled_min == 10 else "RÁPIDA (estaciones 20 min)"
            logger.info(f"[AUTO-SYNC] Próxima ejecución: {NEXT_AUTO_SYNC_TIME} (en {int(sleep_seconds)} s) [{tipo_desc}]")

            time.sleep(sleep_seconds)

            try:
                exec_time = datetime.now().strftime("%H:%M:%S")
                if scheduled_min == 10:
                    logger.info(f"[AUTO-SYNC] Ejecutando sincronización COMPLETA a las {exec_time}...")
                    urls = sync_estaciones.load_height_urls()
                else:
                    logger.info(f"[AUTO-SYNC] Ejecutando sincronización RÁPIDA a las {exec_time}...")
                    urls = sync_estaciones.load_height_urls(frequency=20)

                results = sync_estaciones.run_sync(urls, db_path=DB_PATH, workers=6)
                total_new = sum(r.get("new_records", 0) for r in results if r.get("status") == "OK")

                with _LOCK:
                    LAST_AUTO_SYNC_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                logger.info(f"[AUTO-SYNC] Sincronización ({len(urls)} estaciones) finalizada: +{total_new} registros nuevos.")
            except Exception as e:
                logger.error(f"[AUTO-SYNC] Error en sincronización programada: {e}")

            time.sleep(3)

    t = threading.Thread(target=scheduler_loop, daemon=True, name="AutoSyncScheduler")
    t.start()

    # Iniciar planificador automático de ONS / Represas (minutos 20 y 50 de cada hora)
    start_ons_represas_scheduler()

    # Iniciar planificador automático de Prefectura Naval Argentina (cada hora en minuto 15)
    start_prefectura_scheduler()


def start_ons_represas_scheduler():
    """
    Planificador de actualización automática de caudales ONS (Itaipú + Cuenca del Iguazú):
    - Ejecución cada 30 minutos a las XX:20 y XX:50 hs.
    """
    global LAST_ONS_SYNC_TIME, NEXT_ONS_SYNC_TIME

    def ons_loop():
        global LAST_ONS_SYNC_TIME, NEXT_ONS_SYNC_TIME
        from .represas_service import sync_ons_represas
        logger.info(f"Planificador de ONS / Represas activo en minutos {ONS_REPRESAS_SYNC_MINUTES}.")

        while True:
            now = datetime.now()
            candidates = []
            for tm in ONS_REPRESAS_SYNC_MINUTES:
                target_dt = now.replace(minute=tm, second=0, microsecond=0)
                if target_dt <= now:
                    target_dt += timedelta(hours=1)
                candidates.append(target_dt)

            next_sync = min(candidates)
            with _LOCK:
                NEXT_ONS_SYNC_TIME = next_sync.strftime("%H:%M:%S")

            sleep_sec = max(1, (next_sync - now).total_seconds())
            logger.info(f"[ONS-SYNC] Próxima actualización ONS programada: {NEXT_ONS_SYNC_TIME} (en {int(sleep_sec)} s)")

            time.sleep(sleep_sec)

            try:
                res = sync_ons_represas()
                with _LOCK:
                    LAST_ONS_SYNC_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if res.get("success"):
                    logger.info(f"[ONS-SYNC] Actualización completada exitosamente a las {LAST_ONS_SYNC_TIME}.")
            except Exception as e:
                logger.error(f"[ONS-SYNC] Error en sincronización programada de ONS: {e}")

            time.sleep(5)

    t = threading.Thread(target=ons_loop, daemon=True, name="ONSRepresasScheduler")
    t.start()


def start_prefectura_scheduler():
    """
    Planificador de actualización automática de Prefectura Naval Argentina:
    - Ejecuta periódicamente cada hora a los minutos XX:15.
    - Sincroniza las alturas oficiales de guardia y los umbrales de alerta/evacuación.
    """
    global LAST_PNA_SYNC_TIME, NEXT_PNA_SYNC_TIME

    def pna_loop():
        global LAST_PNA_SYNC_TIME, NEXT_PNA_SYNC_TIME
        from .prefectura_service import sync_prefectura_all
        logger.info("Planificador de Prefectura Naval Argentina activo (actualización horaria a los minutos XX:15).")

        # Ejecución inicial diferida suave (10 segundos tras inicio)
        time.sleep(10)
        try:
            res = sync_prefectura_all(force_history=False)
            with _LOCK:
                LAST_PNA_SYNC_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if res.get("success"):
                logger.info(f"[PNA-SYNC] Sincronización inicial completada exitosamente ({res.get('updated_stations')} estaciones).")
        except Exception as e:
            logger.error(f"[PNA-SYNC] Error en sincronización inicial de Prefectura: {e}")

        while True:
            now = datetime.now()
            # Próximo minuto 15
            target_dt = now.replace(minute=15, second=0, microsecond=0)
            if target_dt <= now:
                target_dt += timedelta(hours=1)

            with _LOCK:
                NEXT_PNA_SYNC_TIME = target_dt.strftime("%H:%M:%S")

            sleep_sec = max(1, (target_dt - now).total_seconds())
            logger.info(f"[PNA-SYNC] Próxima actualización PNA: {NEXT_PNA_SYNC_TIME} (en {int(sleep_sec)} s)")

            time.sleep(sleep_sec)

            try:
                res = sync_prefectura_all(force_history=False)
                with _LOCK:
                    LAST_PNA_SYNC_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if res.get("success"):
                    logger.info(f"[PNA-SYNC] Actualización oficial PNA completada exitosamente ({res.get('updated_stations')} estaciones).")
            except Exception as e:
                logger.error(f"[PNA-SYNC] Error en actualización programada de Prefectura: {e}")

            time.sleep(5)

    t = threading.Thread(target=pna_loop, daemon=True, name="PrefecturaScheduler")
    t.start()
