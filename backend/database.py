"""
backend/database.py
Gestión de conexiones y consultas optimizadas a SQLite
"""

import sqlite3
import os
import logging
from contextlib import contextmanager
from typing import Generator, Optional
from datetime import datetime, timedelta

from .config import DB_PATH
import sync_estaciones

logger = logging.getLogger("hidropanel.db")


def get_connection(timeout: float = 25.0) -> sqlite3.Connection:
    """Crea una conexión SQLite optimizada con soporte multihilo y WAL."""
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.row_factory = sqlite3.Row
    # Optimizaciones de rendimiento para lecturas concurrentes
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
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
                FOREIGN KEY(estacion_id) REFERENCES estaciones(id),
                UNIQUE(estacion_id, timestamp)
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pna_estacion_ts ON mediciones_prefectura(estacion_id, timestamp);")


def seed_stations_catalog():
    """Inicializa la base de datos y cataloga todas las estaciones con sus metadatos limpios."""
    sync_estaciones.init_db(DB_PATH)
    height_urls = sync_estaciones.load_height_urls()
    
    from . import thresholds
    with get_db() as conn:
        thresholds.init_thresholds_table(conn)
        init_prefectura_table(conn)
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
    logger.info("Catálogo de estaciones verificado y actualizado.")


def calculate_range_cutoff(cursor: sqlite3.Cursor, station_id: int, rango: str) -> Optional[str]:
    """
    Calcula la fecha de corte 'desde' según el rango seleccionado.
    Prioriza la fecha más reciente de la estación seleccionada para garantizar que siempre se muestren
    sus mediciones completas (24h, 7d, 30d) incluso si hubo desfases en la telemetría de otras estaciones.
    """
    if rango == "todo":
        return None

    # 1. Intentar con la última medición registrada para esta estación
    cursor.execute("SELECT MAX(timestamp) FROM mediciones WHERE estacion_id = ?", (station_id,))
    row = cursor.fetchone()
    max_ts_str = row[0] if row and row[0] else None

    # 2. Si no hay mediciones directas en ese query, consultar ultimo_timestamp de la estación
    if not max_ts_str:
        cursor.execute("SELECT ultimo_timestamp FROM estaciones WHERE id = ?", (station_id,))
        row = cursor.fetchone()
        max_ts_str = row[0] if row and row[0] else None

    # 3. Fallback al máximo global del catálogo
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

