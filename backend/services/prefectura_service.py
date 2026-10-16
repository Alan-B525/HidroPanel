"""
backend/services/prefectura_service.py
Servicio integral de extracción, almacenamiento histórico y sincronización de
mediciones y umbrales oficiales desde Prefectura Naval Argentina (PNA):
https://contenidosweb.prefecturanaval.gob.ar/alturas/index.php
"""

import urllib.request
import ssl
import re
import unicodedata
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from bs4 import BeautifulSoup

from ..config import DB_PATH
from .. import thresholds

logger = logging.getLogger("hidropanel.prefectura")

PREFECTURA_URL = "https://contenidosweb.prefecturanaval.gob.ar/alturas/index.php"
PREFECTURA_HIST_URL = "https://contenidosweb.prefecturanaval.gob.ar/alturas/?page=historico&tiempo=7&id="

# Contexto SSL permisivo para conexiones institucionales
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# Mapeo de meses en español para timestamps de PNA ("15/OCT/26 - 1000")
MESES_PNA = {
    "ENE": "01", "FEB": "02", "MAR": "03", "ABR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AGO": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DIC": "12"
}

# Mapeo exhaustivo entre códigos internos de estación (AGP) y nombres de puerto en la tabla de PNA
# Solo estaciones de la Cuenca del Paraná, Iguazú, Paraguay y Río de la Plata (excluye Río Uruguay)
PNA_PORT_MAPPING = {
    # Alto Paraná e Iguazú
    "PUERTO_IGUAZU": ["IGUAZU", "PUERTO IGUAZU"],
    "PUERTO_MACUCO-PAGEWNIVEL": ["PUERTO MACUCO", "IGUAZU"],
    "PUNTA_PELIGRO-PAGEWNIVEL": ["PUNTA PELIGRO", "LIBERTAD"],
    "PUERTO_LIBERTAD": ["LIBERTAD", "PUERTO LIBERTAD"],
    "EL_DORADO": ["ELDORADO", "EL DORADO"],
    "PUERTO_LIBERTADOR": ["LIBERTADOR", "PUERTO LIBERTADOR"],
    "PUERTO_MANI": ["PUERTO MANI"],
    "SANTA_ANA": ["SANTA ANA"],
    "POSADAS": ["POSADAS"],
    "ITUZAINGO": ["ITUZAINGO"],
    "ITA_IBATE": ["ITA IBATE"],
    "ITATI": ["ITATI"],
    "PASO_DE_LA_PATRIA": ["PASO DE LA PATRIA"],

    # Eje Paraná Medio
    "CORRIENTES": ["CORRIENTES"],
    "BARRANQUERAS": ["BARRANQUERAS"],
    "EMPEDRADO": ["EMPEDRADO"],
    "BELLAVISTA": ["BELLA VISTA"],
    "LAVALLE": ["LAVALLE"],
    "GOYA": ["GOYA"],
    "RECONQUISTA": ["RECONQUISTA"],
    "ESQUINA": ["ESQUINA"],
    "LAPAZ": ["LA PAZ"],
    "SANTAELENA": ["SANTA ELENA"],
    "HERNANDARIAS": ["HERNANDARIAS"],
    "SANTAFE": ["SANTA FE"],
    "PARANA": ["PARANA"],
    "DIAMANTE_NIVEL": ["DIAMANTE"],

    # Eje Paraná Inferior / Delta
    "TIMBUES": ["TIMBUES", "SAN LORENZO"],
    "SAN_LORENZO": ["SAN LORENZO"],
    "ROSARIO": ["ROSARIO"],
    "ARROYOSECO": ["ARROYO SECO", "VILLA CONSTITUCION"],
    "VILLA_CONSTITUCION": ["VILLA CONSTITUCION"],
    "SAN_NICOLAS": ["SAN NICOLAS"],
    "RAMALLO": ["RAMALLO"],
    "VUELTAOBLIGADO": ["VUELTA DE OBLIGADO", "SAN PEDRO"],
    "SAN_PEDRO": ["SAN PEDRO"],
    "SAN_PEDRO_2": ["SAN PEDRO"],
    "BIFURCACION173": ["BIFURCACION KM 173", "SAN PEDRO"],
    "BARADERO_LEVEL": ["BARADERO"],
    "ZARATE": ["ZARATE"],
    "LASROSAS": ["LAS ROSAS", "ZARATE"],
    "ESCOBAR": ["ESCOBAR"],

    # Río de la Plata y Costa
    "BRAGA": ["BRAGA"],
    "BALIZAMITRE_LEVEL": ["BALIZA MITRE", "BUENOS AIRES"],
    "BUENOSAIRES_PRIMERESPIGON": ["BUENOS AIRES"],
    "BUENOSAIRES": ["BUENOS AIRES"],
    "LAPLATA": ["LA PLATA"],
    "MAGDALENA": ["ATALAYA", "MAGDALENA"],
    "OYARVIDESTARLINK": ["CANAL OYARVIDE", "LA PLATA"],
    "SANCLEMENTE": ["SANTA TERESITA", "SAN CLEMENTE"],
    "SPAR_236RADAR": ["SPAR 236"],

    # Río Paraguay
    "PILCOMAYO": ["PILCOMAYO"],
    "DALMACIA": ["DALMACIA", "BOUVIER"],
    "FORMOSA": ["FORMOSA"],
    "LASPALMAS": ["LAS PALMAS", "BERMEJO"]
}


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFD", name)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _parse_pna_table_timestamp(ts_str: str) -> Optional[str]:
    """Convierte cadenas como '15/OCT/26 - 1000' en '2026-10-15 10:00:00'."""
    if not ts_str:
        return None
    m = re.search(r"(\d{1,2})/([A-Z]{3})/(\d{2,4})\s*-\s*(\d{2})(\d{2})", ts_str.upper())
    if m:
        day, mon, yr, hr, mn = m.groups()
        yr_full = f"20{yr}" if len(yr) == 2 else yr
        mon_num = MESES_PNA.get(mon, "01")
        return f"{yr_full}-{mon_num}-{int(day):02d} {hr}:{mn}:00"
    return None


