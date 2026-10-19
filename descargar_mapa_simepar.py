#!/usr/bin/env python3
"""
descargar_mapa_simepar.py
Descarga automática diaria del mapa de precipitación acumulada de SIMEPAR.
- Lee URL desde mapa_simepar.txt
- Valida la integridad del archivo PNG antes del guardado atómico
- Almacena en 'mapas_simepar/YYYY-MM-DD.png'
"""

import sys
import os
import time
import logging
from datetime import datetime, date, timedelta
import urllib.request
import ssl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("mapa_simepar")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
URL_FILE = os.path.join(BASE_DIR, "mapa_simepar.txt")
OUTPUT_DIR = os.path.join(BASE_DIR, "mapas_simepar")
DEFAULT_URL = "https://lb01.simepar.br/riak/pgw-simepar_telemetricas/mapa_prec_ontem.png"

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def get_image_url() -> str:
    if os.path.exists(URL_FILE):
        try:
            with open(URL_FILE, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    u = line.strip()
                    if u.startswith("http://") or u.startswith("https://"):
                        return u
        except Exception as e:
            logger.warning(f"No se pudo leer {URL_FILE}: {e}")
    return DEFAULT_URL


def download_simepar_map(target_date: date = None, output_dir: str = OUTPUT_DIR, retries: int = 3) -> str:
    if target_date is None:
        target_date = date.today() - timedelta(days=1)
    elif isinstance(target_date, datetime):
        target_date = target_date.date()

    os.makedirs(output_dir, exist_ok=True)
    filename = f"{target_date.strftime('%Y-%m-%d')}.png"
    filepath = os.path.join(output_dir, filename)

    url = get_image_url()
    logger.info(f"Descargando mapa SIMEPAR para {target_date} desde: {url}")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HidroPanel/2.0",
            "Accept": "image/png,image/*;q=0.8"
        }
    )

    content = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=25) as resp:
                content = resp.read()
                if len(content) > 1000 and content.startswith(b"\x89PNG\r\n\x1a\n"):
                    break
        except Exception as e:
            logger.warning(f"Intento {attempt}/{retries} falló: {e}")
            if attempt < retries:
                time.sleep(3 * attempt)

    if not content or not content.startswith(b"\x89PNG\r\n\x1a\n"):
        logger.error(f"Fallo al descargar imagen válida de SIMEPAR tras {retries} intentos.")
        return None

    try:
        temp_filepath = filepath + ".tmp"
        with open(temp_filepath, "wb") as f:
            f.write(content)
        if os.path.exists(filepath):
            os.remove(filepath)
        os.rename(temp_filepath, filepath)

        logger.info(f"Mapa guardado exitosamente: {filepath} ({len(content)/1024:.1f} KB)")
        return filepath
    except Exception as e:
        logger.error(f"Error escribiendo archivo: {e}")
        return None


if __name__ == "__main__":
    download_simepar_map()
