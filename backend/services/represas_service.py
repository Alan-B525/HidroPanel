"""
backend/services/represas_service.py
Integración Hidráulica Unificada para Itaipú y Presas de la Cuenca del Río Iguazú.
Fuente Oficial Primaria: ONS (Operador Nacional do Sistema Elétrico de Brasil)
Dataset S3: https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/dados_hidrologicos_ho/DADOS_HIDROLOGICOS_HO_YYYY_MM.csv

Automatización:
- Sincronización programada cada 30 minutos a las XX:20 y XX:50 hs.
- Transición dinámica de mes (detecta automáticamente el archivo mensual YYYY_MM y enlaza con el mes anterior si está en día 1-3).
- Unificación: Itaipú + Toda la cascada del Iguazú (Baixo Iguaçu, Caxias, Osório, Santiago, Segredo, Foz do Areia) en una sola fuente oficial.
- Respaldo secundario: Archivos TXT locales de Copel / Engie y estación Cataratas.
"""

import os
import sys
import csv
import io
import re
import ssl
import time
import logging
import threading
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timedelta
import sqlite3
from ..config import BASE_DIR, DATA_DIR, DB_PATH

logger = logging.getLogger("hidropanel.represas_service")

# URL Base oficial de datos abiertos de ONS en AWS S3
ONS_S3_BASE_URL = "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/dados_hidrologicos_ho"

# Contexto SSL permisivo para descargas en entornos Windows institucionales
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# Catálogo oficial de presas monitoreadas en ONS
REPRESAS_CATALOGO = {
    "PNJUPI": {
        "codigo": "PNJUPI",
        "clave": "jupia",
        "nombre": "Jupiá",
        "operador": "CTG Brasil",
        "rio": "Río Paraná (Alto Paraná)",
        "lat": -20.7758,
        "lon": -51.6267,
        "es_parana": True,
        "es_iguazu": False,
        "principal": True,
        "orden": 1
    },
    "PNPPRI": {
        "codigo": "PNPPRI",
        "clave": "porto_primavera",
        "nombre": "Porto Primavera",
        "operador": "Auren Energia",
        "rio": "Río Paraná (Alto Paraná)",
        "lat": -22.4757,
        "lon": -52.9587,
        "es_parana": True,
        "es_iguazu": False,
        "principal": True,
        "orden": 2
    },
    "PNITAI": {
        "codigo": "PNITAI",
        "clave": "itaipu",
        "nombre": "Itaipú Binacional",
        "operador": "Itaipú Binacional (Brasil/Paraguay)",
        "rio": "Río Paraná",
        "lat": -25.4081,
        "lon": -54.5887,
        "es_parana": True,
        "es_iguazu": False,
        "principal": True,
        "orden": 3
    },
    "IGGBMU": {
        "codigo": "IGGBMU",
        "clave": "areia",
        "nombre": "Foz do Areia",
        "operador": "COPEL",
        "rio": "Río Iguazú (Cabecera)",
        "lat": -26.0067,
        "lon": -51.6691,
        "es_parana": False,
        "es_iguazu": True,
        "principal": True,
        "orden": 2
    },
    "IGSEGR": {
        "codigo": "IGSEGR",
        "clave": "segredo",
        "nombre": "Segredo",
        "operador": "COPEL",
        "rio": "Río Iguazú",
        "lat": -25.7903,
        "lon": -52.1125,
        "es_parana": False,
        "es_iguazu": True,
        "principal": True,
        "orden": 3
    },
    "IGSSAN": {
        "codigo": "IGSSAN",
        "clave": "santiago",
        "nombre": "Salto Santiago",
        "operador": "ENGIE",
        "rio": "Río Iguazú",
        "lat": -25.6178,
        "lon": -52.6133,
        "es_parana": False,
        "es_iguazu": True,
        "principal": True,
        "orden": 4
    },
    "IGSOSO": {
        "codigo": "IGSOSO",
        "clave": "osorio",
        "nombre": "Salto Osório",
        "operador": "ENGIE",
        "rio": "Río Iguazú",
        "lat": -25.5376,
        "lon": -53.0090,
        "es_parana": False,
        "es_iguazu": True,
        "principal": True,
        "orden": 5
    },
    "IGSCAX": {
        "codigo": "IGSCAX",
        "clave": "caxias",
        "nombre": "Salto Caxias",
        "operador": "COPEL",
        "rio": "Río Iguazú",
        "lat": -25.5431,
        "lon": -53.4981,
        "es_parana": False,
        "es_iguazu": True,
        "principal": True,
        "orden": 6
    },
    "IGUHBI": {
        "codigo": "IGUHBI",
        "clave": "baixo_iguazu",
        "nombre": "Baixo Iguaçu",
        "operador": "COPEL / Neoenergia",
        "rio": "Río Iguazú",
        "lat": -25.5033,
        "lon": -53.6717,
        "es_parana": False,
        "es_iguazu": True,
        "principal": True,
        "orden": 7
    },
    # Centrales afluentes de tributarios del Río Iguazú (Jordão / Chopim)
    "JDJORD": {
        "codigo": "JDJORD",
        "clave": "jordao",
        "nombre": "Jordão",
        "operador": "COPEL",
        "rio": "Río Jordão (Afluente Iguazú)",
        "es_parana": False,
        "es_iguazu": True,
        "principal": False,
        "orden": 8
    },
    "IGFND": {
        "codigo": "IGFND",
        "clave": "fundao",
        "nombre": "Fundão",
        "operador": "COPEL",
        "rio": "Río Jordão (Afluente Iguazú)",
        "es_parana": False,
        "es_iguazu": True,
        "principal": False,
        "orden": 9
    },
    "IGSCL": {
        "codigo": "IGSCL",
        "clave": "santa_clara",
        "nombre": "Santa Clara",
        "operador": "COPEL",
        "rio": "Río Jordão (Afluente Iguazú)",
        "es_parana": False,
        "es_iguazu": True,
        "principal": False,
        "orden": 10
    }
}

