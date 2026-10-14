#!/usr/bin/env python3
"""
sync_estaciones.py
Sincronizador optimizado de telemetría hidrológica (Estaciones de Altura)
Almacena ÚNICAMENTE estaciones y alturas netas válidas en SQLite local.
Soporta carga histórica inicial y actualización incremental rápida.
"""

import sys
import os
import re
import csv
import io
import sqlite3
import logging
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, unquote
import urllib.request
import ssl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("sync_estaciones")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

DEFAULT_DB = "hidrografia.db"
URL_LIST_FILE = "url_stations.txt"

STATION_CLEAN_NAMES = {
    "PUERTO_IGUAZU": "Puerto Iguazú",
    "PUERTO_MACUCO-PAGEWNIVEL": "Puerto Macuco",
    "PUNTA_PELIGRO-PAGEWNIVEL": "Punta Peligro",
    "PUERTO_LIBERTAD": "Puerto Libertad",
    "EL_DORADO": "El Dorado",
    "PUERTO_LIBERTADOR": "Puerto Libertador",
    "PUERTO_MANI": "Puerto Maní",
    "SANTA_ANA": "Santa Ana",
    "POSADAS": "Posadas",
    "ITUZAINGO": "Ituzaingó",
    "ITA_IBATE": "Itá Ibaté",
    "ITATI": "Itatí",
    "PASO_DE_LA_PATRIA": "Paso de la Patria",
    "CORRIENTES": "Corrientes",
    "BARRANQUERAS": "Barranqueras",
    "EMPEDRADO": "Empedrado",
    "BELLAVISTA": "Bella Vista",
    "LAVALLE": "Lavalle",
    "GOYA": "Goya",
    "RECONQUISTA": "Reconquista",
    "ESQUINA": "Esquina",
    "LAPAZ": "La Paz",
    "SANTAELENA": "Santa Elena",
    "HERNANDARIAS": "Hernandarias",
    "SANTAFE": "Santa Fe",
    "PARANA": "Paraná",
    "DIAMANTE_NIVEL": "Diamante",
    "TIMBUES": "Timbúes",
    "SAN_LORENZO": "San Lorenzo",
    "ROSARIO": "Rosario",
    "ARROYOSECO": "Arroyo Seco",
    "VILLA_CONSTITUCION": "Villa Constitución",
    "SAN_NICOLAS": "San Nicolás",
    "RAMALLO": "Ramallo",
    "VUELTAOBLIGADO": "Vuelta de Obligado",
    "SAN_PEDRO": "San Pedro",
    "SAN_PEDRO_2": "San Pedro 2",
    "BIFURCACION173": "Bifurcación Km 173",
    "BARADERO_LEVEL": "Baradero",
    "ZARATE": "Zárate",
    "LASROSAS": "Las Rosas",
    "ESCOBAR": "Escobar",
    "BRAGA": "Braga",
    "BALIZAMITRE_LEVEL": "Baliza Mitre",
    "BUENOSAIRES_PRIMERESPIGON": "Buenos Aires (Primer Espigón)",
    "BUENOSAIRES": "Buenos Aires",
    "LAPLATA": "La Plata",
    "MAGDALENA": "Magdalena",
    "OYARVIDESTARLINK": "Canal Oyarvide",
    "SANCLEMENTE": "San Clemente",
    "SPAR_236RADAR": "SPAR 236",
    "PILCOMAYO": "Pilcomayo",
    "DALMACIA": "Dalmacia",
    "FORMOSA": "Formosa",
    "LASPALMAS": "Las Palmas"
}

