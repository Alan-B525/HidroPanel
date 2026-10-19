"""
backend/config.py
Configuración centralizada para HidroPanel
"""

import os
import sys

# Compatibilidad de rutas para Producción y PyInstaller
# STATIC_DIR: compatible con sys._MEIPASS para public/ cuando se empaqueta con PyInstaller.
# RUNTIME_DIR: directorio base del ejecutable o raíz del proyecto para data/, mapas_simepar/ y SQLite.
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    RUNTIME_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RUNTIME_DIR = BUNDLE_DIR

BASE_DIR = RUNTIME_DIR

# Directorio de recursos estáticos web (Frontend)
STATIC_DIR = os.path.join(BUNDLE_DIR, "public")

# Directorios de persistencia en tiempo de ejecución (fuera de binario temporal)
DATA_DIR = os.path.join(RUNTIME_DIR, "data")
DB_PATH = os.path.join(RUNTIME_DIR, "hidrografia.db")
SIMEPAR_MAPS_DIR = os.path.join(RUNTIME_DIR, "mapas_simepar")
URL_LIST_FILE = os.path.join(RUNTIME_DIR, "url_stations.txt")
if not os.path.exists(URL_LIST_FILE) and os.path.exists(os.path.join(BUNDLE_DIR, "url_stations.txt")):
    URL_LIST_FILE = os.path.join(BUNDLE_DIR, "url_stations.txt")

SIMEPAR_URL_FILE = os.path.join(RUNTIME_DIR, "mapa_simepar.txt")
if not os.path.exists(SIMEPAR_URL_FILE) and os.path.exists(os.path.join(BUNDLE_DIR, "mapa_simepar.txt")):
    SIMEPAR_URL_FILE = os.path.join(BUNDLE_DIR, "mapa_simepar.txt")

# Asegurar existencia de directorios de ejecución
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SIMEPAR_MAPS_DIR, exist_ok=True)

DEFAULT_PORT = 8050
DEFAULT_SIMEPAR_URL = "https://lb01.simepar.br/riak/pgw-simepar_telemetricas/mapa_prec_ontem.png"

# Frecuencias de sincronización automática (en minutos)
AUTO_SYNC_MINUTES = [10, 30, 50]
# Sincronización automática de ONS / Represas (cada 30 min a las XX:20 y XX:50 hs)
ONS_REPRESAS_SYNC_MINUTES = [20, 50]

# Hora de descarga diaria de SIMEPAR
SIMEPAR_DOWNLOAD_HOUR = 7
SIMEPAR_DOWNLOAD_MINUTE = 0