def fetch_prefectura_table() -> List[Dict[str, Any]]:
    """
    Descarga la tabla de alturas de ríos oficial desde Prefectura Naval Argentina.
    Filtra automáticamente cualquier estación perteneciente al Río Uruguay.
    """
    req = urllib.request.Request(
        PREFECTURA_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
    )

    with urllib.request.urlopen(req, context=SSL_CTX, timeout=12) as response:
        content = response.read().decode("utf-8", errors="ignore")

    soup = BeautifulSoup(content, "html.parser")
    table = soup.find("table")
    if not table:
        raise ValueError("No se encontró la tabla de alturas en la página de Prefectura Naval Argentina")

    rows = table.find_all("tr")
    ports_data = []

    for r in rows[1:]:
        cols = [td.get_text(strip=True) for td in r.find_all(["td", "th"])]
        if len(cols) >= 12:
            puerto = cols[0]
            rio = cols[1]

            # FILTRO ESTRICTO: Descartar puertos del Río Uruguay
            if "URUGUAY" in rio.upper():
                continue

            alt_str = cols[2].replace(",", ".")
            fecha_raw = cols[5] if len(cols) > 5 else ""
            timestamp = _parse_pna_table_timestamp(fecha_raw)
            estado_raw = cols[6] if len(cols) > 6 else ""

            # Normalizar estado de tendencia (crece / baja / estacionario)
            estado_rio = "ESTACIONARIO"
            if "CRECE" in estado_raw.upper():
                estado_rio = "CRECE"
            elif "BAJA" in estado_raw.upper():
                estado_rio = "BAJA"

            alerta_str = cols[10].replace(",", ".")
            evac_str = cols[11].replace(",", ".")

            # Lectura anterior (guardia previa, típicamente 12h o 24h atrás)
            alt_ant_str = cols[8].replace(",", ".") if len(cols) > 8 else ""
            fecha_ant_raw = cols[9] if len(cols) > 9 else ""
            timestamp_ant = _parse_pna_table_timestamp(fecha_ant_raw)

            try:
                altura = float(alt_str) if alt_str not in ("-", "", "S/E") else None
            except Exception:
                altura = None

            try:
                altura_ant = float(alt_ant_str) if alt_ant_str not in ("-", "", "S/E") else None
            except Exception:
                altura_ant = None

            try:
                alerta = float(alerta_str) if alerta_str not in ("-", "", "S/E") else None
            except Exception:
                alerta = None

            try:
                evac = float(evac_str) if evac_str not in ("-", "", "S/E") else None
            except Exception:
                evac = None

            # Extraer id de enlace histórico (?page=historico&tiempo=7&id=...)
            link = r.find("a")
            href = link.get("href", "") if link else ""
            m = re.search(r"id=(\d+)", href)
            pna_id = m.group(1) if m else None

            ports_data.append({
                "puerto": puerto,
                "rio": rio,
                "altura": altura,
                "timestamp": timestamp,
                "altura_ant": altura_ant,
                "timestamp_ant": timestamp_ant,
                "estado_rio": estado_rio,
                "alerta": alerta,
                "evacuacion": evac,
                "pna_id": pna_id
            })

    logger.info(f"Descargados {len(ports_data)} registros de puertos desde PNA (excluyendo Río Uruguay).")
    return ports_data


