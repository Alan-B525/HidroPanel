"""
backend/services/represas_service.py
Integración Hidráulica Unificada para Itaipú y Presas de la Cuenca del Plata.
Fuente Oficial Primaria: ONS (Operador Nacional do Sistema Elétrico de Brasil)
Dataset S3: https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/dados_hidrologicos_ho/DADOS_HIDROLOGICOS_HO_YYYY_MM.csv
"""

import os
import glob
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
from typing import Dict, Any, List, Optional, Tuple
import sqlite3
from ..config import BASE_DIR, DATA_DIR, DB_PATH

logger = logging.getLogger("hidropanel.represas_service")

ONS_S3_BASE_URL = "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/dados_hidrologicos_ho"

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

REPRESAS_CATALOGO = {
    "PNJUPI": {
        "codigo": "PNJUPI",
        "clave": "jupia",
        "nombre": "Jupiá",
        "operador": "CTG Brasil",
        "rio": "Paraná",
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
        "rio": "Paraná",
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
        "operador": "Itaipú Binacional",
        "rio": "Paraná",
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
        "rio": "Iguazú",
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
        "rio": "Iguazú",
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
        "rio": "Iguazú",
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
        "rio": "Iguazú",
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
        "rio": "Iguazú",
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
        "rio": "Iguazú",
        "lat": -25.5033,
        "lon": -53.6717,
        "es_parana": False,
        "es_iguazu": True,
        "principal": True,
        "orden": 7
    },
    "JDJORD": {
        "codigo": "JDJORD",
        "clave": "jordao",
        "nombre": "Jordão",
        "operador": "COPEL",
        "rio": "Iguazú · Afluente Jordão",
        "lat": -25.7533,
        "lon": -52.0525,
        "es_parana": False,
        "es_iguazu": True,
        "principal": False,
        "orden": 8
    },
    "IGFND": {
        "codigo": "IGFND",
        "clave": "fundao",
        "nombre": "Fundão",
        "operador": "COPEL / Elejor",
        "rio": "Iguazú · Afluente Jordão",
        "lat": -25.7034,
        "lon": -52.0020,
        "es_parana": False,
        "es_iguazu": True,
        "principal": False,
        "orden": 9
    },
    "IGSCL": {
        "codigo": "IGSCL",
        "clave": "santa_clara",
        "nombre": "Santa Clara",
        "operador": "COPEL / Elejor",
        "rio": "Iguazú · Afluente Jordão",
        "lat": -25.6456,
        "lon": -51.9569,
        "es_parana": False,
        "es_iguazu": True,
        "principal": False,
        "orden": 10
    }
}

_ONS_CACHE_LOCK = threading.Lock()
_ONS_SUMMARY_CACHE: Optional[Dict[str, Any]] = None
_LAST_CACHE_UPDATE: float = 0.0


def clean_num(val_str: Any) -> Optional[float]:
    """
    Convierte números a float.
    REGLA 2: Prohibido el falso cero. Retorna None estricto si no existe dato válido.
    """
    if val_str is None:
        return None
    if isinstance(val_str, (int, float)):
        import math
        if math.isnan(val_str) or math.isinf(val_str):
            return None
        return round(float(val_str), 2)
    s = str(val_str).strip()
    if not s or s.upper() in ('-', '--', 'N/A', 'NAN', 'NONE', 'NULL', 'S/D', 'S/E', 'S/L', 'SD'):
        return None

    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    elif '.' in s:
        parts = s.split('.')
        if len(parts) == 2 and len(parts[1]) == 3 and parts[0].isdigit() and int(parts[0]) > 0:
            s = parts[0] + parts[1]

    try:
        return round(float(s), 2)
    except Exception:
        return None


def parse_copel_dt(dt_str: str) -> Optional[str]:
    """Parsea fechas a formato ISO-8601 canónico 'YYYY-MM-DDTHH:MM:SS'."""
    if not dt_str:
        return None
    s = str(dt_str).strip()
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{2,4})(?:[T\s](\d{1,2})(?::(\d{2}))?(?::\d{2})?)?h?$', s)
    if m:
        d, mth, y, h, mi = m.groups()
        year = int(y)
        if year < 100:
            year += 2000
        hour = int(h) if h is not None else 0
        minute = int(mi) if mi is not None else 0
        return f"{year:04d}-{int(mth):02d}-{int(d):02d}T{hour:02d}:{minute:02d}:00"
    if " " in s and len(s) >= 19:
        return s[:19].replace(" ", "T")
    if "T" in s and len(s) >= 19:
        return s[:19]
    return s


def normalize_iso_timestamp(dt_str: Optional[str]) -> Optional[str]:
    """
    Normaliza marcas de tiempo ONS y de estaciones a formato ISO-8601 canónico.
    En ONS, la medición final del día (24:00) se etiqueta como '23:59:00',
    que corresponde al inicio (00:00:00) del día siguiente.
    """
    if not dt_str:
        return dt_str
    s = str(dt_str).strip()
    if ":59:" in s or s.endswith(":59:00") or s.endswith(":59"):
        try:
            iso_clean = s[:19].replace(" ", "T")
            dt = datetime.fromisoformat(iso_clean)
            dt = dt + timedelta(minutes=1)
            return dt.strftime("%Y-%m-%dT%H:00:00")
        except Exception:
            pass
    if " " in s and len(s) >= 19:
        return s[:19].replace(" ", "T")
    return s


def get_month_info(dt: datetime, ext: str = "parquet") -> Tuple[int, int, str]:
    return dt.year, dt.month, f"DADOS_HIDROLOGICOS_HO_{dt.year}_{dt.month:02d}.{ext}"