# Caché en memoria del balance y series procesadas
_ONS_CACHE_LOCK = threading.Lock()
_ONS_SUMMARY_CACHE: Optional[Dict[str, Any]] = None
_LAST_CACHE_UPDATE: float = 0.0


def clean_num(val_str: Any) -> float:
    """Convierte números formateados ('2.800', '258,310', '8676.0', '220.38') a float."""
    if val_str is None:
        return 0.0
    if isinstance(val_str, (int, float)):
        import math
        if math.isnan(val_str):
            return 0.0
        return round(float(val_str), 2)
    s = str(val_str).strip()
    if not s or s in ('-', '--', 'N/A', 'nan', 'None'):
        return 0.0

    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):  # Formato 1.234,56
            s = s.replace('.', '').replace(',', '.')
        else:  # Formato 1,234.56
            s = s.replace(',', '')
    elif ',' in s:  # Formato 258,310 -> 258.31
        s = s.replace(',', '.')
    elif '.' in s:  # Formato 220.38 o miles de Copel
        parts = s.split('.')
        if len(parts) == 2 and len(parts[1]) == 3 and parts[0].isdigit() and int(parts[0]) > 0:
            s = parts[0] + parts[1]

    try:
        return round(float(s), 2)
    except Exception:
        return 0.0


def get_month_info(dt: datetime, ext: str = "parquet") -> Tuple[int, int, str]:
    """Retorna (año, mes, nombre_archivo_ons)."""
    return dt.year, dt.month, f"DADOS_HIDROLOGICOS_HO_{dt.year}_{dt.month:02d}.{ext}"


def get_prev_month(dt: datetime) -> datetime:
    """Retorna un datetime en el mes inmediatamente anterior."""
    first_of_this_month = dt.replace(day=1)
    return first_of_this_month - timedelta(days=1)


# =========================================================================
# DESCARGA Y GESTIÓN DE ARCHIVOS ONS EN S3 CON TRANSICIÓN DE MES
# =========================================================================