STATION_COORDINATES = {
    # Alto Paraná / Iguazú
    "PUERTO_IGUAZU": (-25.593048, -54.579062),
    "PUERTO_MACUCO-PAGEWNIVEL": (-25.642931, -54.465581),
    "PUNTA_PELIGRO-PAGEWNIVEL": (-25.684726, -54.441813),
    "PUERTO_LIBERTAD": (-25.916547, -54.620386),
    "EL_DORADO": (-26.432292, -54.696431),
    "PUERTO_LIBERTADOR": (-26.791297, -55.0243),
    "PUERTO_MANI": (-27.106389, -55.521389),
    "SANTA_ANA": (-27.335892, -55.589386),
    "POSADAS": (-27.353564, -55.913967),
    "ITUZAINGO": (-27.574167, -56.681692),
    "ITA_IBATE": (-27.422222, -57.332778),
    "ITATI": (-27.266389, -58.243889),
    "PASO_DE_LA_PATRIA": (-27.3223, -58.5824),

    # Río Paraguay
    "PILCOMAYO": (-25.373961, -57.649211),
    "DALMACIA": (-25.874454, -57.873218),
    "FORMOSA": (-26.183269, -58.162067),
    "LASPALMAS": (-27.11805, -58.642508),

    # Paraná Medio
    "CORRIENTES": (-27.4597, -58.8331),
    "BARRANQUERAS": (-27.4885, -58.9239),
    "EMPEDRADO": (-27.9589, -58.8203),
    "BELLAVISTA": (-28.504, -59.0489),
    "LAVALLE": (-29.029102, -59.189566),
    "GOYA": (-29.1432, -59.2727),
    "RECONQUISTA": (-29.2353, -59.5795),
    "ESQUINA": (-30.0167, -59.5369),
    "LAPAZ": (-30.7326, -59.6392),
    "SANTAELENA": (-30.9684, -59.8145),
    "HERNANDARIAS": (-31.23, -59.9927),
    "SANTAFE": (-31.6507, -60.7033),
    "PARANA": (-31.7208, -60.5156),
    "DIAMANTE_NIVEL": (-32.0561, -60.6439),

    # Paraná Inferior / Delta
    "TIMBUES": (-32.579909, -60.784623),
    "SAN_LORENZO": (-32.7197, -60.7259),
    "ROSARIO": (-32.9731, -60.6183),
    "ARROYOSECO": (-33.14252, -60.48559),
    "VILLA_CONSTITUCION": (-33.2264, -60.3214),
    "SAN_NICOLAS": (-33.3236, -60.2181),
    "RAMALLO": (-33.4767, -59.9975),
    "VUELTAOBLIGADO": (-33.595963, -59.792645),
    "SAN_PEDRO": (-33.674, -59.658),
    "SAN_PEDRO_2": (-33.68478, -59.64139),
    "BIFURCACION173": (-33.776111, -59.2775),
    "BARADERO_LEVEL": (-33.9367, -59.2578),
    "ZARATE": (-34.0897, -59.015),
    "LASROSAS": (-34.1836, -58.8894),
    "ESCOBAR": (-34.247018, -58.730177),
    "BRAGA": (-34.3364, -58.4850866),

    # Río de la Plata
    "BALIZAMITRE_LEVEL": (-34.413441, -58.437311),
    "BUENOSAIRES_PRIMERESPIGON": (-34.5881, -58.3595),
    "BUENOSAIRES": (-34.630444, -58.351558),
    "LAPLATA": (-34.8339, -57.8803),
    "MAGDALENA": (-34.93, -57.4617),
    "OYARVIDESTARLINK": (-35.0767, -57.128),
    "SPAR_236RADAR": (-35.09451, -55.99338),
    "SANCLEMENTE": (-36.3546, -56.7152),
}


# Estaciones con frecuencia horaria (60 minutos) que sólo publican datos al cambio de hora (:00).
# Las restantes estaciones se consideran de alta frecuencia (20 minutos / sub-horarias: 10m, 20m, 30m).
STATION_HOURLY_CODES = {
    "BARRANQUERAS", "BELLAVISTA", "CORRIENTES", "DALMACIA", "EL_DORADO",
    "EMPEDRADO", "ESQUINA", "FORMOSA", "GOYA", "HERNANDARIAS",
    "ITATI", "ITA_IBATE", "LAPAZ", "LASPALMAS", "PASO_DE_LA_PATRIA",
    "PILCOMAYO", "POSADAS", "PUERTO_LIBERTADOR", "PUERTO_MANI",
    "RECONQUISTA", "SANTAELENA", "SANTA_ANA"
}


def get_clean_name(code: str) -> str:
    """Retorna un nombre limpio y formal para la estación."""
    if code in STATION_CLEAN_NAMES:
        return STATION_CLEAN_NAMES[code]
    return code.replace('_', ' ').replace('-', ' ').title()


def get_station_coords(code: str):
    """Retorna (latitud, longitud) para la estación o (None, None)."""
    return STATION_COORDINATES.get(code, (None, None))


def get_station_frequency(code: str) -> int:
    """Retorna la frecuencia de actualización esperada en minutos (60 para horarias, 20 para el resto)."""
    return 60 if code in STATION_HOURLY_CODES else 20