def get_prev_month(dt: datetime) -> datetime:
    first_of_this_month = dt.replace(day=1)
    return first_of_this_month - timedelta(days=1)


def fetch_ons_file_for_month(year: int, month: int, force: bool = False, prefer_parquet: bool = True) -> Optional[str]:
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
                    needs_download = (local_len != remote_len and remote_len > 1000)
                else:
                    needs_download = True
        except Exception:
            needs_download = not os.path.exists(local_path)

        if needs_download:
            try:
                dl_req = urllib.request.Request(remote_url, headers={"User-Agent": "Mozilla/5.0 HidroPanel/2.0"})
                with urllib.request.urlopen(dl_req, context=SSL_CTX, timeout=30) as resp:
                    data = resp.read()
                    if len(data) > 1000:
                        with open(local_path, "wb") as f:
                            f.write(data)
            except Exception as e:
                logger.error(f"[ONS] Error descargando {fname}: {e}")

        if os.path.exists(local_path) and os.path.getsize(local_path) > 1000:
            return local_path

    return None


def get_active_ons_files(force_download: bool = False) -> List[str]:
    now = datetime.now()
    cur_year, cur_month, _ = get_month_info(now)
    prev_dt = get_prev_month(now)
    prev_year, prev_month, _ = get_month_info(prev_dt)

    files_to_read = []
    cur_file = fetch_ons_file_for_month(cur_year, cur_month, force=force_download)
    if now.day <= 3 or cur_file is None:
        prev_file = fetch_ons_file_for_month(prev_year, prev_month, force=False)
        if prev_file:
            files_to_read.append(prev_file)
    if cur_file:
        files_to_read.append(cur_file)

    return files_to_read


def parse_ons_data(files: List[str]) -> Dict[str, Dict[str, Any]]:
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
            "records": {}
        }

    for path in files:
        if not os.path.exists(path):
            continue

        if path.lower().endswith(".parquet"):
            try:
                import pyarrow.parquet as pq
                cols = [
                    "id_reservatorio", "din_instante", "val_vazaoafluente",
                    "val_vazaoturbinada", "val_vazaovertida", "val_vazaodefluente",
                    "val_nivelmontante", "val_niveljusante", "val_volumeutil"
                ]
                target_ids = []
                for k in REPRESAS_CATALOGO.keys():
                    target_ids.append(k)
                    target_ids.append(f"{k} ")
                    target_ids.append(f"{k:<6s}")
                target_ids = list(set(target_ids))
                table = pq.read_table(path, columns=cols, filters=[("id_reservatorio", "in", target_ids)])
                pydict = table.to_pydict()
                num_rows = len(pydict["id_reservatorio"])

                for i in range(num_rows):
                    res_id = str(pydict["id_reservatorio"][i] or "").strip()
                    if res_id in parsed_dams:
                        instante_raw = str(pydict["din_instante"][i] or "").strip()
                        if not instante_raw:
                            continue
                        instante_iso = normalize_iso_timestamp(instante_raw[:19].replace(" ", "T"))
                        parsed_dams[res_id]["records"][instante_iso] = {
                            "t": instante_iso,
                            "afluente": clean_num(pydict["val_vazaoafluente"][i]),
                            "turbinada": clean_num(pydict["val_vazaoturbinada"][i]),
                            "vertida": clean_num(pydict["val_vazaovertida"][i]),
                            "defluente": clean_num(pydict["val_vazaodefluente"][i]),
                            "cota": clean_num(pydict["val_nivelmontante"][i]),
                            "jusante": clean_num(pydict["val_niveljusante"][i]),
                            "vol_pct": clean_num(pydict["val_volumeutil"][i])
                        }
                continue
            except Exception as e:
                logger.error(f"[ONS] Error procesando Parquet {path}: {e}")

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    res_id = (row.get("id_reservatorio") or "").strip()
                    if res_id in parsed_dams:
                        instante_raw = (row.get("din_instante") or "").strip()
                        if not instante_raw:
                            continue
                        instante_iso = normalize_iso_timestamp(instante_raw[:19].replace(" ", "T"))
                        parsed_dams[res_id]["records"][instante_iso] = {
                            "t": instante_iso,
                            "afluente": clean_num(row.get("val_vazaoafluente")),
                            "turbinada": clean_num(row.get("val_vazaoturbinada")),
                            "vertida": clean_num(row.get("val_vazaovertida")),
                            "defluente": clean_num(row.get("val_vazaodefluente")),
                            "cota": clean_num(row.get("val_nivelmontante")),
                            "jusante": clean_num(row.get("val_niveljusante")),
                            "vol_pct": clean_num(row.get("val_volumeutil"))
                        }
        except Exception as e:
            logger.error(f"[ONS] Error parseando CSV {path}: {e}")

    result: Dict[str, Dict[str, Any]] = {}
    for code, dam in parsed_dams.items():
        sorted_instantes = sorted(dam["records"].keys())
        history = [dam["records"][t] for t in sorted_instantes]
        latest = history[-1].copy() if history else {
            "t": None, "afluente": None, "turbinada": None, "vertida": None,
            "defluente": None, "cota": None, "jusante": None, "vol_pct": None
        }
        # Si el último registro carece de caudales calculados (común en la hora preliminar de ONS
        # donde se publica la cota pero no el balance de vazão), rescatar los caudales más recientes
        if history and (latest.get("defluente") is None or latest.get("afluente") is None):
            for rec in reversed(history):
                if rec.get("defluente") is not None and rec.get("afluente") is not None:
                    if latest.get("defluente") is None:
                        latest["defluente"] = rec.get("defluente")
                    if latest.get("afluente") is None:
                        latest["afluente"] = rec.get("afluente")
                    if latest.get("turbinada") is None:
                        latest["turbinada"] = rec.get("turbinada")
                    if latest.get("vertida") is None:
                        latest["vertida"] = rec.get("vertida")
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
            "fuente": "ONS",
            "fecha": latest["t"],
            "cota": latest["cota"],
            "jusante": latest["jusante"],
            "vol_pct": latest["vol_pct"],
            "afluente": latest["afluente"],
            "turbinada": latest["turbinada"],
            "vertida": latest["vertida"],
            "defluente": latest["defluente"],
            "history": history[-72:]
        }

    return result