def fetch_ons_file_for_month(year: int, month: int, force: bool = False, prefer_parquet: bool = True) -> Optional[str]:
    """
    Descarga o actualiza de forma inteligente un archivo mensual de ONS en S3.
    Prioriza formato Parquet (~700 KB) con fallback transparente a CSV (~10 MB).
    Verifica HEAD para no re-descargar si no hubo cambios en S3.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    extensions = ["parquet", "csv"] if prefer_parquet else ["csv", "parquet"]

    for ext in extensions:
        fname = f"DADOS_HIDROLOGICOS_HO_{year}_{month:02d}.{ext}"
        local_path = os.path.join(DATA_DIR, fname)
        remote_url = f"{ONS_S3_BASE_URL}/{fname}"

        needs_download = False
        try:
            req_head = urllib.request.Request(remote_url, method="HEAD", headers={"User-Agent": "Mozilla/5.0 HidroPanel/2.0"})
            with urllib.request.urlopen(req_head, context=SSL_CTX, timeout=8) as resp:
                remote_len = int(resp.headers.get("Content-Length", 0))

                if os.path.exists(local_path) and not force:
                    local_len = os.path.getsize(local_path)
                    # Si el archivo remoto cambió de tamaño o tiene nuevos datos
                    if local_len != remote_len and remote_len > 1000:
                        needs_download = True
                    else:
                        needs_download = False
                else:
                    needs_download = True

        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.info(f"[ONS] Archivo {fname} no existe en S3 (404), verificando formato alternativo...")
                continue
            logger.warning(f"[ONS] Error HTTP HEAD en {fname}: {e}")
            needs_download = not os.path.exists(local_path)
        except Exception as e:
            logger.warning(f"[ONS] Error conectando a ONS S3 ({fname}): {e}")
            needs_download = not os.path.exists(local_path)

        if needs_download:
            try:
                logger.info(f"[ONS] Descargando dataset hidrológico ({fname}) desde S3...")
                dl_req = urllib.request.Request(remote_url, headers={"User-Agent": "Mozilla/5.0 HidroPanel/2.0"})
                with urllib.request.urlopen(dl_req, context=SSL_CTX, timeout=30) as resp:
                    data = resp.read()
                    if len(data) > 1000:
                        with open(local_path, "wb") as f:
                            f.write(data)
                        size_str = f"{len(data)/1024:.1f} KB" if len(data) < 1024 * 1024 else f"{len(data)/1024/1024:.2f} MB"
                        logger.info(f"[ONS] Archivo {fname} guardado exitosamente ({size_str}).")
            except Exception as e:
                logger.error(f"[ONS] Error descargando {fname}: {e}")

        if os.path.exists(local_path) and os.path.getsize(local_path) > 1000:
            return local_path

    return None


def get_active_ons_files(force_download: bool = False) -> List[str]:
    """
    Determina los archivos mensuales necesarios y los descarga si corresponde:
    - Mes actual: Siempre se consulta (priorizando Parquet).
    - Mes anterior: Se consulta en los primeros 3 días del mes para empalmar la serie histórica sin cortes.
    - Si el mes actual retorna 404 (ej. primer día antes de la publicación matutina de ONS), conmuta al mes anterior.
    """
    now = datetime.now()
    cur_year, cur_month, _ = get_month_info(now)
    prev_dt = get_prev_month(now)
    prev_year, prev_month, _ = get_month_info(prev_dt)

    files_to_read = []

    # 1. Intentar archivo del mes actual
    cur_file = fetch_ons_file_for_month(cur_year, cur_month, force=force_download)

    # 2. Si estamos en los primeros 3 días del mes o si el mes actual no existe aún, traer el mes anterior
    if now.day <= 3 or cur_file is None:
        prev_file = fetch_ons_file_for_month(prev_year, prev_month, force=False)
        if prev_file:
            files_to_read.append(prev_file)

    if cur_file:
        files_to_read.append(cur_file)

    return files_to_read


# =========================================================================
# PARSEO ROBUSTO DEL DATASET ONS (PARQUET / CSV)
# =========================================================================

def parse_ons_data(files: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Lee uno o dos archivos mensuales de ONS (formato Parquet o CSV),
    filtra las presas de interés y construye la serie cronológica ordenada para cada una.
    """
    parsed_dams: Dict[str, Dict[str, Any]] = {}

    for code, meta in REPRESAS_CATALOGO.items():
        parsed_dams[code] = {
            "codigo": code,
            "clave": meta["clave"],
            "nombre": meta["nombre"],
            "operador": meta["operador"],
            "rio": meta["rio"],
            "es_parana": meta["es_parana"],
            "es_iguazu": meta["es_iguazu"],
            "principal": meta["principal"],
            "orden": meta["orden"],
            "records": {}  # din_instante -> row_dict
        }

    for path in files:
        if not os.path.exists(path):
            continue

        # 1. Procesamiento optimizado de archivo Parquet (~700 KB con pushdown filters)
        if path.lower().endswith(".parquet"):
            try:
                import pyarrow.parquet as pq
                cols = [
                    "id_reservatorio", "din_instante", "val_vazaoafluente",
                    "val_vazaoturbinada", "val_vazaovertida", "val_vazaodefluente",
                    "val_nivelmontante", "val_niveljusante", "val_volumeutil"
                ]
                target_ids = list(REPRESAS_CATALOGO.keys())
                table = pq.read_table(path, columns=cols, filters=[("id_reservatorio", "in", target_ids)])
                pydict = table.to_pydict()
                num_rows = len(pydict["id_reservatorio"])

                for i in range(num_rows):
                    res_id = str(pydict["id_reservatorio"][i] or "").strip()
                    if res_id in parsed_dams:
                        instante = str(pydict["din_instante"][i] or "").strip()
                        if not instante:
                            continue
                        aflu = clean_num(pydict["val_vazaoafluente"][i])
                        turb = clean_num(pydict["val_vazaoturbinada"][i])
                        vert = clean_num(pydict["val_vazaovertida"][i])
                        defl = clean_num(pydict["val_vazaodefluente"][i])
                        cota = clean_num(pydict["val_nivelmontante"][i])
                        jusante = clean_num(pydict["val_niveljusante"][i])
                        vol_pct = clean_num(pydict["val_volumeutil"][i])

                        # En hidráulica de presas: Defluente = Turbinada + Vertida
                        if defl == 0.0 and (turb > 0.0 or vert > 0.0):
                            defl = round(turb + vert, 2)

                        parsed_dams[res_id]["records"][instante] = {
                            "t": instante,
                            "afluente": aflu,
                            "turbinada": turb,
                            "vertida": vert,
                            "defluente": defl,
                            "cota": cota,
                            "jusante": jusante,
                            "vol_pct": vol_pct
                        }

                logger.info(f"[ONS] Dataset Parquet {os.path.basename(path)} procesado ({num_rows} registros filtrados).")
                continue
            except Exception as e:
                logger.error(f"[ONS] Error procesando Parquet {path}, fallback a CSV si existe: {e}")

        # 2. Procesamiento de archivo CSV (fallback)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    res_id = (row.get("id_reservatorio") or "").strip()
                    if res_id in parsed_dams:
                        instante = (row.get("din_instante") or "").strip()
                        if not instante:
                            continue
                        aflu = clean_num(row.get("val_vazaoafluente"))
                        turb = clean_num(row.get("val_vazaoturbinada"))
                        vert = clean_num(row.get("val_vazaovertida"))
                        defl = clean_num(row.get("val_vazaodefluente"))
                        cota = clean_num(row.get("val_nivelmontante"))
                        jusante = clean_num(row.get("val_niveljusante"))
                        vol_pct = clean_num(row.get("val_volumeutil"))

                        if defl == 0.0 and (turb > 0.0 or vert > 0.0):
                            defl = round(turb + vert, 2)

                        parsed_dams[res_id]["records"][instante] = {
                            "t": instante,
                            "afluente": aflu,
                            "turbinada": turb,
                            "vertida": vert,
                            "defluente": defl,
                            "cota": cota,
                            "jusante": jusante,
                            "vol_pct": vol_pct
                        }
        except Exception as e:
            logger.error(f"[ONS] Error parseando archivo CSV {path}: {e}")

    # Estructurar resultado ordenado cronológicamente
    result: Dict[str, Dict[str, Any]] = {}
    for code, dam in parsed_dams.items():
        sorted_instantes = sorted(dam["records"].keys())
        history = [dam["records"][t] for t in sorted_instantes]
        latest = history[-1].copy() if history else {
            "t": "--", "afluente": 0.0, "turbinada": 0.0, "vertida": 0.0,
            "defluente": 0.0, "cota": 0.0, "jusante": 0.0, "vol_pct": 0.0
        }

        # Continuidad hidráulica: Si el registro más reciente de ONS tiene campos nulos
        # (ej. afluente pendiente de consolidar por balance volumétrico o defluente sin consolidar),
        # buscar hacia atrás en el historial reciente el último valor medido válido > 0.
        if history:
            if latest.get("defluente", 0.0) == 0.0:
                for h in reversed(history):
                    if h.get("defluente", 0.0) > 0.0:
                        latest["defluente"] = h["defluente"]
                        break
            if latest.get("afluente", 0.0) == 0.0:
                for h in reversed(history):
                    if h.get("afluente", 0.0) > 0.0:
                        latest["afluente"] = h["afluente"]
                        break
            if latest.get("cota", 0.0) == 0.0:
                for h in reversed(history):
                    if h.get("cota", 0.0) > 0.0:
                        latest["cota"] = h["cota"]
                        break
            if latest.get("jusante", 0.0) == 0.0:
                for h in reversed(history):
                    if h.get("jusante", 0.0) > 0.0:
                        latest["jusante"] = h["jusante"]
                        break
            if latest.get("vol_pct", 0.0) == 0.0:
                for h in reversed(history):
                    if h.get("vol_pct", 0.0) > 0.0:
                        latest["vol_pct"] = h["vol_pct"]
                        break

        result[code] = {
            "codigo": code,
            "clave": dam["clave"],
            "nombre": dam["nombre"],
            "operador": dam["operador"],
            "rio": dam["rio"],
            "es_parana": dam["es_parana"],
            "es_iguazu": dam["es_iguazu"],
            "principal": dam["principal"],
            "orden": dam["orden"],
            "fuente": "ONS Brasil",
            "fecha": latest["t"],
            "cota": latest["cota"],
            "jusante": latest["jusante"],
            "vol_pct": latest["vol_pct"],
            "afluente": latest["afluente"],
            "turbinada": latest["turbinada"],
            "vertida": latest["vertida"],
            "defluente": latest["defluente"],
            "history": history[-72:]  # Conservar hasta 72 horas para curvas y gráficos
        }

    return result