def fetch_pna_history_7d(pna_id: str) -> List[Tuple[str, float]]:
    """
    Descarga los registros de los últimos 7 días de un puerto específico de PNA.
    Retorna lista de (timestamp 'YYYY-MM-DD HH:MM:SS', altura).
    """
    url = f"{PREFECTURA_HIST_URL}{pna_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=12) as resp:
            soup = BeautifulSoup(resp.read(), "html.parser")
    except Exception as e:
        logger.warning(f"Error descargando historial de PNA (ID {pna_id}): {e}")
        return []

    table = soup.find("table")
    if not table:
        return []

    records = []
    for r in table.find_all("tr")[1:]:
        cols = [td.get_text(strip=True) for td in r.find_all(["td", "th"])]
        if len(cols) >= 3:
            raw_dt = cols[1]
            raw_val = cols[2].replace(" Mts", "").replace(",", ".").strip()
            # Formatos comunes: "2026-10-1406:00" o "2026-10-14 06:00"
            m = re.match(r"(\d{4}-\d{2}-\d{2})\s*(\d{2}:\d{2})", raw_dt)
            if m:
                dt_str = f"{m.group(1)} {m.group(2)}:00"
                try:
                    val = round(float(raw_val), 2)
                    records.append((dt_str, val))
                except ValueError:
                    pass
    return records


