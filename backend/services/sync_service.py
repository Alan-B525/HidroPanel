"""
backend/services/sync_service.py
Motor de Sincronización Paralelo y Planificador en Segundo Plano de HidroPanel.
Sincroniza en paralelo los 4 recolectores oficiales (stations, represas, prefectura, simepar)
usando ThreadPoolExecutor(max_workers=4), registrando métricas en sync_status con
política Last Known Good State y cooldown de 60 segundos para invocaciones manuales.
"""

import threading
import time
import logging
import concurrent.futures
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from ..config import DB_PATH, AUTO_SYNC_MINUTES, ONS_REPRESAS_SYNC_MINUTES
from ..database import get_db, update_sync_status, get_all_sync_status, save_hydro_reading
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

# Control de concurrencia y cooldown para sincronizaciones manuales
_MANUAL_SYNC_LOCK = threading.Lock()
_LAST_MANUAL_SYNC_TIME: float = 0.0
MANUAL_SYNC_COOLDOWN_SECONDS: float = 60.0


def is_older_than_hours(dt_str: Optional[str], hours: float = 6.0) -> bool:
    """Evalúa si una marca temporal tiene más de 'hours' horas de antigüedad (STALE)."""
    if not dt_str:
        return True
    dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(str(dt_str)[:19], fmt)
            break
        except Exception:
            pass
    if dt is None:
        return True
    return (datetime.now() - dt).total_seconds() > (hours * 3600.0)


def get_sources_status_dict() -> Dict[str, Dict[str, Any]]:
    """Obtiene el estado consolidado de las 4 fuentes desde la base de datos SQLite."""
    return get_all_sync_status()


def get_sync_status() -> Dict[str, Any]:
    """Retorna el estado de la sincronización y el bloque sources_status con el contenido de sync_status."""
    with _LOCK:
        return {
            "success": True,
            "last_auto_sync": LAST_AUTO_SYNC_TIME,
            "next_auto_sync": NEXT_AUTO_SYNC_TIME,
            "last_ons_sync": LAST_ONS_SYNC_TIME,
            "next_ons_sync": NEXT_ONS_SYNC_TIME,
            "last_pna_sync": LAST_PNA_SYNC_TIME,
            "next_pna_sync": NEXT_PNA_SYNC_TIME,
            "sources_status": get_sources_status_dict()
        }


# =========================================================================
# WORKERS DE RECOLECCIÓN POR FUENTE (Idempotentes y Last Known Good State)
# =========================================================================

