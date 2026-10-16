"""
backend/config.py
Configuración centralizada para HidroPanel
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "hidrografia.db")
STATIC_DIR = os.path.join(BASE_DIR, "public")
SIMEPAR_MAPS_DIR = os.path.join(BASE_DIR, "mapas_simepar")
URL_LIST_FILE = os.path.join(BASE_DIR, "url_stations.txt")
SIMEPAR_URL_FILE = os.path.join(BASE_DIR, "mapa_simepar.txt")

DEFAULT_PORT = 8050
DEFAULT_SIMEPAR_URL = "https://lb01.simepar.br/riak/pgw-simepar_telemetricas/mapa_prec_ontem.png"

# Frecuencias de sincronización automática (en minutos)
AUTO_SYNC_MINUTES = [10, 30, 50]
# Sincronización automática de ONS / Represas (cada 30 min a las XX:20 y XX:50 hs)
ONS_REPRESAS_SYNC_MINUTES = [20, 50]

# Hora de descarga diaria de SIMEPAR
SIMEPAR_DOWNLOAD_HOUR = 7
SIMEPAR_DOWNLOAD_MINUTE = 0

DATA_DIR = os.path.join(BASE_DIR, "data")