# =========================================================================
# DATOS COMPLEMENTARIOS: ESTACIONES CATARATAS Y CAPANEMA (COPEL)
# =========================================================================

def parse_copel_dt(dt_str: str) -> str:
    """Parsea fechas tipo '16/10/26 08h' o '16/10/2026 08:00' o '16/10/2026 08' a 'YYYY-MM-DD HH:00:00'."""
    s = str(dt_str).strip()
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{2,4})(?:[T\s](\d{1,2})(?::(\d{2}))?(?::\d{2})?)?h?$', s)
    if m:
        d, mth, y, h, mi = m.groups()
        year = int(y)
        if year < 100:
            year += 2000
        hour = int(h) if h is not None else 0
        minute = int(mi) if mi is not None else 0
        return f"{year:04d}-{int(mth):02d}-{int(d):02d} {hour:02d}:{minute:02d}:00"
    return s


def get_capanema_copel() -> Dict[str, Any]:
    """Obtiene la lectura de regla y caudal de la estación fluviométrica Porto Capanema."""
    search_dirs = [DATA_DIR, BASE_DIR, os.path.join(BASE_DIR, "test"), os.path.join(BASE_DIR, "copel_scraper")]
    for folder in search_dirs:
        p = os.path.join(folder, "Capanema.txt")
        if os.path.exists(p) and os.path.getsize(p) > 10:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [l.strip().split("\t") for l in f if l.strip()]
                    if lines and len(lines[0]) >= 3:
                        latest = lines[0]
                        history = []
                        for row in reversed(lines[:72]):
                            if len(row) >= 3:
                                t_fmt = parse_copel_dt(row[0])
                                r_val = clean_num(row[1])
                                q_val = clean_num(row[2])
                                history.append({
                                    "t": t_fmt,
                                    "regla": r_val,
                                    "caudal": q_val,
                                    "cota": r_val
                                })

                        return {
                            "codigo": "CAPANEMA",
                            "clave": "capanema",
                            "nombre": "Porto Capanema",
                            "operador": "COPEL / ANA",
                            "rio": "Río Iguazú",
                            "tipo": "Punto de Medición Fluviométrica",
                            "fuente": "COPEL / ANA",
                            "lat": -25.5808,
                            "lon": -53.9219,
                            "fecha": parse_copel_dt(latest[0]),
                            "regla": clean_num(latest[1]),
                            "caudal": clean_num(latest[2]),
                            "es_parana": False,
                            "es_iguazu": True,
                            "principal": True,
                            "orden": 7.5,
                            "history": history
                        }
            except Exception as e:
                logger.warning(f"Error leyendo Capanema.txt: {e}")
    return {}


def get_cataratas_copel() -> Dict[str, Any]:
    """Obtiene la lectura de regla y caudal de la estación fluviométrica Cataratas."""
    search_dirs = [DATA_DIR, BASE_DIR, os.path.join(BASE_DIR, "test"), os.path.join(BASE_DIR, "copel_scraper")]
    for folder in search_dirs:
        p = os.path.join(folder, "Cataratas.txt")
        if os.path.exists(p) and os.path.getsize(p) > 10:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [l.strip().split("\t") for l in f if l.strip()]
                    if lines and len(lines[0]) >= 3:
                        latest = lines[0]
                        history = []
                        for row in reversed(lines[:72]):
                            if len(row) >= 3:
                                t_fmt = parse_copel_dt(row[0])
                                r_val = clean_num(row[1])
                                q_val = clean_num(row[2])
                                history.append({
                                    "t": t_fmt,
                                    "regla": r_val,
                                    "caudal": q_val,
                                    "cota": r_val
                                })

                        return {
                            "codigo": "CATARATAS",
                            "clave": "cataratas",
                            "nombre": "Cataratas",
                            "operador": "COPEL / Parques",
                            "rio": "Río Iguazú",
                            "tipo": "Punto de Medición Fluviométrica",
                            "fuente": "COPEL / Parques",
                            "lat": -25.6831,
                            "lon": -54.4406,
                            "fecha": parse_copel_dt(latest[0]),
                            "regla": clean_num(latest[1]),
                            "caudal": clean_num(latest[2]),
                            "es_parana": False,
                            "es_iguazu": True,
                            "principal": True,
                            "orden": 8,
                            "history": history
                        }
            except Exception as e:
                logger.warning(f"Error leyendo Cataratas.txt: {e}")
    return {}