def sync_prefectura_all(force_history: bool = False) -> Dict[str, Any]:
    """
    Sincroniza todas las mediciones y umbrales oficiales de Prefectura:
    1. Descarga la tabla actual de PNA y actualiza la última medición de cada estación coincidente.
    2. Actualiza los umbrales oficiales en SQLite.
    3. Si force_history=True o hay pocas mediciones PNA, descarga los últimos 7 días de cada puerto.
    """
    try:
        pna_records = fetch_prefectura_table()
    except Exception as e:
        logger.error(f"Error en sincronización con Prefectura: {e}")
        return {"success": False, "error": f"Fallo al conectar con Prefectura: {str(e)}"}

    pna_index: Dict[str, Dict[str, Any]] = {}
    for item in pna_records:
        norm_key = _normalize_name(item["puerto"])
        pna_index[norm_key] = item

    from ..database import init_prefectura_table
    conn = sqlite3.connect(DB_PATH)
    init_prefectura_table(conn)
    c = conn.cursor()
    c.execute("SELECT id, codigo, nombre FROM estaciones")
    db_stations = c.fetchall()

    # Comprobar cuántos registros históricos tenemos actualmente
    c.execute("SELECT COUNT(*) FROM mediciones_prefectura")
    count_pna_db = c.fetchone()[0]
    need_history = force_history or (count_pna_db < 50)

    updated_count = 0
    new_measurements_count = 0
    matched_stations_for_history = []

    for st_id, codigo, nombre in db_stations:
        code_upper = codigo.upper().strip()

        # Buscar match usando PNA_PORT_MAPPING
        match_record = None
        aliases = PNA_PORT_MAPPING.get(code_upper, []) + [nombre, code_upper]
        for alias in aliases:
            norm_alias = _normalize_name(alias)
            if norm_alias in pna_index:
                match_record = pna_index[norm_alias]
                break

        if not match_record:
            norm_n = _normalize_name(nombre)
            for p_key, p_val in pna_index.items():
                if p_key == norm_n or (len(p_key) >= 5 and p_key in norm_n) or (len(norm_n) >= 5 and norm_n in p_key):
                    match_record = p_val
                    break

        if match_record:
            alerta = match_record.get("alerta")
            evac = match_record.get("evacuacion")
            altura = match_record.get("altura")
            ts = match_record.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pna_id = match_record.get("pna_id")
            puerto_pna = match_record.get("puerto")
            estado_rio = match_record.get("estado_rio")

            # 1. Insertar o actualizar la última medición oficial en mediciones_prefectura
            if altura is not None:
                c.execute("""
                    INSERT INTO mediciones_prefectura (estacion_id, puerto_pna, pna_id, timestamp, altura, estado_rio, alerta, evacuacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(estacion_id, timestamp) DO UPDATE SET
                        altura = excluded.altura,
                        estado_rio = excluded.estado_rio,
                        alerta = excluded.alerta,
                        evacuacion = excluded.evacuacion
                """, (st_id, puerto_pna, pna_id, ts, altura, estado_rio, alerta, evac))
                new_measurements_count += 1

            # 1b. Insertar medición anterior si está disponible
            alt_ant = match_record.get("altura_ant")
            ts_ant = match_record.get("timestamp_ant")
            if alt_ant is not None and ts_ant:
                c.execute("""
                    INSERT OR IGNORE INTO mediciones_prefectura (estacion_id, puerto_pna, pna_id, timestamp, altura, estado_rio, alerta, evacuacion)
                    VALUES (?, ?, ?, ?, ?, 'ANTERIOR', ?, ?)
                """, (st_id, puerto_pna, pna_id, ts_ant, alt_ant, alerta, evac))

            # 2. Actualizar umbrales oficiales de Prefectura (Alerta y Evacuación)
            if alerta is not None or evac is not None:
                thresholds.save_station_thresholds(
                    codigo=code_upper,
                    alerta=alerta,
                    evacuacion=evac,
                    db_conn=conn
                )
                updated_count += 1

            if need_history and pna_id:
                matched_stations_for_history.append((st_id, pna_id, puerto_pna, alerta, evac))

    conn.commit()

    # 3. Descarga de histórico si corresponde
    history_downloaded_points = 0
    if need_history and matched_stations_for_history:
        logger.info(f"Iniciando descarga histórica de 7 días de Prefectura para {len(matched_stations_for_history)} puertos...")
        for st_id, pna_id, puerto_pna, alerta, evac in matched_stations_for_history:
            hist_pts = fetch_pna_history_7d(pna_id)
            for h_ts, h_alt in hist_pts:
                c.execute("""
                    INSERT OR IGNORE INTO mediciones_prefectura (estacion_id, puerto_pna, pna_id, timestamp, altura, estado_rio, alerta, evacuacion)
                    VALUES (?, ?, ?, ?, ?, 'HISTORICO', ?, ?)
                """, (st_id, puerto_pna, pna_id, h_ts, h_alt, alerta, evac))
                history_downloaded_points += 1
        conn.commit()
        logger.info(f"Histórico PNA completado: {history_downloaded_points} puntos insertados.")

    conn.close()

    logger.info(f"[PNA-SYNC] Sincronización finalizada: {updated_count} estaciones actualizadas, {new_measurements_count + history_downloaded_points} registros.")
    return {
        "success": True,
        "updated_stations": updated_count,
        "latest_measurements": new_measurements_count,
        "history_points": history_downloaded_points
    }


# Alias de compatibilidad
sync_prefectura_thresholds = sync_prefectura_all
