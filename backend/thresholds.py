"""
backend/thresholds.py
Catálogo de umbrales hidrológicos oficiales de Prefectura Naval Argentina (Alerta y Evacuación).
Eliminados todos los niveles no oficiales o sintéticos (Vigilancia y Emergencia).
"""

from typing import Optional, Dict, Any, List
import sqlite3
import logging
from datetime import datetime
from .config import DB_PATH

logger = logging.getLogger("hidropanel.thresholds")

# Umbrales hidrométricos oficiales base (en metros)
# Formato: código: {"alerta": float, "evacuacion": float}
STATION_THRESHOLDS: Dict[str, Dict[str, Optional[float]]] = {
    # Alto Paraná e Iguazú
    "PUERTO_IGUAZU": {"alerta": 25.0, "evacuacion": 28.0},
    "PUERTO_MACUCO-PAGEWNIVEL": {"alerta": 23.0, "evacuacion": 26.0},
    "PUNTA_PELIGRO-PAGEWNIVEL": {"alerta": 21.0, "evacuacion": 24.0},
    "PUERTO_LIBERTAD": {"alerta": 23.0, "evacuacion": 24.5},
    "EL_DORADO": {"alerta": 14.0, "evacuacion": 17.0},
    "PUERTO_LIBERTADOR": {"alerta": 13.5, "evacuacion": 15.0},
    "PUERTO_MANI": {"alerta": 12.0, "evacuacion": 13.5},
    "SANTA_ANA": {"alerta": 10.0, "evacuacion": 11.5},
    "POSADAS": {"alerta": 10.5, "evacuacion": 11.5},
    "ITUZAINGO": {"alerta": 3.5, "evacuacion": 4.0},
    "ITA_IBATE": {"alerta": 7.0, "evacuacion": 7.5},
    "ITATI": {"alerta": 6.8, "evacuacion": 7.5},
    "PASO_DE_LA_PATRIA": {"alerta": 6.5, "evacuacion": 7.0},
    
    # Paraná Medio / Eje Corrientes-Chaco-Santa Fe
    "CORRIENTES": {"alerta": 6.5, "evacuacion": 7.0},
    "BARRANQUERAS": {"alerta": 6.0, "evacuacion": 6.5},
    "EMPEDRADO": {"alerta": 6.5, "evacuacion": 7.0},
    "BELLAVISTA": {"alerta": 6.0, "evacuacion": 6.5},
    "LAVALLE": {"alerta": 5.8, "evacuacion": 6.2},
    "GOYA": {"alerta": 5.2, "evacuacion": 5.7},
    "RECONQUISTA": {"alerta": 5.1, "evacuacion": 5.3},
    "ESQUINA": {"alerta": 4.8, "evacuacion": 5.2},
    "LAPAZ": {"alerta": 5.8, "evacuacion": 6.15},
    "SANTAELENA": {"alerta": 5.5, "evacuacion": 6.0},
    "HERNANDARIAS": {"alerta": 5.3, "evacuacion": 5.8},
    "SANTAFE": {"alerta": 5.3, "evacuacion": 5.7},
    "PARANA": {"alerta": 4.7, "evacuacion": 5.0},
    "DIAMANTE_NIVEL": {"alerta": 5.3, "evacuacion": 5.5},

    # Paraná Inferior / Delta
    "TIMBUES": {"alerta": 5.0, "evacuacion": 5.3},
    "SAN_LORENZO": {"alerta": 5.0, "evacuacion": 5.3},
    "ROSARIO": {"alerta": 5.0, "evacuacion": 5.3},
    "ARROYOSECO": {"alerta": 4.5, "evacuacion": 4.9},
    "VILLA_CONSTITUCION": {"alerta": 4.3, "evacuacion": 4.7},
    "SAN_NICOLAS": {"alerta": 4.0, "evacuacion": 4.4},
    "RAMALLO": {"alerta": 3.5, "evacuacion": 4.0},
    "VUELTAOBLIGADO": {"alerta": 3.3, "evacuacion": 3.7},
    "SAN_PEDRO": {"alerta": 3.1, "evacuacion": 3.4},
    "SAN_PEDRO_2": {"alerta": 3.1, "evacuacion": 3.4},
    "BARADERO_LEVEL": {"alerta": 2.8, "evacuacion": 3.1},
    "ZARATE": {"alerta": 2.0, "evacuacion": 2.2},
    "LASROSAS": {"alerta": 2.4, "evacuacion": 2.8},
    "ESCOBAR": {"alerta": 2.6, "evacuacion": 3.0},

    # Río de la Plata y Costa
    "BALIZAMITRE_LEVEL": {"alerta": 2.8, "evacuacion": 3.2},
    "BUENOSAIRES_PRIMERESPIGON": {"alerta": 2.8, "evacuacion": 3.2},
    "BUENOSAIRES": {"alerta": 2.8, "evacuacion": 3.2},
    "LAPLATA": {"alerta": 2.6, "evacuacion": 3.0},
    "MAGDALENA": {"alerta": 2.4, "evacuacion": 2.8},
    "SANCLEMENTE": {"alerta": 2.3, "evacuacion": 2.6},

    # Río Paraguay
    "PILCOMAYO": {"alerta": 5.35, "evacuacion": 6.0},
    "FORMOSA": {"alerta": 7.8, "evacuacion": 8.3},
    "LASPALMAS": {"alerta": 6.0, "evacuacion": 6.5},
    "DALMACIA": {"alerta": 5.8, "evacuacion": 6.4}
}