def get_segredo_copel() -> Dict[str, Any]:
    """
    Obtiene la telemetría de la Central Hidroeléctrica Segredo (Gov. Ney Braga)
    extraída directamente del portal oficial de COPEL MHB.
    Columnas en segredo.txt:
    0: Fecha/hora (ej. '16/10/26 08h')
    1: Cota montante (Nivel de agua montante msnm)
    2: Volumen útil (%)
    3: Nivel jusante (msnm)
    4: Vazão afluente (m³/s)
    5: Vazão turbinada (m³/s)
    6: Vazão vertida (m³/s)
    7: Vazão defluente (m³/s)
    8: Precipitación horaria (mm)
    9: Precipitación acumulada (mm)
    """
    search_dirs = [DATA_DIR, BASE_DIR, os.path.join(BASE_DIR, "test"), os.path.join(BASE_DIR, "copel_scraper"), os.path.join(BASE_DIR, "copel_scraper", "ejemplos")]
    for folder in search_dirs:
        p = os.path.join(folder, "segredo.txt")
        if os.path.exists(p) and os.path.getsize(p) > 10:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [l.strip().split("\t") for l in f if l.strip()]
                    if not lines:
                        continue

                    def parse_dt(dt_str: str) -> str:
                        m = re.match(r'^(\d{2})/(\d{2})/(\d{2,4})\s+(\d{1,2})h?$', dt_str.strip())
                        if m:
                            d, mth, y, h = m.groups()
                            year = int(y)
                            if year < 100:
                                year += 2000
                            return f"{year:04d}-{int(mth):02d}-{int(d):02d} {int(h):02d}:00:00"
                        return dt_str.strip()

                    # Buscar la fila más reciente que tenga datos reales (ignorar filas 's/l' preliminares)
                    latest_valid = None
                    for row in lines:
                        if len(row) >= 8:
                            cota = clean_num(row[1])
                            defl = clean_num(row[7])
                            turb = clean_num(row[5])
                            aflu = clean_num(row[4])
                            if cota > 0 or defl > 0 or turb > 0 or aflu > 0:
                                latest_valid = row
                                break

                    if not latest_valid:
                        continue

                    fmt_fecha = parse_dt(latest_valid[0])

                    # Construir historial (hasta 72 horas) en orden cronológico
                    history_copel = []
                    for row in reversed(lines[:72]):
                        if len(row) >= 8:
                            cota_h = clean_num(row[1])
                            defl_h = clean_num(row[7])
                            turb_h = clean_num(row[5])
                            vert_h = clean_num(row[6])
                            aflu_h = clean_num(row[4])
                            if defl_h == 0.0 and (turb_h > 0.0 or vert_h > 0.0):
                                defl_h = round(turb_h + vert_h, 2)

                            if cota_h > 0 or defl_h > 0 or aflu_h > 0:
                                history_copel.append({
                                    "t": parse_dt(row[0]),
                                    "cota": cota_h,
                                    "vol_pct": clean_num(row[2]),
                                    "jusante": clean_num(row[3]),
                                    "afluente": aflu_h,
                                    "turbinada": turb_h,
                                    "vertida": vert_h,
                                    "defluente": defl_h
                                })

                    aflu_val = clean_num(latest_valid[4])
                    turb_val = clean_num(latest_valid[5])
                    vert_val = clean_num(latest_valid[6])
                    defl_val = clean_num(latest_valid[7])
                    if defl_val == 0.0 and (turb_val > 0.0 or vert_val > 0.0):
                        defl_val = round(turb_val + vert_val, 2)

                    return {
                        "codigo": "IGSEGR",
                        "clave": "segredo",
                        "nombre": "Segredo",
                        "operador": "COPEL",
                        "rio": "Río Iguazú",
                        "tipo": "Central Hidroeléctrica",
                        "lat": -25.7903,
                        "lon": -52.1125,
                        "es_parana": False,
                        "es_iguazu": True,
                        "principal": True,
                        "orden": 3,
                        "fuente": "COPEL MHB",
                        "fecha": fmt_fecha,
                        "cota": clean_num(latest_valid[1]),
                        "vol_pct": clean_num(latest_valid[2]),
                        "jusante": clean_num(latest_valid[3]),
                        "afluente": aflu_val,
                        "turbinada": turb_val,
                        "vertida": vert_val,
                        "defluente": defl_val,
                        "history": history_copel
                    }
            except Exception as e:
                logger.warning(f"Error leyendo segredo.txt: {e}")
    return {}