def get_capanema_copel() -> Dict[str, Any]:
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
                                t_iso = parse_copel_dt(row[0])
                                r_val = clean_num(row[1])
                                q_val = clean_num(row[2])
                                history.append({
                                    "t": t_iso,
                                    "regla": r_val,
                                    "caudal": q_val,
                                    "cota": r_val
                                })

                        return {
                            "codigo": "CAPANEMA",
                            "clave": "capanema",
                            "nombre": "Porto Capanema",
                            "operador": "COPEL / ANA",
                            "rio": "Iguazú",
                            "tipo": "Posto Hidrométrico",
                            "fuente": "COPEL",
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
                                t_iso = parse_copel_dt(row[0])
                                r_val = clean_num(row[1])
                                q_val = clean_num(row[2])
                                history.append({
                                    "t": t_iso,
                                    "regla": r_val,
                                    "caudal": q_val,
                                    "cota": r_val
                                })

                        return {
                            "codigo": "CATARATAS",
                            "clave": "cataratas",
                            "nombre": "Cataratas",
                            "operador": "COPEL / Parques",
                            "rio": "Iguazú",
                            "tipo": "Posto Hidrométrico",
                            "fuente": "COPEL",
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
    search_dirs = [DATA_DIR, BASE_DIR, os.path.join(BASE_DIR, "test"), os.path.join(BASE_DIR, "copel_scraper"), os.path.join(BASE_DIR, "copel_scraper", "ejemplos")]
    for folder in search_dirs:
        p = os.path.join(folder, "segredo.txt")
        if os.path.exists(p) and os.path.getsize(p) > 10:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [l.strip().split("\t") for l in f if l.strip()]
                    if not lines:
                        continue

                    latest_valid = None
                    # Prioridad 1: fila más reciente con lectura oficial de defluente
                    for row in lines:
                        if len(row) >= 8 and clean_num(row[7]) is not None:
                            latest_valid = row
                            break

                    # Prioridad 2: fila más reciente con cota u otra variable
                    if not latest_valid:
                        for row in lines:
                            if len(row) >= 8 and (clean_num(row[1]) is not None or clean_num(row[4]) is not None):
                                latest_valid = row
                                break

                    # Prioridad 3: primera fila disponible
                    if not latest_valid and lines:
                        for row in lines:
                            if len(row) >= 8:
                                latest_valid = row
                                break

                    if not latest_valid:
                        continue

                    fmt_fecha = parse_copel_dt(latest_valid[0])
                    history_copel = []
                    for row in reversed(lines[:72]):
                        if len(row) >= 8:
                            history_copel.append({
                                "t": parse_copel_dt(row[0]),
                                "cota": clean_num(row[1]),
                                "vol_pct": clean_num(row[2]),
                                "jusante": clean_num(row[3]),
                                "afluente": clean_num(row[4]),
                                "turbinada": clean_num(row[5]),
                                "vertida": clean_num(row[6]),
                                "defluente": clean_num(row[7])
                            })

                    return {
                        "codigo": "IGSEGR",
                        "clave": "segredo",
                        "nombre": "Segredo",
                        "operador": "COPEL",
                        "rio": "Iguazú",
                        "tipo": "Usina Hidrelétrica",
                        "lat": -25.7903,
                        "lon": -52.1125,
                        "es_parana": False,
                        "es_iguazu": True,
                        "principal": True,
                        "orden": 3,
                        "fuente": "COPEL",
                        "fecha": fmt_fecha,
                        "cota": clean_num(latest_valid[1]),
                        "vol_pct": clean_num(latest_valid[2]),
                        "jusante": clean_num(latest_valid[3]),
                        "afluente": clean_num(latest_valid[4]),
                        "turbinada": clean_num(latest_valid[5]),
                        "vertida": clean_num(latest_valid[6]),
                        "defluente": clean_num(latest_valid[7]),
                        "history": history_copel
                    }
            except Exception as e:
                logger.warning(f"Error leyendo segredo.txt: {e}")
    return {}


def get_represas_dto() -> List[Dict[str, Any]]:
    """
    Retorna la lista de represas y estaciones hidrológicas de la cuenca
    cumpliendo estrictamente con el CONTRATO DTO UNIFICADO.
    """
    summary = build_hydraulic_summary(force_refresh=False)
    centrales = summary.get("centrales_lista", [])
    fetched_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    dto_list: List[Dict[str, Any]] = []
    for c in centrales:
        src = str(c.get("fuente", "ONS")).upper()
        if "COPEL" in src:
            fuente_norm = "COPEL"
        elif "ENGIE" in src:
            fuente_norm = "ENGIE"
        elif "ITAIPU" in src:
            fuente_norm = "ITAIPU"
        else:
            fuente_norm = "ONS"

        f_raw = c.get("fecha")
        m_at = parse_copel_dt(f_raw) or f_raw or fetched_at
        if m_at and " " in m_at:
            m_at = m_at.replace(" ", "T")

        level = clean_num(c.get("cota") if c.get("cota") is not None else c.get("regla"))
        flow_out = clean_num(c.get("defluente") if c.get("defluente") is not None else c.get("caudal"))

        dto_list.append({
            "station_id": str(c.get("codigo", "")),
            "station_name": str(c.get("nombre", "")),
            "river": "Iguazú" if c.get("es_iguazu") else "Paraná",
            "source": fuente_norm,
            "measured_at": str(m_at),
            "fetched_at": fetched_at,
            "level_m": level,
            "variation_m": None,
            "flow_in_m3s": clean_num(c.get("afluente")),
            "flow_out_m3s": flow_out,
            "flow_turbined_m3s": clean_num(c.get("turbinada")),
            "flow_spilled_m3s": clean_num(c.get("vertida")),
            "rain_mm": None,
            "trend": None,
            "raw_status": "OPERATIVA"
        })

    return dto_list


def persist_ons_stations_to_db(dams_data: Dict[str, Dict[str, Any]]):
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

            history = dam.get("history", [])
            to_insert = []
            for item in history:
                t = item.get("t")
                val = item.get("cota") if item.get("cota") is not None else item.get("defluente")
                if t and val is not None:
                    to_insert.append((st_id, t.replace("T", " "), round(float(val), 2)))

            if to_insert:
                c.executemany("""
                    INSERT OR IGNORE INTO mediciones (estacion_id, timestamp, altura)
                    VALUES (?, ?, ?)
                """, to_insert)

                last_t = history[-1]["t"].replace("T", " ")
                c.execute("SELECT COUNT(*) FROM mediciones WHERE estacion_id = ?", (st_id,))
                cnt = c.fetchone()[0]

                c.execute("""
                    UPDATE estaciones
                    SET ultimo_timestamp = ?, total_registros = ?
                    WHERE id = ?
                """, (last_t, cnt, st_id))

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[ONS-DB] Error persistiendo presas en SQLite: {e}")


def build_hydraulic_summary(force_refresh: bool = False) -> Dict[str, Any]:
    global _ONS_SUMMARY_CACHE, _LAST_CACHE_UPDATE

    with _ONS_CACHE_LOCK:
        now_ts = time.time()
        if not force_refresh and _ONS_SUMMARY_CACHE is not None and (now_ts - _LAST_CACHE_UPDATE < 600):
            return _ONS_SUMMARY_CACHE

        files = get_active_ons_files(force_download=force_refresh)
        dams_data = parse_ons_data(files) if files else {}

        copel_segredo = get_segredo_copel()
        capanema = get_capanema_copel()
        cataratas = get_cataratas_copel()

        if dams_data:
            persist_ons_stations_to_db(dams_data)

        itaipu = dams_data.get("PNITAI", {})
        baixo_iguazu = dams_data.get("IGUHBI", {})

        q_it_def = clean_num(itaipu.get("defluente"))
        q_bx_def = clean_num(baixo_iguazu.get("defluente"))
        q_cat = clean_num(cataratas.get("caudal"))
        q_cap = clean_num(capanema.get("caudal"))

        # Caudal representativo de confluencia Iguazú: Cataratas como aforo downstream final, con fallback
        q_iguazu_efectivo = q_cat if q_cat is not None else (q_cap if q_cap is not None else q_bx_def)
        
        q_total_yacyreta = None
        if q_it_def is not None and q_iguazu_efectivo is not None:
            q_total_yacyreta = round(q_it_def + q_iguazu_efectivo, 1)

        # Generar serie temporal combinada para gráficos de Itaipú y Caudales Yacyretá
        it_hist = {normalize_iso_timestamp(pt["t"]): pt for pt in itaipu.get("history", []) if pt.get("t")}
        bx_hist = {normalize_iso_timestamp(pt["t"]): pt for pt in baixo_iguazu.get("history", []) if pt.get("t")}
        cat_hist = {normalize_iso_timestamp(pt["t"]): pt for pt in cataratas.get("history", []) if pt.get("t")}
        cap_hist = {normalize_iso_timestamp(pt["t"]): pt for pt in capanema.get("history", []) if pt.get("t")}

        all_timestamps = sorted(list(set(list(it_hist.keys()) + list(cat_hist.keys()) + list(bx_hist.keys()))))
        recent_timestamps = all_timestamps[-48:] if len(all_timestamps) >= 48 else all_timestamps

        combined_timeline = []
        for t in recent_timestamps:
            it_pt = it_hist.get(t)
            if not it_pt:
                try:
                    cur_dt = datetime.fromisoformat(t)
                    prev_t = (cur_dt - timedelta(hours=1)).strftime("%Y-%m-%dT%H:00:00")
                    next_t = (cur_dt + timedelta(hours=1)).strftime("%Y-%m-%dT%H:00:00")
                    it_pt = it_hist.get(prev_t) or it_hist.get(next_t) or {}
                except Exception:
                    it_pt = {}

            bx_pt = bx_hist.get(t, {})
            cat_pt = cat_hist.get(t, {})
            cap_pt = cap_hist.get(t, {})

            it_d = clean_num(it_pt.get("defluente"))

            # Río Iguazú: Cataratas como aforo downstream hacia Yacyretá, con fallback
            ig_d = clean_num(cat_pt.get("caudal"))
            if ig_d is None:
                ig_d = clean_num(cap_pt.get("caudal"))
            if ig_d is None:
                ig_d = clean_num(bx_pt.get("defluente"))

            tot = round(it_d + ig_d, 1) if (it_d is not None and ig_d is not None) else None

            combined_timeline.append({
                "t": t,
                "itaipu_defluente": it_d,
                "itaipu_turbinada": clean_num(it_pt.get("turbinada")),
                "itaipu_vertida": clean_num(it_pt.get("vertida")),
                "iguazu_defluente": ig_d,
                "iguazu_turbinada": clean_num(bx_pt.get("turbinada")),
                "iguazu_vertida": clean_num(bx_pt.get("vertida")),
                "total_yacyreta": tot
            })

        centrales_ordenadas = []
        for code in ["PNJUPI", "PNPPRI", "PNITAI", "IGGBMU", "IGSEGR", "IGSSAN", "IGSOSO", "IGSCAX", "IGUHBI"]:
            if code == "IGSEGR" and copel_segredo and (copel_segredo.get("defluente") is not None or copel_segredo.get("cota") is not None):
                centrales_ordenadas.append(copel_segredo)
            elif code in dams_data:
                centrales_ordenadas.append(dams_data[code])

        if capanema:
            centrales_ordenadas.append(capanema)
        if cataratas:
            centrales_ordenadas.append(cataratas)

        for code in ["JDJORD", "IGFND", "IGSCL"]:
            if code in dams_data:
                centrales_ordenadas.append(dams_data[code])

        # Enriquecer cada central con los campos exactos del Contrato DTO
        fetched_at_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        for c in centrales_ordenadas:
            src_str = str(c.get("fuente", "ONS")).upper()
            src_norm = "COPEL" if "COPEL" in src_str else ("ENGIE" if "ENGIE" in src_str else "ONS")
            t_iso = parse_copel_dt(c.get("fecha")) or c.get("fecha")
            c["station_id"] = str(c.get("codigo", ""))
            c["station_name"] = str(c.get("nombre", ""))
            c["river"] = "Iguazú" if c.get("es_iguazu") else "Paraná"
            c["source"] = src_norm
            c["measured_at"] = t_iso.replace(" ", "T") if t_iso else None
            c["fetched_at"] = fetched_at_iso
            c["level_m"] = clean_num(c.get("cota") if c.get("cota") is not None else c.get("regla"))
            c["variation_m"] = None
            c["flow_in_m3s"] = clean_num(c.get("afluente"))
            c["flow_out_m3s"] = clean_num(c.get("defluente") if c.get("defluente") is not None else c.get("caudal"))
            c["flow_turbined_m3s"] = clean_num(c.get("turbinada"))
            c["flow_spilled_m3s"] = clean_num(c.get("vertida"))
            c["rain_mm"] = None
            c["trend"] = None
            c["raw_status"] = "OPERATIVA"

        jupia_dam = dams_data.get("PNJUPI", {})
        ppri_dam = dams_data.get("PNPPRI", {})

        summary = {
            "success": True,
            "fuente": "Operador Nacional do Sistema Elétrico · ONS Brasil · Open Data S3",
            "balance_yacyreta": {
                "caudal_total_m3s": q_total_yacyreta,
                "aporte_itaipu_m3s": q_it_def,
                "aporte_iguazu_m3s": q_iguazu_efectivo,
                "pct_itaipu": round((q_it_def / q_total_yacyreta * 100), 1) if (q_total_yacyreta and q_it_def) else None,
                "pct_iguazu": round((q_iguazu_efectivo / q_total_yacyreta * 100), 1) if (q_total_yacyreta and q_iguazu_efectivo) else None,
                "descripcion": "Balance hidráulico combinado verificado en tránsito hacia Yacyretá."
            },
            "jupia": jupia_dam,
            "porto_primavera": ppri_dam,
            "itaipu": itaipu,
            "iguazu": {
                "baixo_iguazu_defluente": q_bx_def,
                "baixo_iguazu_turbinada": clean_num(baixo_iguazu.get("turbinada")),
                "baixo_iguazu_vertida": clean_num(baixo_iguazu.get("vertida")),
                "baixo_iguazu_afluente": clean_num(baixo_iguazu.get("afluente")),
                "baixo_iguazu_cota": clean_num(baixo_iguazu.get("cota")),
                "capanema_caudal": q_cap,
                "capanema_regla": clean_num(capanema.get("regla")),
                "cataratas_caudal": q_cat,
                "cataratas_regla": clean_num(cataratas.get("regla")),
                "fecha": baixo_iguazu.get("fecha")
            },
            "capanema": capanema,
            "segredo_copel": copel_segredo,
            "centrales_lista": centrales_ordenadas,
            "timeline": combined_timeline,
            "ultima_actualizacion_ons": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        }

        _ONS_SUMMARY_CACHE = summary
        _LAST_CACHE_UPDATE = now_ts
        return summary


def get_hydraulic_summary() -> Dict[str, Any]:
    return build_hydraulic_summary(force_refresh=False)


def sync_ons_represas() -> Dict[str, Any]:
    logger.info("[ONS-SYNC] Iniciando sincronización de ONS y presas...")
    try:
        script_path = os.path.join(BASE_DIR, "copel_scraper", "descargar_copel.py")
        if os.path.exists(script_path):
            try:
                subprocess.run([sys.executable, script_path, DATA_DIR], cwd=BASE_DIR, capture_output=True, timeout=45)
            except Exception as ex:
                logger.warning(f"[ONS-SYNC] Aviso ejecutando descargar_copel.py: {ex}")

        summary = build_hydraulic_summary(force_refresh=True)
        return {
            "success": True,
            "fuente": summary.get("fuente"),
            "total_yacyreta": summary["balance_yacyreta"]["caudal_total_m3s"],
            "fecha_ons": summary.get("ultima_actualizacion_ons")
        }
    except Exception as e:
        logger.error(f"[ONS-SYNC] Error en sincronización ONS: {e}")
        return {"success": False, "error": str(e)}

sync_copel_and_itaipu = sync_ons_represas


_PARQUET_HISTORY_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_PARQUET_CACHE_LOCK = threading.Lock()


def get_dam_historical_data(dam_code: str, month_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Extrae la serie histórica horaria de una central hidroeléctrica desde los archivos .parquet
    mensuales oficiales de ONS en data/.
    Soporta visualización consolidada multimensual ('all', 'year_2026', 'last_6m', 'last_3m')
    o individual mes a mes, concatenando series temporales en orden cronológico exacto.
    """
    global _PARQUET_HISTORY_CACHE
    code = (dam_code or "PNITAI").upper().strip()

    # 1. Encontrar todos los archivos Parquet disponibles en data/
    monthly_files: Dict[str, str] = {}
    search_dirs = [DATA_DIR, os.path.join(BASE_DIR, "data")]
    for d in search_dirs:
        if os.path.exists(d):
            try:
                for fname in os.listdir(d):
                    m = re.search(r"DADOS_HIDROLOGICOS_HO_(\d{4})[-_](\d{2})\.parquet$", fname, re.IGNORECASE)
                    if m:
                        p = os.path.join(d, fname)
                        key = f"{m.group(1)}_{m.group(2)}"
                        monthly_files[key] = p
            except Exception as e_scan:
                logger.warning(f"[ONS] Error explorando directorio {d}: {e_scan}")

    sorted_keys = sorted(monthly_files.keys())
    rev_keys = sorted(monthly_files.keys(), reverse=True)

    month_names = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    }

    def format_m_label(m_id: str) -> str:
        parts = m_id.split('_')
        y_int, mo_int = int(parts[0]), int(parts[1])
        return f"{month_names.get(mo_int, '')[:3]} {y_int}"

    # Construir opciones de períodos disponibles
    periodos_disponibles = []
    if len(sorted_keys) > 1:
        first_lbl = format_m_label(sorted_keys[0])
        last_lbl = format_m_label(sorted_keys[-1])
        periodos_disponibles.append({
            "id": "all",
            "codigo": "all",
            "label": f"Todo el Histórico ({first_lbl} – {last_lbl})",
            "grupo": "Períodos Consolidados"
        })

        # Agrupados por año
        years_seen = sorted(list(set(k.split('_')[0] for k in sorted_keys)), reverse=True)
        for y in years_seen:
            y_months = [k for k in sorted_keys if k.startswith(f"{y}_")]
            if len(y_months) > 1:
                periodos_disponibles.append({
                    "id": f"year_{y}",
                    "codigo": f"year_{y}",
                    "label": f"Año {y} Completo",
                    "grupo": "Períodos Consolidados"
                })

        if len(sorted_keys) >= 6:
            periodos_disponibles.append({
                "id": "last_6m",
                "codigo": "last_6m",
                "label": f"Últimos 6 meses ({format_m_label(rev_keys[5])} – {format_m_label(rev_keys[0])})",
                "grupo": "Períodos Consolidados"
            })
        if len(sorted_keys) >= 3:
            periodos_disponibles.append({
                "id": "last_3m",
                "codigo": "last_3m",
                "label": f"Últimos 3 meses ({format_m_label(rev_keys[2])} – {format_m_label(rev_keys[0])})",
                "grupo": "Períodos Consolidados"
            })

    for k in rev_keys:
        parts = k.split('_')
        y_int, mo_int = int(parts[0]), int(parts[1])
        periodos_disponibles.append({
            "id": k,
            "codigo": f"{y_int}-{mo_int:02d}",
            "label": f"{month_names.get(mo_int, '')} {y_int}",
            "year": y_int,
            "month": mo_int,
            "grupo": "Meses Individuales"
        })

    # Catálogo estructurado para selector del modal
    centrales_disponibles = [
        {"codigo": "PNITAI", "nombre": "Itaipú Binacional", "rio": "Río Paraná", "fuente": "ONS", "grupo": "Cuenca Río Paraná"},
        {"codigo": "PNPPRI", "nombre": "Porto Primavera", "rio": "Río Paraná", "fuente": "ONS", "grupo": "Cuenca Río Paraná"},
        {"codigo": "PNJUPI", "nombre": "Jupiá", "rio": "Río Paraná", "fuente": "ONS", "grupo": "Cuenca Río Paraná"},
        {"codigo": "PNISOL", "nombre": "Ilha Solteira", "rio": "Río Paraná", "fuente": "ONS", "grupo": "Cuenca Río Paraná"},
        {"codigo": "IGUHBI", "nombre": "Baixo Iguaçu", "rio": "Río Iguazú", "fuente": "ONS", "grupo": "Cuenca Río Iguazú"},
        {"codigo": "CATARATAS", "nombre": "Cataratas", "rio": "Río Iguazú", "fuente": "COPEL", "grupo": "Cuenca Río Iguazú"},
        {"codigo": "CAPANEMA", "nombre": "Porto Capanema", "rio": "Río Iguazú", "fuente": "COPEL", "grupo": "Cuenca Río Iguazú"},
        {"codigo": "IGSCAX", "nombre": "Salto Caxias", "rio": "Río Iguazú", "fuente": "ONS", "grupo": "Cuenca Río Iguazú"},
        {"codigo": "IGSOSO", "nombre": "Salto Osório", "rio": "Río Iguazú", "fuente": "ONS", "grupo": "Cuenca Río Iguazú"},
        {"codigo": "IGSSAN", "nombre": "Salto Santiago", "rio": "Río Iguazú", "fuente": "ONS", "grupo": "Cuenca Río Iguazú"},
        {"codigo": "IGSEGR", "nombre": "Segredo", "rio": "Río Iguazú", "fuente": "COPEL / ONS", "grupo": "Cuenca Río Iguazú"},
        {"codigo": "IGGBMU", "nombre": "Foz do Areia", "rio": "Río Iguazú", "fuente": "ONS", "grupo": "Cuenca Río Iguazú"},
        {"codigo": "JDJORD", "nombre": "Jordão", "rio": "Río Iguazú · Afluente", "fuente": "ONS", "grupo": "Cuenca Río Iguazú"},
        {"codigo": "IGFND", "nombre": "Fundão", "rio": "Río Iguazú · Afluente", "fuente": "ONS", "grupo": "Cuenca Río Iguazú"},
        {"codigo": "IGSCL", "nombre": "Santa Clara", "rio": "Río Iguazú · Afluente", "fuente": "ONS", "grupo": "Cuenca Río Iguazú"}
    ]

    # Verificar si es estación de aforo fluviométrico COPEL (Cataratas o Capanema)
    if code in ("CATARATAS", "CAPANEMA"):
        flu_dam = get_cataratas_copel() if code == "CATARATAS" else get_capanema_copel()
        hist = flu_dam.get("history", [])
        pts = []
        for h in hist:
            t_val = h.get("t")
            if t_val:
                pts.append({
                    "t": t_val,
                    "caudal": clean_num(h.get("caudal")),
                    "regla": clean_num(h.get("regla") if h.get("regla") is not None else h.get("cota"))
                })
        pts.sort(key=lambda x: x["t"])
        return {
            "success": True,
            "codigo": code,
            "nombre": flu_dam.get("nombre", code),
            "rio": flu_dam.get("rio", "Iguazú"),
            "operador": flu_dam.get("operador", "COPEL"),
            "fuente": "COPEL",
            "mes": "all",
            "periodo": "all",
            "periodos_disponibles": periodos_disponibles,
            "meses_disponibles": periodos_disponibles,
            "centrales_disponibles": centrales_disponibles,
            "variables": [
                {"id": "caudal", "nombre": "Caudal Pasante", "unidad": "m³/s", "color": "#f59e0b", "eje": "y", "default": True, "has_data": True, "puntos_validos": len(pts)},
                {"id": "regla", "nombre": "Nivel Regla", "unidad": "m", "color": "#0284c7", "eje": "y1", "default": True, "has_data": True, "puntos_validos": len(pts)}
            ],
            "puntos": pts,
            "total": len(pts)
        }

    # Resolver qué archivos Parquet leer según el período solicitado
    target_files: List[str] = []
    target_period_key = None

    req = (month_str or "").strip().lower()
    if req in ("all", "todo"):
        target_files = [monthly_files[k] for k in sorted_keys]
        target_period_key = "all"
    elif req.startswith("year_") or (len(req) == 4 and req.isdigit()):
        y_str = req.replace("year_", "")
        target_files = [monthly_files[k] for k in sorted_keys if k.startswith(f"{y_str}_")]
        target_period_key = f"year_{y_str}"
    elif req == "last_6m":
        target_files = [monthly_files[k] for k in rev_keys[:6]][::-1]
        target_period_key = "last_6m"
    elif req == "last_3m":
        target_files = [monthly_files[k] for k in rev_keys[:3]][::-1]
        target_period_key = "last_3m"
    elif req:
        norm_m = req.replace("-", "_")
        if norm_m in monthly_files:
            target_files = [monthly_files[norm_m]]
            target_period_key = norm_m
        else:
            m_match = re.match(r"^(\d{4})_(\d{2})$", norm_m)
            if m_match:
                y_req, mo_req = int(m_match.group(1)), int(m_match.group(2))
                dl_p = fetch_ons_file_for_month(y_req, mo_req, force=False)
                if dl_p and os.path.exists(dl_p):
                    monthly_files[norm_m] = dl_p
                    target_files = [dl_p]
                    target_period_key = norm_m

    if not target_files:
        if len(sorted_keys) > 1:
            target_files = [monthly_files[k] for k in sorted_keys]
            target_period_key = "all"
        elif sorted_keys:
            target_files = [monthly_files[sorted_keys[0]]]
            target_period_key = sorted_keys[0]

    if not target_files:
        return {
            "success": False,
            "error": "Archivo Parquet ONS no disponible localmente",
            "periodos_disponibles": periodos_disponibles,
            "meses_disponibles": periodos_disponibles,
            "centrales_disponibles": centrales_disponibles
        }

    # Verificar caché para los archivos de este período
    mtimes_sig = ",".join(f"{os.path.basename(p)}:{os.path.getmtime(p)}" for p in target_files if os.path.exists(p))
    cache_key = f"{code}:{target_period_key}:{mtimes_sig}"
    with _PARQUET_CACHE_LOCK:
        if cache_key in _PARQUET_HISTORY_CACHE:
            _, cached_res = _PARQUET_HISTORY_CACHE[cache_key]
            res_copy = dict(cached_res)
            res_copy["periodos_disponibles"] = periodos_disponibles
            res_copy["meses_disponibles"] = periodos_disponibles
            res_copy["centrales_disponibles"] = centrales_disponibles
            return res_copy

    try:
        import pyarrow.parquet as pq
        import pyarrow as pa

        cols = [
            "id_reservatorio", "nom_reservatorio", "nom_bacia", "din_instante",
            "val_vazaodefluente", "val_vazaoturbinada", "val_vazaovertida", "val_vazaoafluente",
            "val_nivelmontante", "val_niveljusante", "val_volumeutil",
            "val_vazaooutrasestruturas", "val_vazaotransferida", "val_vazaovertidanaoturbinavel"
        ]

        tables = []
        for p in target_files:
            if os.path.exists(p):
                tbl = pq.read_table(p, columns=cols, filters=[("id_reservatorio", "=", code)])
                if tbl.num_rows > 0:
                    tables.append(tbl)

        if not tables:
            return {
                "success": False,
                "error": f"No se registraron datos en ONS para la central {code} en el período seleccionado.",
                "codigo": code,
                "periodo": target_period_key,
                "periodos_disponibles": periodos_disponibles,
                "meses_disponibles": periodos_disponibles,
                "centrales_disponibles": centrales_disponibles
            }

        combined = pa.concat_tables(tables) if len(tables) > 1 else tables[0]
        num_rows = combined.num_rows
        pydict = combined.to_pydict()

        dam_meta = REPRESAS_CATALOGO.get(code, {})
        dam_name = dam_meta.get("nombre")
        dam_rio = dam_meta.get("rio")
        dam_operador = dam_meta.get("operador", "ONS")

        if num_rows > 0 and not dam_name:
            dam_name = str(pydict["nom_reservatorio"][0] or code).strip().title()
            dam_rio = str(pydict["nom_bacia"][0] or "Paraná").strip().title()

        if not dam_name:
            dam_name = code

        times = pydict["din_instante"]
        defl = pydict["val_vazaodefluente"]
        turb = pydict["val_vazaoturbinada"]
        vert = pydict["val_vazaovertida"]
        aflu = pydict["val_vazaoafluente"]
        cota = pydict["val_nivelmontante"]
        jusan = pydict["val_niveljusante"]
        vol = pydict["val_volumeutil"]
        outras = pydict["val_vazaooutrasestruturas"]
        transf = pydict["val_vazaotransferida"]
        vert_nt = pydict["val_vazaovertidanaoturbinavel"]

        puntos = []
        for i in range(num_rows):
            dt = times[i]
            if dt is None:
                continue
            if isinstance(dt, datetime):
                t_str = dt.strftime("%Y-%m-%dT%H:%M:%S")
            else:
                t_str = str(dt)[:19].replace(" ", "T")
            t_iso = normalize_iso_timestamp(t_str)

            puntos.append({
                "t": t_iso,
                "defluente": clean_num(defl[i]),
                "turbinada": clean_num(turb[i]),
                "vertida": clean_num(vert[i]),
                "afluente": clean_num(aflu[i]),
                "cota": clean_num(cota[i]),
                "jusante": clean_num(jusan[i]),
                "vol_util": clean_num(vol[i]),
                "outras": clean_num(outras[i]),
                "transferida": clean_num(transf[i]),
                "vertida_nao_turb": clean_num(vert_nt[i])
            })

        puntos.sort(key=lambda p: p["t"])

        variables = [
            {"id": "defluente", "nombre": "Defluente", "unidad": "m³/s", "color": "#10b981", "eje": "y", "default": True},
            {"id": "turbinada", "nombre": "Turbinado", "unidad": "m³/s", "color": "#0284c7", "eje": "y", "default": True},
            {"id": "vertida", "nombre": "Vertido", "unidad": "m³/s", "color": "#f97316", "eje": "y", "default": True},
            {"id": "afluente", "nombre": "Afluente", "unidad": "m³/s", "color": "#8b5cf6", "eje": "y", "default": False},
            {"id": "cota", "nombre": "Cota Montante", "unidad": "msnm", "color": "#06b6d4", "eje": "y1", "default": False},
            {"id": "jusante", "nombre": "Nivel Jusante", "unidad": "msnm", "color": "#64748b", "eje": "y1", "default": False},
            {"id": "vol_util", "nombre": "Vol. Útil", "unidad": "%", "color": "#ec4899", "eje": "y2", "default": False},
            {"id": "outras", "nombre": "Otras Estruct.", "unidad": "m³/s", "color": "#a855f7", "eje": "y", "default": False},
            {"id": "transferida", "nombre": "Transferido", "unidad": "m³/s", "color": "#14b8a6", "eje": "y", "default": False},
            {"id": "vertida_nao_turb", "nombre": "Vert. No Turb.", "unidad": "m³/s", "color": "#f43f5e", "eje": "y", "default": False}
        ]

        for v in variables:
            v_id = v["id"]
            valid_pts = sum(1 for p in puntos if p.get(v_id) is not None)
            v["has_data"] = valid_pts > 0
            v["puntos_validos"] = valid_pts

        result = {
            "success": True,
            "codigo": code,
            "nombre": dam_name,
            "rio": dam_rio or "Paraná",
            "operador": dam_operador,
            "fuente": "ONS",
            "mes": target_period_key,
            "periodo": target_period_key,
            "periodos_disponibles": periodos_disponibles,
            "meses_disponibles": periodos_disponibles,
            "centrales_disponibles": centrales_disponibles,
            "variables": variables,
            "puntos": puntos,
            "total": len(puntos)
        }

        with _PARQUET_CACHE_LOCK:
            _PARQUET_HISTORY_CACHE[cache_key] = (time.time(), result)

        return result
    except Exception as e:
        logger.error(f"[ONS-PARQUET] Error leyendo histórico de presa {code}: {e}")
        return {
            "success": False,
            "error": f"Error leyendo archivo Parquet: {str(e)}",
            "codigo": code,
            "periodos_disponibles": periodos_disponibles,
            "meses_disponibles": periodos_disponibles,
            "centrales_disponibles": centrales_disponibles
        }
