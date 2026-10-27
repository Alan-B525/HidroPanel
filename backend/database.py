"""
backend/database.py
Gestión de conexiones y consultas optimizadas a SQLite con soporte WAL,
control estricto de concurrencia e idempotencia en persistencia histórica.
"""

import sqlite3
import os
import logging
from contextlib import contextmanager
from typing import Generator, Optional, Dict, Any, List
from datetime import datetime, timedelta

from .config import DB_PATH
import sync_estaciones

logger = logging.getLogger("hidropanel.db")


def get_connection(timeout: float = 25.0) -> sqlite3.Connection:
    """
    Crea una conexión SQLite optimizada con soporte multihilo y WAL.
    Ejecuta siempre las directivas PRAGMA obligatorias:
    PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;
    """
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.row_factory = sqlite3.Row
    # Optimizaciones y directivas de integridad requeridas
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA cache_size=-16000;")  # 16 MB cache
    return conn


@contextmanager
def get_db(timeout: float = 25.0) -> Generator[sqlite3.Connection, None, None]:
    """Context manager para conexiones seguras con autocierre."""
    conn = get_connection(timeout)
    try:
        yield conn
    finally:
        conn.close()


def init_prefectura_table(conn: sqlite3.Connection):
    """Crea la tabla de almacenamiento histórico de mediciones de Prefectura Naval Argentina."""
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mediciones_prefectura (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                estacion_id INTEGER NOT NULL,
                puerto_pna TEXT NOT NULL,
                pna_id TEXT,
                timestamp TEXT NOT NULL,
                altura REAL,
                estado_rio TEXT,
                alerta REAL,
                evacuacion REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                source TEXT DEFAULT 'PNA',
                fetched_at TEXT,
                FOREIGN KEY(estacion_id) REFERENCES estaciones(id),
                UNIQUE(estacion_id, timestamp)
            );
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pna_estacion_ts ON mediciones_prefectura(estacion_id, timestamp);")