def init_db(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    """Inicializa la base de datos SQLite con esquema limpio (solo estaciones y alturas)."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS estaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE NOT NULL,
                nombre TEXT,
                url TEXT UNIQUE NOT NULL,
                latitud REAL,
                longitud REAL,
                ultimo_timestamp TEXT,
                total_registros INTEGER DEFAULT 0,
                ultima_actualizacion TEXT,
                estado TEXT
            );
        """)

        # Migración automática si las columnas latitud/longitud no existían
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(estaciones)")
        cols = [c[1] for c in cursor.fetchall()]
        if "latitud" not in cols:
            cursor.execute("ALTER TABLE estaciones ADD COLUMN latitud REAL")
        if "longitud" not in cols:
            cursor.execute("ALTER TABLE estaciones ADD COLUMN longitud REAL")
        if "frecuencia_minutos" not in cols:
            cursor.execute("ALTER TABLE estaciones ADD COLUMN frecuencia_minutos INTEGER DEFAULT 20")
        if "last_modified" not in cols:
            cursor.execute("ALTER TABLE estaciones ADD COLUMN last_modified TEXT")

        # Asegurar coordenadas correctas para todas las estaciones
        for code, (lat, lon) in STATION_COORDINATES.items():
            cursor.execute(
                "UPDATE estaciones SET latitud = ?, longitud = ? WHERE codigo = ? AND (latitud IS NULL OR longitud IS NULL)",
                (lat, lon, code)
            )

        # Asegurar clasificación de frecuencias
        for code in STATION_HOURLY_CODES:
            cursor.execute("UPDATE estaciones SET frecuencia_minutos = 60 WHERE codigo = ?", (code,))
        placeholders = ','.join('?' * len(STATION_HOURLY_CODES))
        cursor.execute(
            f"UPDATE estaciones SET frecuencia_minutos = 20 WHERE frecuencia_minutos IS NULL OR (frecuencia_minutos != 20 AND codigo NOT IN ({placeholders}))",
            list(STATION_HOURLY_CODES)
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS mediciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                estacion_id INTEGER NOT NULL REFERENCES estaciones(id) ON DELETE CASCADE,
                timestamp TEXT NOT NULL,
                altura REAL NOT NULL,
                UNIQUE(estacion_id, timestamp)
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mediciones_estacion_time 
            ON mediciones(estacion_id, timestamp);
        """)
        
    return conn


def get_station_code_from_url(url: str) -> str:
    """Extrae un código limpio a partir de la URL."""
    path = urlparse(url).path
    filename = os.path.basename(path)
    clean_name = unquote(filename)
    if clean_name.lower().endswith(".dat"):
        clean_name = clean_name[:-4]
    clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', clean_name).strip('_')
    return clean_name.upper()


def load_height_urls(file_path: str = URL_LIST_FILE, frequency: int = None) -> list:
    """
    Carga los URLs descartando viento y visibilidad.
    Si se especifica frequency (20 o 60), filtra las estaciones según su frecuencia programada.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo: {file_path}")

    height_urls = []
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            u = line.strip()
            if not u:
                continue
            u_lower = u.lower()
            if "viento" in u_lower or "visibilidad" in u_lower:
                continue
            if frequency is not None:
                code = get_station_code_from_url(u)
                st_freq = get_station_frequency(code)
                if st_freq != frequency:
                    continue
            height_urls.append(u)
    return height_urls


def parse_float(val: str):
    """Convierte valor a float. Retorna None si es 'NAN', vacío o inválido."""
    if val is None:
        return None
    val = val.strip().strip('"').strip("'")
    if not val or val.upper() in ("NAN", "-INF", "INF", "NULL"):
        return None
    try:
        return float(val)
    except ValueError:
        return None


def parse_toa5_heights(content_bytes: bytes):
    """
    Parsea archivo Campbell Scientific TOA5 extrayendo únicamente timestamp y altura neta.
    Retorna (station_name, rows_generator_or_list)
    """
    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = content_bytes.decode("latin-1", errors="replace")

    lines = text.splitlines()
    if len(lines) < 2:
        raise ValueError(f"Archivo demasiado corto o inválido ({len(lines)} líneas)")

    reader = csv.reader(lines)
    header_line1 = next(reader, [])
    header_columns = next(reader, [])
    # Saltear líneas de unidades y sampling si existen
    if len(lines) > 2:
        next(reader, [])
    if len(lines) > 3:
        next(reader, [])

    station_name = header_line1[1].strip() if len(header_line1) > 1 else ""

    # Ubicar columnas de TIMESTAMP y ALTURA
    cols_lower = [c.lower() for c in header_columns]
    idx_time = 0
    idx_altura = None

    for i, col in enumerate(cols_lower):
        if "timestamp" in col:
            idx_time = i
        elif "altura" in col and idx_altura is None:
            idx_altura = i

    if idx_altura is None:
        raise ValueError(f"No se encontró ninguna columna de altura en: {header_columns}")

    # Retornar filas restantes
    return station_name, idx_time, idx_altura, reader


def download_file(url: str, if_modified_since: str = None, timeout: int = 25):
    """
    Descarga archivo vía HTTP con timeout seguro y soporte para If-Modified-Since.
    Retorna una tupla: (content_bytes, last_modified_str, not_modified_bool)
    Si el servidor devuelve 304 Not Modified, retorna (None, last_modified_str, True).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HidroSync/2.0"
    }
    if if_modified_since:
        headers["If-Modified-Since"] = if_modified_since

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout) as resp:
            content = resp.read()
            last_mod = resp.headers.get("Last-Modified")
            return content, last_mod, False
    except urllib.error.HTTPError as e:
        if e.code == 304:
            last_mod = e.headers.get("Last-Modified") or if_modified_since
            return None, last_mod, True
        raise


def sync_station(station_info: dict, db_path: str = DEFAULT_DB, force_all: bool = False) -> dict:
    """
    Sincroniza una estación a SQLite guardando únicamente timestamp y altura neta válida.
    Aprovecha la validación condicional If-Modified-Since para transferir 0 bytes si no hay cambios.
    """
    url = station_info["url"]
    code = station_info.get("code") or get_station_code_from_url(url)
    res = {
        "code": code,
        "url": url,
        "status": "PENDING",
        "new_records": 0,
        "total_records": 0,
        "last_timestamp": None,
        "latest_height": None,
        "not_modified": False,
        "error": None
    }

    conn = sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, ultimo_timestamp, total_registros, last_modified FROM estaciones WHERE url = ?", (url,))
    row = cursor.fetchone()

    station_id = None
    existing_name = None
    last_timestamp = None
    existing_total = 0
    last_modified = None

    if row:
        station_id, existing_name, last_timestamp, existing_total, last_modified = row
        existing_total = existing_total or 0

    if force_all:
        last_timestamp = None
        last_modified = None

    # Descarga condicional
    try:
        content, new_last_mod, not_modified = download_file(url, if_modified_since=last_modified)
    except Exception as e:
        res["status"] = "ERROR_DOWNLOAD"
        res["error"] = str(e)
        logger.warning(f"[{code}] Error de descarga: {e}")
        try:
            with conn:
                cursor.execute(
                    "UPDATE estaciones SET estado = ?, ultima_actualizacion = ? WHERE url = ?",
                    (f"ERROR: {e}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), url)
                )
        except Exception:
            pass
        conn.close()
        return res

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Si el servidor responde 304 Not Modified, no se transfirieron bytes
    if not_modified:
        with conn:
            cursor.execute(
                "UPDATE estaciones SET estado = 'OK (304)', ultima_actualizacion = ? WHERE id = ?",
                (now_str, station_id)
            )
        res["status"] = "OK"
        res["not_modified"] = True
        res["new_records"] = 0
        res["total_records"] = existing_total
        res["last_timestamp"] = last_timestamp

        # Obtener última altura en base de datos
        if last_timestamp:
            cursor.execute("SELECT altura FROM mediciones WHERE estacion_id = ? AND timestamp = ?", (station_id, last_timestamp))
            row_alt = cursor.fetchone()
            if row_alt:
                res["latest_height"] = row_alt[0]

        logger.info(f"[{code}] Sin modificaciones en datalogger (HTTP 304 Not Modified, 0 bytes transferidos).")
        conn.close()
        return res

    # Parseo de TOA5
    try:
        parsed_name, idx_time, idx_altura, rows_iter = parse_toa5_heights(content)
    except Exception as e:
        res["status"] = "ERROR_PARSE"
        res["error"] = str(e)
        logger.warning(f"[{code}] Error de parseo: {e}")
        conn.close()
        return res

    station_name = get_clean_name(code)
    lat, lon = get_station_coords(code)

    with conn:
        if station_id is None:
            cursor.execute("""
                INSERT INTO estaciones (codigo, nombre, url, latitud, longitud, estado, ultima_actualizacion, last_modified)
                VALUES (?, ?, ?, ?, ?, 'OK', ?, ?)
            """, (code, station_name, url, lat, lon, now_str, new_last_mod))
            station_id = cursor.lastrowid
        else:
            cursor.execute("""
                UPDATE estaciones 
                SET nombre = ?, latitud = coalesce(latitud, ?), longitud = coalesce(longitud, ?), estado = 'OK', ultima_actualizacion = ?, last_modified = coalesce(?, last_modified)
                WHERE id = ?
            """, (station_name, lat, lon, now_str, new_last_mod, station_id))

    records_to_insert = []
    latest_ts_seen = last_timestamp
    latest_alt_seen = None

    for r in rows_iter:
        if len(r) <= max(idx_time, idx_altura):
            continue
        ts_str = r[idx_time].strip().strip('"').strip("'")
        if not ts_str or len(ts_str) < 10:
            continue

        # Filtro incremental: solo registros nuevos
        if last_timestamp and ts_str <= last_timestamp:
            continue

        alt_val = parse_float(r[idx_altura])
        # Descartar mediciones sin altura neta válida ("NAN")
        if alt_val is None:
            continue

        records_to_insert.append((station_id, ts_str, alt_val))

        if latest_ts_seen is None or ts_str > latest_ts_seen:
            latest_ts_seen = ts_str
            latest_alt_seen = alt_val

    inserted_count = 0
    if records_to_insert:
        with conn:
            cursor.executemany("""
                INSERT OR IGNORE INTO mediciones (estacion_id, timestamp, altura)
                VALUES (?, ?, ?)
            """, records_to_insert)
            inserted_count = cursor.rowcount

        with conn:
            cursor.execute("SELECT COUNT(*), MAX(timestamp) FROM mediciones WHERE estacion_id = ?", (station_id,))
            total_in_db, max_db_ts = cursor.fetchone()
            cursor.execute("""
                UPDATE estaciones 
                SET ultimo_timestamp = ?, total_registros = ?, estado = 'OK', last_modified = coalesce(?, last_modified)
                WHERE id = ?
            """, (max_db_ts, total_in_db, new_last_mod, station_id))
            existing_total = total_in_db
            latest_ts_seen = max_db_ts
    else:
        with conn:
            cursor.execute("SELECT COUNT(*), MAX(timestamp) FROM mediciones WHERE estacion_id = ?", (station_id,))
            total_in_db, max_db_ts = cursor.fetchone()
            cursor.execute("""
                UPDATE estaciones 
                SET estado = 'OK', last_modified = coalesce(?, last_modified) 
                WHERE id = ?
            """, (new_last_mod, station_id))
            existing_total = total_in_db or 0
            latest_ts_seen = max_db_ts or last_timestamp

    # Obtener última altura en base de datos
    if latest_ts_seen:
        cursor.execute("SELECT altura FROM mediciones WHERE estacion_id = ? AND timestamp = ?", (station_id, latest_ts_seen))
        row_alt = cursor.fetchone()
        if row_alt:
            latest_alt_seen = row_alt[0]

    conn.close()

    res["status"] = "OK"
    res["new_records"] = inserted_count
    res["total_records"] = existing_total
    res["last_timestamp"] = latest_ts_seen
    res["latest_height"] = latest_alt_seen
    return res


def run_sync(urls: list, db_path: str = DEFAULT_DB, workers: int = 6, force_all: bool = False):
    """Sincroniza en paralelo una lista de URLs."""
    init_db(db_path)
    stations_to_process = [{"code": get_station_code_from_url(u), "url": u} for u in urls]
    
    logger.info(f"Sincronizando {len(stations_to_process)} estaciones con {workers} hilos...")
    t_start = datetime.now()

    summary = {"OK": 0, "ERROR": 0, "new_records": 0, "total_records": 0}
    results = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_station = {
            executor.submit(sync_station, st, db_path, force_all): st
            for st in stations_to_process
        }

        for future in as_completed(future_to_station):
            st = future_to_station[future]
            try:
                res = future.result()
                results.append(res)
                if res["status"] == "OK":
                    summary["OK"] += 1
                    summary["new_records"] += res["new_records"]
                    summary["total_records"] += res["total_records"]
                    alt_info = f"{res['latest_height']:.2f} m" if res['latest_height'] is not None else "NAN"
                    logger.info(
                        f"✓ [{res['code']}] +{res['new_records']:,} nuevos | Total: {res['total_records']:,} | Últ: {alt_info} ({res['last_timestamp']})"
                    )
                else:
                    summary["ERROR"] += 1
                    logger.warning(f"✗ [{res['code']}] Error: {res['error']}")
            except Exception as exc:
                summary["ERROR"] += 1
                logger.error(f"✗ [{st['code']}] Excepción: {exc}")

    elapsed = (datetime.now() - t_start).total_seconds()
    logger.info("=" * 60)
    logger.info(f"Sincronización finalizada en {elapsed:.2f} s. Éxito: {summary['OK']}/{len(stations_to_process)} | +{summary['new_records']:,} registros nuevos.")
    logger.info("=" * 60)
    return results


def print_status(db_path: str = DEFAULT_DB):
    """Muestra el estado de la base de datos con su clasificación de frecuencia."""
    if not os.path.exists(db_path):
        print(f"Base de datos '{db_path}' no encontrada.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM estaciones;")
    num_stations = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM mediciones;")
    num_measurements = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM estaciones WHERE frecuencia_minutos = 60;")
    num_hourly = cursor.fetchone()[0]
    num_20m = num_stations - num_hourly

    print("\n" + "=" * 90)
    print(f"ESTADO DE BASE DE DATOS (SOLO ALTURAS NETAS): {os.path.abspath(db_path)}")
    print(f"Estaciones: {num_stations} (Alta frec ~20m: {num_20m} | Horarias 1h: {num_hourly}) | Mediciones netas: {num_measurements:,}")
    print("=" * 90)

    cursor.execute("""
        SELECT e.codigo, e.nombre, e.frecuencia_minutos, e.total_registros, e.ultimo_timestamp, m.altura, e.estado
        FROM estaciones e
        LEFT JOIN mediciones m ON m.estacion_id = e.id AND m.timestamp = e.ultimo_timestamp
        ORDER BY e.frecuencia_minutos ASC, e.nombre ASC
    """)
    rows = cursor.fetchall()
    
    print(f"{'CÓDIGO':<26} {'NOMBRE':<25} {'FREC':<6} {'REGISTROS':<10} {'ÚLTIMA FECHA':<20} {'ALTURA (m)':<10}")
    print("-" * 105)
    for r in rows:
        cod, nom, freq, tot, u_ts, alt, est = r
        nom_disp = (nom[:22] + "..") if nom and len(nom) > 24 else (nom or "")
        tot_disp = f"{tot:,}" if tot is not None else "0"
        u_ts_disp = u_ts or "N/A"
        alt_disp = f"{alt:.2f} m" if alt is not None else "NAN"
        freq_disp = "1h" if freq == 60 else "20m"
        print(f"{cod:<26} {nom_disp:<25} {freq_disp:<6} {tot_disp:<10} {u_ts_disp:<20} {alt_disp:<10}")
    print("-" * 105)
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Sincronizador de Alturas Netas de Estaciones")
    parser.add_argument("--db", default=DEFAULT_DB, help="Ruta SQLite (default: hidrografia.db)")
    parser.add_argument("--limit", type=int, default=None, help="Limitar a N estaciones")
    parser.add_argument("--station", type=str, default=None, help="Estación específica")
    parser.add_argument("--freq", type=int, choices=[20, 60], help="Filtrar por frecuencia en minutos (20 o 60)")
    parser.add_argument("--all", action="store_true", help="Todas las estaciones de altura")
    parser.add_argument("--force-all", action="store_true", help="Reimportar histórico completo")
    parser.add_argument("--workers", type=int, default=6, help="Hilos de descarga (default: 6)")
    parser.add_argument("--status", action="store_true", help="Ver estado de la base de datos")

    args = parser.parse_args()

    if args.status:
        print_status(args.db)
        return

    urls = load_height_urls(URL_LIST_FILE, frequency=args.freq)
    if args.station:
        target = args.station.lower()
        urls = [u for u in urls if target in u.lower()]
        if not urls:
            logger.error(f"No encontrada: '{args.station}'")
            return
    elif args.limit:
        urls = urls[:args.limit]

    run_sync(urls, db_path=args.db, workers=args.workers, force_all=args.force_all)
    print_status(args.db)


if __name__ == "__main__":
    main()