def persist_ons_stations_to_db(dams_data: Dict[str, Dict[str, Any]]):
    """
    Registra y mantiene actualizadas las presas de ONS (Río Paraná y Cuenca del Río Iguazú)
    en las tablas 'estaciones' y 'mediciones' de SQLite para que aparezcan en todos los selectores, gráficos y mapas.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        target_dams = [
            (code, meta["nombre"], f"ONS:{code}", meta.get("lat", 0.0), meta.get("lon", 0.0))
            for code, meta in REPRESAS_CATALOGO.items()
        ]

        for code, nombre, url, lat, lon in target_dams:
            dam = dams_data.get(code)
            if not dam:
                continue

            # 1. Asegurar registro en 'estaciones'
            c.execute("""
                INSERT INTO estaciones (codigo, nombre, url, latitud, longitud, frecuencia_minutos, estado)
                VALUES (?, ?, ?, ?, ?, 60, 'ACTIVA')
                ON CONFLICT(codigo) DO UPDATE SET
                    nombre = excluded.nombre,
                    latitud = excluded.latitud,
                    longitud = excluded.longitud,
                    estado = 'ACTIVA'
            """, (code, nombre, url, lat, lon))

            c.execute("SELECT id FROM estaciones WHERE codigo = ?", (code,))
            row = c.fetchone()
            if not row:
                continue
            st_id = row[0]

            # 2. Insertar registros recientes en 'mediciones'
            history = dam.get("history", [])
            to_insert = []
            for item in history:
                t = item.get("t")
                val = item.get("cota") or item.get("defluente")
                if t and val is not None and val > 0:
                    to_insert.append((st_id, t, round(float(val), 2)))

            if to_insert:
                c.executemany("""
                    INSERT OR IGNORE INTO mediciones (estacion_id, timestamp, altura)
                    VALUES (?, ?, ?)
                """, to_insert)

                last_t = history[-1]["t"]
                c.execute("SELECT COUNT(*) FROM mediciones WHERE estacion_id = ?", (st_id,))
                cnt = c.fetchone()[0]

                c.execute("""
                    UPDATE estaciones
                    SET ultimo_timestamp = ?, total_registros = ?
                    WHERE id = ?
                """, (last_t, cnt, st_id))

        # 3. Asegurar registro y telemetría de Capanema y Cataratas
        capanema = get_capanema_copel()
        if capanema and capanema.get("fecha"):
            c.execute("""
                INSERT INTO estaciones (codigo, nombre, url, latitud, longitud, frecuencia_minutos, estado)
                VALUES (?, ?, ?, ?, ?, 60, 'ACTIVA')
                ON CONFLICT(codigo) DO UPDATE SET
                    nombre = excluded.nombre,
                    latitud = excluded.latitud,
                    longitud = excluded.longitud,
                    estado = 'ACTIVA'
            """, ("CAPANEMA", "Porto Capanema", "COPEL:CAPANEMA", -25.5808, -53.9219))
            c.execute("SELECT id FROM estaciones WHERE codigo = 'CAPANEMA'")
            row_cap = c.fetchone()
            if row_cap:
                st_cap_id = row_cap[0]
                history_cap = capanema.get("history", [])
                to_insert = []
                for item in history_cap:
                    t = item.get("t")
                    val = item.get("regla") or item.get("caudal")
                    if t and val is not None and val > 0:
                        to_insert.append((st_cap_id, t, round(float(val), 2)))
                if to_insert:
                    c.executemany("INSERT OR IGNORE INTO mediciones (estacion_id, timestamp, altura) VALUES (?, ?, ?)", to_insert)
                elif capanema.get("regla"):
                    c.execute("INSERT OR IGNORE INTO mediciones (estacion_id, timestamp, altura) VALUES (?, ?, ?)",
                              (st_cap_id, capanema["fecha"], round(float(capanema["regla"]), 2)))
                c.execute("SELECT COUNT(*) FROM mediciones WHERE estacion_id = ?", (st_cap_id,))
                cnt_cap = c.fetchone()[0]
                c.execute("UPDATE estaciones SET ultimo_timestamp = ?, total_registros = ? WHERE id = ?",
                          (capanema["fecha"], cnt_cap, st_cap_id))

        cataratas = get_cataratas_copel()
        if cataratas and cataratas.get("fecha"):
            c.execute("""
                INSERT INTO estaciones (codigo, nombre, url, latitud, longitud, frecuencia_minutos, estado)
                VALUES (?, ?, ?, ?, ?, 60, 'ACTIVA')
                ON CONFLICT(codigo) DO UPDATE SET
                    nombre = excluded.nombre,
                    latitud = excluded.latitud,
                    longitud = excluded.longitud,
                    estado = 'ACTIVA'
            """, ("CATARATAS", "Cataratas", "COPEL:CATARATAS", -25.6831, -54.4406))
            c.execute("SELECT id FROM estaciones WHERE codigo = 'CATARATAS'")
            row_cat = c.fetchone()
            if row_cat:
                st_cat_id = row_cat[0]
                history_cat = cataratas.get("history", [])
                to_insert = []
                for item in history_cat:
                    t = item.get("t")
                    val = item.get("regla") or item.get("caudal")
                    if t and val is not None and val > 0:
                        to_insert.append((st_cat_id, t, round(float(val), 2)))
                if to_insert:
                    c.executemany("INSERT OR IGNORE INTO mediciones (estacion_id, timestamp, altura) VALUES (?, ?, ?)", to_insert)
                elif cataratas.get("regla"):
                    c.execute("INSERT OR IGNORE INTO mediciones (estacion_id, timestamp, altura) VALUES (?, ?, ?)",
                              (st_cat_id, cataratas["fecha"], round(float(cataratas["regla"]), 2)))
                c.execute("SELECT COUNT(*) FROM mediciones WHERE estacion_id = ?", (st_cat_id,))
                cnt_cat = c.fetchone()[0]
                c.execute("UPDATE estaciones SET ultimo_timestamp = ?, total_registros = ? WHERE id = ?",
                          (cataratas["fecha"], cnt_cat, st_cat_id))

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[ONS-DB] Error persistiendo presas en SQLite: {e}")


# =========================================================================
# BALANCE HIDROLÓGICO INTEGRADO: APORTE A YACYRETÁ
# =========================================================================

def build_hydraulic_summary(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Construye el resumen unificado a partir de ONS y genera las series temporales:
    Q_Total_Yacyreta ≈ Q_Defluente_Itaipu + Q_Defluente_BaixoIguazu
    """
    global _ONS_SUMMARY_CACHE, _LAST_CACHE_UPDATE

    with _ONS_CACHE_LOCK:
        # Usar caché en memoria si tiene menos de 10 minutos y no se forzó refresco
        now_ts = time.time()
        if not force_refresh and _ONS_SUMMARY_CACHE is not None and (now_ts - _LAST_CACHE_UPDATE < 600):
            return _ONS_SUMMARY_CACHE

        files = get_active_ons_files(force_download=force_refresh)
        dams_data = parse_ons_data(files) if files else {}

        # Si ONS no pudo leer datos, intentar fallback al dataset local anterior
        if not dams_data or "PNITAI" not in dams_data or not dams_data["PNITAI"].get("history"):
            logger.warning("[ONS] Datos no disponibles en S3; usando fallback local si existe.")

        # Cargar datos de apoyo y estaciones fluviométricas de COPEL
        copel_segredo = get_segredo_copel()
        capanema = get_capanema_copel()
        cataratas = get_cataratas_copel()

        # Arquitectura de Alta Disponibilidad y Redundancia Dual para SEGREDO (ONS <-> COPEL)
        segredo_ons = dams_data.get("IGSEGR")
        if not segredo_ons or not segredo_ons.get("history"):
            # Si ONS falló o no contiene a Segredo, cargar directamente desde COPEL
            if copel_segredo:
                dams_data["IGSEGR"] = copel_segredo
                logger.info("[REPRESAS] Segredo activado desde COPEL MHB (ONS no disponible o vacío).")
        else:
            # Si ONS está activo, evaluar si COPEL tiene lectura más reciente o si complementa datos pendientes
            if copel_segredo:
                ons_fecha = segredo_ons.get("fecha", "")
                copel_fecha = copel_segredo.get("fecha", "")
                copel_defl = copel_segredo.get("defluente", 0.0)
                copel_aflu = copel_segredo.get("afluente", 0.0)
                ons_defl = segredo_ons.get("defluente", 0.0)
                ons_aflu = segredo_ons.get("afluente", 0.0)

                # Si COPEL tiene telemetría de hora más reciente con defluente medido
                if copel_fecha and copel_fecha > ons_fecha and copel_defl > 0:
                    segredo_ons["fecha"] = copel_fecha
                    segredo_ons["afluente"] = copel_aflu if copel_aflu > 0 else ons_aflu
                    segredo_ons["defluente"] = copel_defl
                    segredo_ons["turbinada"] = copel_segredo.get("turbinada", segredo_ons.get("turbinada", 0.0))
                    segredo_ons["vertida"] = copel_segredo.get("vertida", segredo_ons.get("vertida", 0.0))
                    segredo_ons["cota"] = copel_segredo.get("cota") or segredo_ons.get("cota", 0.0)
                    segredo_ons["jusante"] = copel_segredo.get("jusante") or segredo_ons.get("jusante", 0.0)
                    segredo_ons["vol_pct"] = copel_segredo.get("vol_pct") or segredo_ons.get("vol_pct", 0.0)
                    segredo_ons["fuente"] = "COPEL MHB (Operador Directo)"
                else:
                    # Si ONS aún no consolidó afluente o defluente en su despacho preliminar
                    if ons_defl == 0.0 and copel_defl > 0:
                        segredo_ons["defluente"] = copel_defl
                        segredo_ons["turbinada"] = copel_segredo.get("turbinada", segredo_ons.get("turbinada", 0.0))
                        segredo_ons["vertida"] = copel_segredo.get("vertida", segredo_ons.get("vertida", 0.0))
                        segredo_ons["fuente"] = "Híbrido ONS / COPEL"

                    if ons_aflu == 0.0 and copel_aflu > 0:
                        segredo_ons["afluente"] = copel_aflu
                        segredo_ons["fuente"] = "Híbrido ONS / COPEL"

                if not segredo_ons.get("fuente"):
                    segredo_ons["fuente"] = "ONS Brasil (Validado con COPEL)"
                segredo_ons["fuente_redundante"] = "COPEL MHB Disponible"

                # Incorporar marcas horarias adicionales de COPEL al historial si no existen
                s_hist = segredo_ons.setdefault("history", [])
                existing_ts = {h["t"] for h in s_hist}
                for ch in copel_segredo.get("history", []):
                    if ch["t"] not in existing_ts and (ch.get("defluente", 0) > 0 or ch.get("afluente", 0) > 0):
                        s_hist.append(ch)
                s_hist.sort(key=lambda x: x["t"])
                segredo_ons["history"] = s_hist[-72:]

        # Persistir presas consolidadas en la base de datos para sincronización con mapas y listas
        if dams_data:
            persist_ons_stations_to_db(dams_data)

        itaipu = dams_data.get("PNITAI", {})
        baixo_iguazu = dams_data.get("IGUHBI", {})
        capanema = capanema
        cataratas = cataratas

        # Caudales clave
        q_itaipu_defl = itaipu.get("defluente", 0.0)
        q_itaipu_turb = itaipu.get("turbinada", 0.0)
        q_itaipu_vert = itaipu.get("vertida", 0.0)
        q_itaipu_aflu = itaipu.get("afluente", 0.0)

        q_iguazu_defl = baixo_iguazu.get("defluente", 0.0)
        q_iguazu_turb = baixo_iguazu.get("turbinada", 0.0)
        q_iguazu_vert = baixo_iguazu.get("vertida", 0.0)
        q_capanema = capanema.get("caudal", 0.0)
        q_cataratas = cataratas.get("caudal", 0.0)

        # Caudal del Iguazú que confluye al Paraná
        q_iguazu_efectivo = q_iguazu_defl if q_iguazu_defl > 0 else (q_cataratas if q_cataratas > 0 else q_capanema)
        q_total_yacyreta = round(q_itaipu_defl + q_iguazu_efectivo, 1)

        # Generar serie temporal combinada de las últimas 36 horas
        it_hist = {pt["t"]: pt for pt in itaipu.get("history", [])}
        bx_hist = {pt["t"]: pt for pt in baixo_iguazu.get("history", [])}

        # Unión ordenada de marcas temporales comunes
        all_timestamps = sorted(list(set(list(it_hist.keys()) + list(bx_hist.keys()))))
        recent_timestamps = all_timestamps[-36:] if len(all_timestamps) >= 36 else all_timestamps

        combined_timeline = []
        for t in recent_timestamps:
            it_pt = it_hist.get(t, {})
            bx_pt = bx_hist.get(t, {})

            it_d = it_pt.get("defluente", q_itaipu_defl)
            bx_d = bx_pt.get("defluente", q_iguazu_defl)

            combined_timeline.append({
                "t": t,
                "itaipu_defluente": it_d,
                "itaipu_turbinada": it_pt.get("turbinada", q_itaipu_turb),
                "itaipu_vertida": it_pt.get("vertida", q_itaipu_vert),
                "iguazu_defluente": bx_d,
                "iguazu_turbinada": bx_pt.get("turbinada", q_iguazu_turb),
                "iguazu_vertida": bx_pt.get("vertida", q_iguazu_vert),
                "total_yacyreta": round(it_d + bx_d, 1)
            })

        # Lista completa de centrales ordenadas para la tabla hidráulica
        # 1. Cascada del Alto Paraná: Jupiá -> Porto Primavera -> Itaipú
        # 2. Cascada del Iguazú aguas arriba -> aguas abajo
        # 3. Porto Capanema
        # 4. Cataratas
        # 5. Centrales secundarias
        centrales_ordenadas = []
        for code in ["PNJUPI", "PNPPRI", "PNITAI", "IGGBMU", "IGSEGR", "IGSSAN", "IGSOSO", "IGSCAX", "IGUHBI"]:
            if code in dams_data:
                centrales_ordenadas.append(dams_data[code])

        if capanema:
            centrales_ordenadas.append(capanema)

        if cataratas:
            centrales_ordenadas.append(cataratas)

        # Agregar secundarias (Jordão, Fundão, Santa Clara)
        for code in ["JDJORD", "IGFND", "IGSCL"]:
            if code in dams_data:
                centrales_ordenadas.append(dams_data[code])

        jupia_dam = dams_data.get("PNJUPI", {})
        ppri_dam = dams_data.get("PNPPRI", {})

        summary = {
            "success": True,
            "fuente": "Operador Nacional do Sistema Elétrico (ONS Brasil) - Open Data S3",
            "balance_yacyreta": {
                "caudal_total_m3s": q_total_yacyreta,
                "aporte_itaipu_m3s": q_itaipu_defl,
                "aporte_iguazu_m3s": q_iguazu_efectivo,
                "pct_itaipu": round((q_itaipu_defl / q_total_yacyreta * 100), 1) if q_total_yacyreta > 0 else 0,
                "pct_iguazu": round((q_iguazu_efectivo / q_total_yacyreta * 100), 1) if q_total_yacyreta > 0 else 0,
                "descripcion": "Balance hidráulico combinado en tránsito hacia la Central Hidroeléctrica Yacyretá."
            },
            "jupia": {
                "nombre": "Jupiá",
                "operador": "CTG Brasil",
                "rio": "Río Paraná (Alto Paraná)",
                "afluente": jupia_dam.get("afluente", 0.0),
                "defluente": jupia_dam.get("defluente", 0.0),
                "turbinada": jupia_dam.get("turbinada", 0.0),
                "vertida": jupia_dam.get("vertida", 0.0),
                "cota": jupia_dam.get("cota", 0.0),
                "vol_pct": jupia_dam.get("vol_pct", 0.0),
                "fecha": jupia_dam.get("fecha", "--")
            },
            "porto_primavera": {
                "nombre": "Porto Primavera",
                "operador": "Auren Energia",
                "rio": "Río Paraná (Alto Paraná)",
                "afluente": ppri_dam.get("afluente", 0.0),
                "defluente": ppri_dam.get("defluente", 0.0),
                "turbinada": ppri_dam.get("turbinada", 0.0),
                "vertida": ppri_dam.get("vertida", 0.0),
                "cota": ppri_dam.get("cota", 0.0),
                "vol_pct": ppri_dam.get("vol_pct", 0.0),
                "fecha": ppri_dam.get("fecha", "--")
            },
            "itaipu": {
                "afluente": q_itaipu_aflu,
                "defluente": q_itaipu_defl,
                "turbinada": q_itaipu_turb,
                "vertida": q_itaipu_vert,
                "cota": itaipu.get("cota", 0.0),
                "jusante": itaipu.get("jusante", 0.0),
                "vol_pct": itaipu.get("vol_pct", 0.0),
                "fecha": itaipu.get("fecha", "--")
            },
            "iguazu": {
                "baixo_iguazu_defluente": q_iguazu_defl,
                "baixo_iguazu_turbinada": q_iguazu_turb,
                "baixo_iguazu_vertida": q_iguazu_vert,
                "baixo_iguazu_afluente": baixo_iguazu.get("afluente", 0.0),
                "baixo_iguazu_cota": baixo_iguazu.get("cota", 0.0),
                "capanema_caudal": q_capanema,
                "capanema_regla": capanema.get("regla", 0.0),
                "cataratas_caudal": q_cataratas,
                "cataratas_regla": cataratas.get("regla", 0.0),
                "fecha": baixo_iguazu.get("fecha", "--")
            },
            "capanema": capanema,
            "segredo_copel": copel_segredo,
            "centrales_lista": centrales_ordenadas,
            "timeline": combined_timeline,
            "ultima_actualizacion_ons": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        _ONS_SUMMARY_CACHE = summary
        _LAST_CACHE_UPDATE = now_ts
        return summary


def get_hydraulic_summary() -> Dict[str, Any]:
    """Acceso público al balance hidráulico consolidado."""
    return build_hydraulic_summary(force_refresh=False)


def sync_ons_represas() -> Dict[str, Any]:
    """
    Sincroniza y descarga datos frescos de ONS S3 y estaciones de COPEL.
    Ejecutado automáticamente en minutos [20, 50] y bajo demanda.
    """
    logger.info("[ONS-SYNC] Iniciando sincronización programada de ONS (Itaipú + Cuenca del Iguazú)...")
    try:
        # Ejecutar primero el extractor de Cataratas, Capanema y Segredo si existe (guardando en DATA_DIR)
        script_path = os.path.join(BASE_DIR, "copel_scraper", "descargar_copel.py")
        if os.path.exists(script_path):
            try:
                subprocess.run([sys.executable, script_path, DATA_DIR], cwd=BASE_DIR, capture_output=True, timeout=45)
            except Exception as ex:
                logger.warning(f"[ONS-SYNC] Aviso ejecutando descargar_copel.py: {ex}")

        summary = build_hydraulic_summary(force_refresh=True)

        logger.info(f"[ONS-SYNC] Sincronización ONS finalizada: Itaipú {summary['itaipu']['defluente']} m³/s, Iguazú {summary['iguazu']['baixo_iguazu_defluente']} m³/s.")
        return {
            "success": True,
            "fuente": summary.get("fuente"),
            "total_yacyreta": summary["balance_yacyreta"]["caudal_total_m3s"],
            "fecha_ons": summary.get("ultima_actualizacion_ons")
        }
    except Exception as e:
        logger.error(f"[ONS-SYNC] Error en sincronización ONS: {e}")
        return {"success": False, "error": str(e)}


# Alias de compatibilidad
sync_copel_and_itaipu = sync_ons_represas