def _sync_stations_worker(frequency: Optional[int] = None) -> Dict[str, Any]:
    """Recolector de estaciones telemétricas (AGP / Altura)."""
    attempt_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[SYNC-STATIONS] Iniciando recolección de estaciones (frecuencia={frequency or 'todas'})...")
    try:
        urls = sync_estaciones.load_height_urls(frequency=frequency)
        results = sync_estaciones.run_sync(urls, db_path=DB_PATH, workers=6)
        total_new = sum(r.get("new_records", 0) for r in results if r.get("status") == "OK")
        ok_count = sum(1 for r in results if r.get("status") == "OK")

        # Persistir lecturas en lecturas_hidrometricas para trazabilidad
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT e.id, m.timestamp, m.altura 
                    FROM estaciones e 
                    JOIN mediciones m ON m.estacion_id = e.id AND m.timestamp = e.ultimo_timestamp 
                    WHERE m.altura IS NOT NULL
                """)
                for row in cursor.fetchall():
                    save_hydro_reading(conn, row["id"], "AGP", row["timestamp"], row["altura"], fetched_at=attempt_at)
        except Exception as ex_db:
            logger.warning(f"[SYNC-STATIONS] Advertencia guardando en lecturas_hidrometricas: {ex_db}")

        # Determinar frescura de datos (evaluando última medición real)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(ultimo_timestamp) FROM estaciones")
            row = cursor.fetchone()
            max_ts = row[0] if row else None

        status = "STALE" if is_older_than_hours(max_ts, 6.0) else "OK"
        update_sync_status(
            source="stations",
            status=status,
            records_count=ok_count,
            error_message=None,
            last_attempt_at=attempt_at,
            last_success_at=attempt_at
        )

        global LAST_AUTO_SYNC_TIME
        with _LOCK:
            LAST_AUTO_SYNC_TIME = attempt_at

        logger.info(f"[SYNC-STATIONS] Finalizado: {status} ({ok_count}/{len(urls)} OK, +{total_new} nuevos).")
        return {
            "status": status,
            "total_stations": len(urls),
            "ok_count": ok_count,
            "new_records": total_new,
            "last_timestamp": max_ts
        }
    except Exception as e:
        logger.error(f"[SYNC-STATIONS] Error en recolección: {e}")
        # Conservar intactos en base de datos los últimos registros válidos (Last Known Good State)
        update_sync_status(
            source="stations",
            status="ERROR",
            records_count=0,
            error_message=str(e),
            last_attempt_at=attempt_at
        )
        return {"status": "ERROR", "error": str(e)}


def _sync_represas_worker() -> Dict[str, Any]:
    """Recolector de balance hidráulico y caudales de represas (ONS / COPEL)."""
    attempt_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("[SYNC-REPRESAS] Iniciando recolección de ONS y represas...")
    try:
        from .represas_service import sync_ons_represas, build_hydraulic_summary
        res = sync_ons_represas()
        if not res.get("success"):
            raise RuntimeError(res.get("error", "Fallo al sincronizar ONS"))

        summary = build_hydraulic_summary(force_refresh=False)
        fecha_ons = summary.get("ultima_actualizacion_ons") or res.get("fecha_ons")
        status = "STALE" if is_older_than_hours(fecha_ons, 6.0) else "OK"
        centrales_count = len(summary.get("centrales_lista", []))

        update_sync_status(
            source="represas",
            status=status,
            records_count=centrales_count,
            error_message=None,
            last_attempt_at=attempt_at,
            last_success_at=attempt_at
        )

        global LAST_ONS_SYNC_TIME
        with _LOCK:
            LAST_ONS_SYNC_TIME = attempt_at

        logger.info(f"[SYNC-REPRESAS] Finalizado: {status} (Centrales: {centrales_count}, Yacyretá: {res.get('total_yacyreta')} m³/s).")
        return {
            "status": status,
            "total_yacyreta": res.get("total_yacyreta"),
            "centrales_count": centrales_count,
            "fecha_ons": fecha_ons
        }
    except Exception as e:
        logger.error(f"[SYNC-REPRESAS] Error en recolección: {e}")
        # Conservar Last Known Good State en base de datos y memoria
        update_sync_status(
            source="represas",
            status="ERROR",
            records_count=0,
            error_message=str(e),
            last_attempt_at=attempt_at
        )
        return {"status": "ERROR", "error": str(e)}


def _sync_prefectura_worker(force_history: bool = False) -> Dict[str, Any]:
    """Recolector oficial de guardias y umbrales de Prefectura Naval Argentina (PNA)."""
    attempt_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("[SYNC-PREFECTURA] Iniciando recolección oficial PNA...")
    try:
        from .prefectura_service import sync_prefectura_all
        res = sync_prefectura_all(force_history=force_history)
        if not res.get("success"):
            raise RuntimeError(res.get("error", "Fallo en sincronización con Prefectura"))

        # Determinar frescura de datos PNA
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(timestamp) FROM mediciones_prefectura")
            row = cursor.fetchone()
            max_ts = row[0] if row else None

        status = "STALE" if is_older_than_hours(max_ts, 6.0) else "OK"
        updated_st = res.get("updated_stations", 0)

        update_sync_status(
            source="prefectura",
            status=status,
            records_count=updated_st,
            error_message=None,
            last_attempt_at=attempt_at,
            last_success_at=attempt_at
        )

        global LAST_PNA_SYNC_TIME
        with _LOCK:
            LAST_PNA_SYNC_TIME = attempt_at

        logger.info(f"[SYNC-PREFECTURA] Finalizado: {status} ({updated_st} puertos oficiales actualizados).")
        return {
            "status": status,
            "updated_stations": updated_st,
            "latest_measurements": res.get("latest_measurements", 0),
            "last_timestamp": max_ts
        }
    except Exception as e:
        logger.error(f"[SYNC-PREFECTURA] Error en recolección: {e}")
        # Conservar Last Known Good State
        update_sync_status(
            source="prefectura",
            status="ERROR",
            records_count=0,
            error_message=str(e),
            last_attempt_at=attempt_at
        )
        return {"status": "ERROR", "error": str(e)}


def _sync_simepar_worker() -> Dict[str, Any]:
    """Recolector de mapas de precipitación acumulada de SIMEPAR."""
    attempt_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("[SYNC-SIMEPAR] Iniciando descarga de mapa SIMEPAR...")
    try:
        from .simepar_service import download_on_demand, get_available_maps
        res = download_on_demand()
        maps_info = get_available_maps()
        latest_map = maps_info.get("ultima_fecha")

        if not res.get("success") and not latest_map:
            raise RuntimeError(res.get("error", "Fallo al descargar mapa de SIMEPAR"))

        # Los mapas de precipitación son diarios (generados tras el cierre de jornada)
        status = "OK" if res.get("success") else "STALE"
        maps_count = len(maps_info.get("fechas", []))

        update_sync_status(
            source="simepar",
            status=status,
            records_count=maps_count,
            error_message=None if res.get("success") else res.get("error"),
            last_attempt_at=attempt_at,
            last_success_at=attempt_at if res.get("success") else None
        )

        logger.info(f"[SYNC-SIMEPAR] Finalizado: {status} (Último mapa: {latest_map}).")
        return {
            "status": status,
            "ultima_fecha": latest_map,
            "total_mapas": maps_count
        }
    except Exception as e:
        logger.error(f"[SYNC-SIMEPAR] Error en recolección: {e}")
        # Conservar mapa existente en disco
        update_sync_status(
            source="simepar",
            status="ERROR",
            records_count=0,
            error_message=str(e),
            last_attempt_at=attempt_at
        )
        return {"status": "ERROR", "error": str(e)}


# =========================================================================
# MOTOR PARALELO CON THREADPOOLEXECUTOR(max_workers=4) Y COOLDOWN DE 60s
# =========================================================================

def sync_all_sources_parallel(is_manual: bool = False) -> Dict[str, Any]:
    """
    Ejecuta los 4 recolectores oficiales (represas, prefectura, stations, simepar)
    en paralelo usando concurrent.futures.ThreadPoolExecutor(max_workers=4).
    Aplica un candado (threading.Lock) y cooldown de 60 segundos si es llamado manualmente.
    """
    global _LAST_MANUAL_SYNC_TIME

    if is_manual:
        now = time.time()
        elapsed = now - _LAST_MANUAL_SYNC_TIME
        if elapsed < MANUAL_SYNC_COOLDOWN_SECONDS:
            remaining = int(MANUAL_SYNC_COOLDOWN_SECONDS - elapsed)
            logger.warning(f"Sincronización manual bloqueada por cooldown. Restan {remaining}s.")
            return {
                "success": False,
                "cooldown": True,
                "retry_after": remaining,
                "message": f"Cooldown activo: espere {remaining} segundos antes de sincronizar nuevamente.",
                "sources_status": get_sources_status_dict()
            }

        if not _MANUAL_SYNC_LOCK.acquire(blocking=False):
            logger.warning("Sincronización manual rechazada: sincronización ya en curso.")
            return {
                "success": False,
                "locked": True,
                "message": "Una sincronización ya se encuentra en ejecución en segundo plano.",
                "sources_status": get_sources_status_dict()
            }
    else:
        if not _MANUAL_SYNC_LOCK.acquire(blocking=False):
            logger.info("Sincronización automática omitida: otra tarea está sincronizando.")
            return {"success": False, "message": "Sincronización en curso"}

    try:
        if is_manual:
            _LAST_MANUAL_SYNC_TIME = time.time()

        logger.info("=" * 65)
        logger.info(" [SYNC-PARALELO] Lanzando los 4 recolectores en paralelo (max_workers=4)...")
        logger.info("=" * 65)

        with concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="ParallelSync") as executor:
            fut_st = executor.submit(_sync_stations_worker)
            fut_rep = executor.submit(_sync_represas_worker)
            fut_pref = executor.submit(_sync_prefectura_worker)
            fut_sim = executor.submit(_sync_simepar_worker)

            results = {
                "stations": fut_st.result(),
                "represas": fut_rep.result(),
                "prefectura": fut_pref.result(),
                "simepar": fut_sim.result()
            }

        logger.info(" [SYNC-PARALELO] Completada la recolección paralela de todas las fuentes.")
        logger.info("=" * 65)

        return {
            "success": True,
            "results": results,
            "sources_status": get_sources_status_dict()
        }
    finally:
        _MANUAL_SYNC_LOCK.release()


def sync_single_source(source_name: str, is_manual: bool = True) -> Dict[str, Any]:
    """Sincroniza una fuente individual respetando lock y cooldown si es manual."""
    global _LAST_MANUAL_SYNC_TIME

    if is_manual:
        now = time.time()
        elapsed = now - _LAST_MANUAL_SYNC_TIME
        if elapsed < MANUAL_SYNC_COOLDOWN_SECONDS:
            remaining = int(MANUAL_SYNC_COOLDOWN_SECONDS - elapsed)
            return {
                "success": False,
                "cooldown": True,
                "retry_after": remaining,
                "message": f"Cooldown activo: espere {remaining} segundos antes de sincronizar nuevamente.",
                "sources_status": get_sources_status_dict()
            }

    if source_name == "stations":
        res = _sync_stations_worker()
    elif source_name == "represas":
        res = _sync_represas_worker()
    elif source_name == "prefectura":
        res = _sync_prefectura_worker()
    elif source_name == "simepar":
        res = _sync_simepar_worker()
    else:
        return {"success": False, "error": f"Fuente desconocida: {source_name}"}

    if is_manual and res.get("status") in ("OK", "STALE"):
        _LAST_MANUAL_SYNC_TIME = time.time()

    return {
        "success": res.get("status") in ("OK", "STALE"),
        "result": res,
        "sources_status": get_sources_status_dict()
    }


def trigger_sync(station_id: Optional[int] = None, all_stations: bool = False, frequency: Optional[int] = None) -> Dict[str, Any]:
    """
    Ejecuta sincronización bajo demanda (para una estación o para todas/por frecuencia).
    Si all_stations=True, invoca la sincronización paralela completa con cooldown de 60s.
    """
    if all_stations:
        return sync_all_sources_parallel(is_manual=True)

    elif frequency is not None:
        return sync_single_source("stations", is_manual=True)

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
            "error": res.get("error"),
            "sources_status": get_sources_status_dict()
        }

    return {"success": False, "error": "Parámetro inválido para sincronización"}


# =========================================================================
# PLANIFICADORES AUTOMÁTICOS EN SEGUNDO PLANO
# =========================================================================

def start_background_scheduler():
    """Inicia el planificador programado inteligente en segundo plano."""
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
                freq = None if scheduled_min == 10 else 20
                _sync_stations_worker(frequency=freq)
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
    """Planificador de actualización automática de caudales ONS."""
    global LAST_ONS_SYNC_TIME, NEXT_ONS_SYNC_TIME

    def ons_loop():
        global LAST_ONS_SYNC_TIME, NEXT_ONS_SYNC_TIME
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
                _sync_represas_worker()
            except Exception as e:
                logger.error(f"[ONS-SYNC] Error en sincronización programada de ONS: {e}")

            time.sleep(5)

    t = threading.Thread(target=ons_loop, daemon=True, name="ONSRepresasScheduler")
    t.start()


def start_prefectura_scheduler():
    """Planificador de actualización automática de Prefectura Naval Argentina."""
    global LAST_PNA_SYNC_TIME, NEXT_PNA_SYNC_TIME

    def pna_loop():
        global LAST_PNA_SYNC_TIME, NEXT_PNA_SYNC_TIME
        logger.info("Planificador de Prefectura Naval Argentina activo (minuto 15 de cada hora).")

        # Ejecución diferida suave (10 s)
        time.sleep(10)
        try:
            _sync_prefectura_worker(force_history=False)
        except Exception as e:
            logger.error(f"[PNA-SYNC] Error en sincronización inicial de Prefectura: {e}")

        while True:
            now = datetime.now()
            target_dt = now.replace(minute=15, second=0, microsecond=0)
            if target_dt <= now:
                target_dt += timedelta(hours=1)

            with _LOCK:
                NEXT_PNA_SYNC_TIME = target_dt.strftime("%H:%M:%S")

            sleep_sec = max(1, (target_dt - now).total_seconds())
            logger.info(f"[PNA-SYNC] Próxima actualización PNA: {NEXT_PNA_SYNC_TIME} (en {int(sleep_sec)} s)")

            time.sleep(sleep_sec)

            try:
                _sync_prefectura_worker(force_history=False)
            except Exception as e:
                logger.error(f"[PNA-SYNC] Error en actualización programada de Prefectura: {e}")

            time.sleep(5)

    t = threading.Thread(target=pna_loop, daemon=True, name="PrefecturaScheduler")
    t.start()