# Caché en memoria de umbrales personalizados configurados por el usuario
_CUSTOM_THRESHOLDS: Dict[str, Dict[str, Optional[float]]] = {}


def init_thresholds_table(conn: sqlite3.Connection):
    """Crea la tabla de persistencia de umbrales en la base de datos."""
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS umbrales_config (
                codigo TEXT PRIMARY KEY,
                vigilancia REAL,
                alerta REAL,
                evacuacion REAL,
                emergencia REAL,
                alertas_activas INTEGER DEFAULT 1,
                actualizado_en TEXT
            );
        """)
        # Migración segura
        try:
            conn.execute("ALTER TABLE umbrales_config ADD COLUMN alertas_activas INTEGER DEFAULT 1;")
        except sqlite3.OperationalError:
            pass


def load_custom_thresholds():
    """Carga los umbrales oficiales/personalizados desde SQLite al caché de memoria."""
    global _CUSTOM_THRESHOLDS
    try:
        conn = sqlite3.connect(DB_PATH)
        init_thresholds_table(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT codigo, alerta, evacuacion, alertas_activas FROM umbrales_config")
        rows = cursor.fetchall()
        loaded = {}
        for r in rows:
            code = r[0].upper().strip()
            loaded[code] = {
                "alerta": r[1],
                "evacuacion": r[2],
                "alertas_activas": bool(r[3] if len(r) > 3 and r[3] is not None else 1),
                "custom": True
            }
        _CUSTOM_THRESHOLDS = loaded
        conn.close()
    except Exception as e:
        logger.warning(f"No se pudieron cargar umbrales personalizados: {e}")


def get_station_thresholds(station_code: str) -> Dict[str, Any]:
    """
    Obtiene los umbrales oficiales para una estación (Alerta y Evacuación):
    Prioriza configuración guardada en SQLite;
    si no existe, retorna los valores oficiales base del catálogo PNA.
    """
    norm_code = station_code.upper().strip()
    
    # 1. Override guardado en base de datos
    if norm_code in _CUSTOM_THRESHOLDS:
        custom = dict(_CUSTOM_THRESHOLDS[norm_code])
        return {
            "alerta": custom.get("alerta"),
            "evacuacion": custom.get("evacuacion"),
            "alertas_activas": custom.get("alertas_activas", True),
            "custom": True
        }

    # 2. Valores oficiales base PNA
    base = STATION_THRESHOLDS.get(norm_code)
    if base:
        return {
            "alerta": base.get("alerta"),
            "evacuacion": base.get("evacuacion"),
            "alertas_activas": True,
            "custom": False
        }

    return {"alerta": None, "evacuacion": None, "alertas_activas": True, "custom": False}


def get_all_thresholds_dict() -> Dict[str, Dict[str, Any]]:
    """
    Devuelve un diccionario con los umbrales vigentes de todas las estaciones registradas.
    """
    all_codes = set(STATION_THRESHOLDS.keys()).union(_CUSTOM_THRESHOLDS.keys())
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT codigo, nombre FROM estaciones")
        db_stations = cursor.fetchall()
        conn.close()
        for r in db_stations:
            all_codes.add(r[0].upper().strip())
    except Exception:
        pass

    result = {}
    for code in sorted(all_codes):
        result[code] = get_station_thresholds(code)
    return result


def save_station_thresholds(codigo: str, 
                            alerta: Optional[float] = None, 
                            evacuacion: Optional[float] = None, 
                            alertas_activas: Optional[bool] = None,
                            db_conn: Optional[sqlite3.Connection] = None,
                            **kwargs) -> Dict[str, Any]:
    """
    Guarda o actualiza umbrales oficiales (Alerta y Evacuación) en SQLite.
    Elimina cualquier remanente de vigilancia o emergencia.
    """
    norm_code = codigo.upper().strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _coerce(val):
        if val is None or val == "" or str(val).lower() == "null":
            return None
        try:
            return round(float(val), 2)
        except (ValueError, TypeError):
            return None

    current = get_station_thresholds(norm_code)

    ale = _coerce(alerta) if alerta is not None else current.get("alerta")
    eva = _coerce(evacuacion) if evacuacion is not None else current.get("evacuacion")
    
    act = bool(alertas_activas) if alertas_activas is not None else current.get("alertas_activas", True)
    act_int = 1 if act else 0

    should_close = False
    conn = db_conn
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute("PRAGMA busy_timeout = 30000;")
        should_close = True

    try:
        init_thresholds_table(conn)
        with conn:
            conn.execute("""
                INSERT INTO umbrales_config (codigo, alerta, evacuacion, vigilancia, emergencia, alertas_activas, actualizado_en)
                VALUES (?, ?, ?, NULL, NULL, ?, ?)
                ON CONFLICT(codigo) DO UPDATE SET
                    alerta = excluded.alerta,
                    evacuacion = excluded.evacuacion,
                    vigilancia = NULL,
                    emergencia = NULL,
                    alertas_activas = excluded.alertas_activas,
                    actualizado_en = excluded.actualizado_en
            """, (norm_code, ale, eva, act_int, now_str))
    finally:
        if should_close:
            conn.close()

    _CUSTOM_THRESHOLDS[norm_code] = {
        "alerta": ale,
        "evacuacion": eva,
        "alertas_activas": act,
        "custom": True
    }

    logger.info(f"Umbrales guardados para {norm_code}: Alerta={ale}, Evacuación={eva}, Activo={act}")
    return {
        "success": True,
        "codigo": norm_code,
        "umbrales": get_station_thresholds(norm_code)
    }


def reset_station_thresholds(codigo: str) -> Dict[str, Any]:
    """
    Restaura los umbrales de una estación a sus valores oficiales base eliminando el override.
    """
    norm_code = codigo.upper().strip()
    try:
        conn = sqlite3.connect(DB_PATH)
        init_thresholds_table(conn)
        with conn:
            conn.execute("DELETE FROM umbrales_config WHERE codigo = ?", (norm_code,))
        conn.close()
    except Exception as e:
        logger.error(f"Error al restablecer umbrales de {norm_code}: {e}")

    _CUSTOM_THRESHOLDS.pop(norm_code, None)
    logger.info(f"Umbrales de {norm_code} restablecidos a valores oficiales.")
    return {
        "success": True,
        "codigo": norm_code,
        "umbrales": get_station_thresholds(norm_code)
    }


def calculate_station_status(altura_agp: Optional[float], 
                             thresholds: Dict[str, Any],
                             altura_pna: Optional[float] = None, 
                             timestamp_pna: Optional[str] = None) -> str:
    """
    Determina el estado hidrológico oficial de la estación:
    1. Si las alertas están desactivadas para este hidrómetro -> 'desactivado'.
    2. Si hay lectura oficial reciente de PNA (<= 6 horas) -> se evalúa la altura de PNA.
    3. Si PNA no ha actualizado en más de 6 horas o no existe -> se evalúa la telemetría de AGP.
    Retorna exclusivamente estados oficiales: 'evacuacion', 'alerta', 'normal', 'sin_datos' o 'desactivado'.
    """
    if not thresholds.get("alertas_activas", True):
        return "desactivado"

    altura_evaluar = None
    if altura_pna is not None and timestamp_pna:
        try:
            pna_dt = None
            if "-" in timestamp_pna and ":" in timestamp_pna:
                pna_dt = datetime.strptime(timestamp_pna[:19], "%Y-%m-%d %H:%M:%S")
            elif "/" in timestamp_pna:
                pna_dt = datetime.strptime(timestamp_pna[:16], "%d/%m/%Y %H:%M")
            
            if pna_dt:
                horas_dif = abs((datetime.now() - pna_dt).total_seconds()) / 3600.0
                if horas_dif <= 6.0:
                    altura_evaluar = altura_pna
        except Exception:
            pass

    if altura_evaluar is None:
        altura_evaluar = altura_agp

    if altura_evaluar is None:
        return "sin_datos"

    evac = thresholds.get("evacuacion")
    alerta = thresholds.get("alerta")

    # 1. Nivel oficial de Evacuación
    if evac is not None and altura_evaluar >= evac:
        return "evacuacion"

    # 2. Nivel oficial de Alerta
    if alerta is not None and altura_evaluar >= alerta:
        return "alerta"

    return "normal"


# Inicialización inicial de caché al importar el módulo
load_custom_thresholds()