def init_db_schema(conn: Optional[sqlite3.Connection] = None):
    """
    Inicializa de forma retrocompatible todo el esquema de la base de datos:
    1. Tabla sync_status para trazabilidad de recolectores.
    2. Tablas lecturas_hidrometricas y lecturas_represas con UNIQUE(station_id, source, measured_at).
    3. Migraciones seguras en tablas existentes mediciones y mediciones_prefectura.
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    try:
        with conn:
            # 1. Tabla sync_status
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_status (
                    source TEXT PRIMARY KEY,
                    last_attempt_at TEXT,
                    last_success_at TEXT,
                    status TEXT,
                    records_count INTEGER DEFAULT 0,
                    error_message TEXT
                );
            """)

            # 2. Tabla lecturas_hidrometricas (idempotencia y trazabilidad temporal)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lecturas_hidrometricas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    measured_at TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    altura REAL,
                    FOREIGN KEY(station_id) REFERENCES estaciones(id) ON DELETE CASCADE,
                    UNIQUE(station_id, source, measured_at)
                );
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_lecturas_hidro_unique 
                ON lecturas_hidrometricas(station_id, source, measured_at);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_lecturas_hidro_ts 
                ON lecturas_hidrometricas(station_id, measured_at);
            """)

            # 3. Tabla lecturas_represas (idempotencia y trazabilidad de caudales y cotas)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lecturas_represas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    measured_at TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    cota REAL,
                    afluente REAL,
                    defluente REAL,
                    vertido REAL,
                    FOREIGN KEY(station_id) REFERENCES estaciones(id) ON DELETE CASCADE,
                    UNIQUE(station_id, source, measured_at)
                );
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_lecturas_represas_unique 
                ON lecturas_represas(station_id, source, measured_at);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_lecturas_represas_ts 
                ON lecturas_represas(station_id, measured_at);
            """)

            # 4. Asegurar tabla de Prefectura
            init_prefectura_table(conn)

            # 5. Migraciones seguras en mediciones existentes
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(mediciones)")
            cols_med = [col[1] for col in cursor.fetchall()]
            if "source" not in cols_med:
                cursor.execute("ALTER TABLE mediciones ADD COLUMN source TEXT DEFAULT 'AGP'")
            if "fetched_at" not in cols_med:
                cursor.execute("ALTER TABLE mediciones ADD COLUMN fetched_at TEXT")

            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_mediciones_estacion_time 
                ON mediciones(estacion_id, timestamp);
            """)

            # 6. Migraciones seguras en mediciones_prefectura
            cursor.execute("PRAGMA table_info(mediciones_prefectura)")
            cols_pna = [col[1] for col in cursor.fetchall()]
            if "source" not in cols_pna:
                cursor.execute("ALTER TABLE mediciones_prefectura ADD COLUMN source TEXT DEFAULT 'PNA'")
            if "fetched_at" not in cols_pna:
                cursor.execute("ALTER TABLE mediciones_prefectura ADD COLUMN fetched_at TEXT")

            # 7. Inicializar estados base en sync_status si no existen
            sources = ["stations", "represas", "prefectura", "simepar"]
            for src in sources:
                conn.execute("""
                    INSERT OR IGNORE INTO sync_status (source, last_attempt_at, last_success_at, status, records_count, error_message)
                    VALUES (?, NULL, NULL, 'PENDING', 0, NULL)
                """, (src,))

    finally:
        if should_close:
            conn.close()


_SYNC_STATUS_CACHE: Dict[str, Dict[str, Any]] = {}


def update_sync_status(source: str, 
                       status: str, 
                       records_count: int = 0, 
                       error_message: Optional[str] = None, 
                       last_attempt_at: Optional[str] = None, 
                       last_success_at: Optional[str] = None,
                       conn: Optional[sqlite3.Connection] = None) -> None:
    """
    Actualiza el estado de sincronización para una fuente en la tabla sync_status.
    Mantiene intacto last_success_at si no se provee uno nuevo (Last Known Good State).
    """
    global _SYNC_STATUS_CACHE
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    attempt_at = last_attempt_at or now_str

    def _do_update(c: sqlite3.Connection):
        with c:
            if last_success_at is not None:
                c.execute("""
                    INSERT INTO sync_status (source, last_attempt_at, last_success_at, status, records_count, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source) DO UPDATE SET
                        last_attempt_at = excluded.last_attempt_at,
                        last_success_at = excluded.last_success_at,
                        status = excluded.status,
                        records_count = excluded.records_count,
                        error_message = excluded.error_message
                """, (source, attempt_at, last_success_at, status, records_count, error_message))
                _SYNC_STATUS_CACHE[source] = {
                    "source": source,
                    "last_attempt_at": attempt_at,
                    "last_success_at": last_success_at,
                    "status": status,
                    "records_count": records_count,
                    "error_message": error_message
                }
            else:
                c.execute("""
                    INSERT INTO sync_status (source, last_attempt_at, last_success_at, status, records_count, error_message)
                    VALUES (?, ?, NULL, ?, ?, ?)
                    ON CONFLICT(source) DO UPDATE SET
                        last_attempt_at = excluded.last_attempt_at,
                        status = excluded.status,
                        records_count = excluded.records_count,
                        error_message = excluded.error_message
                """, (source, attempt_at, status, records_count, error_message))
                # Preservar el last_success_at previo en el caché si existe
                prev_success = _SYNC_STATUS_CACHE.get(source, {}).get("last_success_at")
                _SYNC_STATUS_CACHE[source] = {
                    "source": source,
                    "last_attempt_at": attempt_at,
                    "last_success_at": prev_success,
                    "status": status,
                    "records_count": records_count,
                    "error_message": error_message
                }

    if conn is not None:
        _do_update(conn)
    else:
        with get_db() as c:
            _do_update(c)


def get_all_sync_status() -> Dict[str, Dict[str, Any]]:
    """
    Retorna el estado de todas las fuentes registradas en la tabla sync_status.
    Utiliza caché en memoria para respuesta ultra rápida (< 1 ms).
    """
    global _SYNC_STATUS_CACHE
    sources = ("stations", "represas", "prefectura", "simepar")
    if _SYNC_STATUS_CACHE and all(s in _SYNC_STATUS_CACHE for s in sources):
        return dict(_SYNC_STATUS_CACHE)

    result: Dict[str, Dict[str, Any]] = {
        "stations": {"source": "stations", "last_attempt_at": None, "last_success_at": None, "status": "PENDING", "records_count": 0, "error_message": None},
        "represas": {"source": "represas", "last_attempt_at": None, "last_success_at": None, "status": "PENDING", "records_count": 0, "error_message": None},
        "prefectura": {"source": "prefectura", "last_attempt_at": None, "last_success_at": None, "status": "PENDING", "records_count": 0, "error_message": None},
        "simepar": {"source": "simepar", "last_attempt_at": None, "last_success_at": None, "status": "PENDING", "records_count": 0, "error_message": None}
    }
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT source, last_attempt_at, last_success_at, status, records_count, error_message FROM sync_status")
            for r in cursor.fetchall():
                src = r["source"]
                result[src] = {
                    "source": src,
                    "last_attempt_at": r["last_attempt_at"],
                    "last_success_at": r["last_success_at"],
                    "status": r["status"],
                    "records_count": r["records_count"],
                    "error_message": r["error_message"]
                }
        _SYNC_STATUS_CACHE = result
    except Exception as e:
        logger.warning(f"Error consultando sync_status: {e}")
    return dict(result)


def save_hydro_reading(conn: sqlite3.Connection,
                       station_id: int,
                       source: str,
                       measured_at: str,
                       altura: Optional[float],
                       fetched_at: Optional[str] = None) -> None:
    """Inserta una lectura hidrométrica con idempotencia estricta ON CONFLICT DO UPDATE."""
    now_str = fetched_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with conn:
        conn.execute("""
            INSERT INTO lecturas_hidrometricas (station_id, source, measured_at, fetched_at, altura)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(station_id, source, measured_at) DO UPDATE SET
                altura = coalesce(excluded.altura, lecturas_hidrometricas.altura),
                fetched_at = coalesce(excluded.fetched_at, lecturas_hidrometricas.fetched_at)
            WHERE excluded.altura IS NOT NULL
        """, (station_id, source, measured_at, now_str, altura))


def save_hydro_readings_batch(conn: sqlite3.Connection, readings: List[tuple]) -> int:
    """Inserta un lote de lecturas hidrométricas con idempotencia estricta."""
    if not readings:
        return 0
    with conn:
        conn.executemany("""
            INSERT INTO lecturas_hidrometricas (station_id, source, measured_at, fetched_at, altura)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(station_id, source, measured_at) DO UPDATE SET
                altura = coalesce(excluded.altura, lecturas_hidrometricas.altura),
                fetched_at = coalesce(excluded.fetched_at, lecturas_hidrometricas.fetched_at)
            WHERE excluded.altura IS NOT NULL
        """, readings)
    return len(readings)


def save_represa_reading(conn: sqlite3.Connection,
                         station_id: int,
                         source: str,
                         measured_at: str,
                         cota: Optional[float],
                         afluente: Optional[float],
                         defluente: Optional[float],
                         vertido: Optional[float],
                         fetched_at: Optional[str] = None) -> None:
    """Inserta una lectura de represa con idempotencia estricta ON CONFLICT DO UPDATE."""
    now_str = fetched_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with conn:
        conn.execute("""
            INSERT INTO lecturas_represas (station_id, source, measured_at, fetched_at, cota, afluente, defluente, vertido)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(station_id, source, measured_at) DO UPDATE SET
                cota = coalesce(excluded.cota, lecturas_represas.cota),
                afluente = coalesce(excluded.afluente, lecturas_represas.afluente),
                defluente = coalesce(excluded.defluente, lecturas_represas.defluente),
                vertido = coalesce(excluded.vertido, lecturas_represas.vertido),
                fetched_at = coalesce(excluded.fetched_at, lecturas_represas.fetched_at)
        """, (station_id, source, measured_at, now_str, cota, afluente, defluente, vertido))


def seed_stations_catalog():
    """Inicializa la base de datos, asegura esquemas e índices y cataloga todas las estaciones."""
    sync_estaciones.init_db(DB_PATH)
    height_urls = sync_estaciones.load_height_urls()

    from . import thresholds
    with get_db() as conn:
        thresholds.init_thresholds_table(conn)
        init_db_schema(conn)
        with conn:
            for u in height_urls:
                code = sync_estaciones.get_station_code_from_url(u)
                clean_name = sync_estaciones.get_clean_name(code)
                lat, lon = sync_estaciones.get_station_coords(code)
                freq = sync_estaciones.get_station_frequency(code)
                conn.execute("""
                    INSERT INTO estaciones (codigo, nombre, url, latitud, longitud, frecuencia_minutos, estado, ultimo_timestamp, total_registros)
                    VALUES (?, ?, ?, ?, ?, ?, 'PENDIENTE', NULL, 0)
                    ON CONFLICT(codigo) DO UPDATE SET 
                        nombre = excluded.nombre,
                        latitud = coalesce(excluded.latitud, estaciones.latitud),
                        longitud = coalesce(excluded.longitud, estaciones.longitud),
                        frecuencia_minutos = coalesce(excluded.frecuencia_minutos, estaciones.frecuencia_minutos)
                """, (code, clean_name, u, lat, lon, freq))
    thresholds.load_custom_thresholds()
    logger.info("Catálogo de estaciones verificado y actualizado con esquema de alta concurrencia.")


def calculate_range_cutoff(cursor: sqlite3.Cursor, station_id: int, rango: str, table_name: str = "mediciones") -> Optional[str]:
    """
    Calcula la fecha de corte 'desde' según el rango seleccionado y la fuente/tabla específica (mediciones o mediciones_prefectura).
    Evita desfasajes temporales cuando una fuente tiene datos más recientes o desactualizados respecto a otra.
    """
    if rango == "todo":
        return None

    max_ts_str = None
    target_table = "mediciones_prefectura" if table_name == "mediciones_prefectura" else "mediciones"
    try:
        cursor.execute(f"SELECT MAX(timestamp) FROM {target_table} WHERE estacion_id = ?", (station_id,))
        row = cursor.fetchone()
        max_ts_str = row[0] if row and row[0] else None
    except Exception:
        max_ts_str = None

    # Si la tabla específica no tiene registros para esta estación, consultar la otra tabla
    if not max_ts_str:
        alt_table = "mediciones" if target_table == "mediciones_prefectura" else "mediciones_prefectura"
        try:
            cursor.execute(f"SELECT MAX(timestamp) FROM {alt_table} WHERE estacion_id = ?", (station_id,))
            row = cursor.fetchone()
            max_ts_str = row[0] if row and row[0] else None
        except Exception:
            max_ts_str = None

    # Fallback al ultimo_timestamp de la estación
    if not max_ts_str:
        cursor.execute("SELECT ultimo_timestamp FROM estaciones WHERE id = ?", (station_id,))
        row = cursor.fetchone()
        max_ts_str = row[0] if row and row[0] else None

    # Fallback al máximo global del catálogo
    if not max_ts_str:
        cursor.execute("SELECT MAX(ultimo_timestamp) FROM estaciones")
        row = cursor.fetchone()
        max_ts_str = row[0] if row and row[0] else None

    if not max_ts_str:
        return None

    try:
        max_dt = datetime.strptime(max_ts_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    if rango == "24h":
        cutoff = max_dt - timedelta(hours=24)
    elif rango == "7d":
        cutoff = max_dt - timedelta(days=7)
    elif rango == "30d":
        cutoff = max_dt - timedelta(days=30)
    else:
        cutoff = None

    return cutoff.strftime("%Y-%m-%d %H:%M:%S") if cutoff else None
