"""
test/verify_iguazu_umbrales.py
Auditoría automatizada de umbrales hidrológicos, escalas oficiales PNA/AGP
y verificación técnica del hidrómetro Puerto Iguazú.
Garantiza:
1. Coherencia matemática (threshold_alert < threshold_evacuation) en todas las estaciones.
2. Ausencia total de umbrales no oficiales o sintéticos (Vigilancia / Emergencia).
3. Respeto a las lecturas originales de PNA y AGP sin cálculo, interpolación ni falsos ceros.
"""

import sys
import os
import sqlite3

# Asegurar importación de backend desde la raíz del proyecto
sys.path.insert(0, os.path.abspath('.'))

from backend.services.station_service import (
    get_station_measurements,
    get_all_stations,
    get_situation_overview
)
from backend import thresholds
from backend.config import DB_PATH

def verify_station_thresholds_catalog():
    """Verifica que todas las estaciones base del catálogo cumplan threshold_alert < threshold_evacuation."""
    print("--- 1. AUDITORÍA DE CATÁLOGO BASE (STATION_THRESHOLDS) ---")
    verified = 0
    for code, th in thresholds.STATION_THRESHOLDS.items():
        ale = th.get("alerta")
        eva = th.get("evacuacion")
        
        # Validar ausencia estricta de niveles sintéticos
        assert "vigilancia" not in th, f"[{code}] 'vigilancia' no oficial encontrada en STATION_THRESHOLDS"
        assert "emergencia" not in th, f"[{code}] 'emergencia' no oficial encontrada en STATION_THRESHOLDS"

        if ale is not None and eva is not None:
            assert ale < eva, f"[{code}] Umbral incoherente: Alerta ({ale}) >= Evacuación ({eva})"
            verified += 1
            
    print(f"   [OK] {verified} estaciones con umbrales base validadas con éxito (Alerta < Evacuación).")

def verify_database_thresholds_table():
    """Verifica que la tabla umbrales_config en SQLite no tenga datos invertidos ni niveles obsoletos."""
    print("\n--- 2. AUDITORÍA DE TABLA SQLITE (umbrales_config) ---")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT codigo, alerta, evacuacion FROM umbrales_config")
    rows = cursor.fetchall()
    conn.close()

    verified = 0
    for codigo, alerta, evacuacion in rows:
        if alerta is not None and evacuacion is not None:
            assert alerta < evacuacion, f"[{codigo} en DB] Alerta ({alerta}) >= Evacuación ({evacuacion})"
            verified += 1

    print(f"   [OK] {verified} registros en DB validados (Alerta < Evacuación).")

def verify_puerto_iguazu_kpis():
    """Verifica la integridad de datos y umbrales para Puerto Iguazú."""
    print("\n--- 3. VERIFICACIÓN TÉCNICA PUERTO IGUAZÚ ---")
    data = get_station_measurements(5)
    kpis = data.get('kpis', {})

    agp_alt = kpis.get('ultima_altura')
    pna_alt = kpis.get('pna_altura')
    falla = kpis.get('falla_reporte')
    umbrales = kpis.get('umbrales', {})

    print(f"   AGP última altura: {agp_alt} (Timestamp: {kpis.get('ultimo_timestamp')})")
    print(f"   PNA altura:        {pna_alt} (Timestamp: {kpis.get('pna_timestamp')})")
    print(f"   Falla de reporte:  {falla} | Tiempo: {kpis.get('tiempo_sin_reportar_str')}")
    print(f"   Umbrales:          {umbrales}")

    # Validar tipos e integridad física de Puerto Iguazú
    assert agp_alt is not None and isinstance(agp_alt, (int, float)), f"Altura AGP inválida: {agp_alt}"
    assert 0.0 < agp_alt < 60.0, f"Altura AGP fuera de rango hidrológico creíble: {agp_alt}"

    if pna_alt is not None:
        assert isinstance(pna_alt, (int, float)), f"Altura PNA inválida: {pna_alt}"
        assert 0.0 < pna_alt < 60.0, f"Altura PNA fuera de rango hidrológico creíble: {pna_alt}"

    assert isinstance(falla, bool), "falla_reporte debe ser boolean"

    # Validar umbrales oficiales en Iguazú
    assert "vigilancia" not in umbrales, "vigilancia no debe estar en umbrales"
    assert "emergencia" not in umbrales, "emergencia no debe estar en umbrales"
    assert umbrales.get('alerta') == 25.0, f"Umbral alerta esperado 25.0, obtenido {umbrales.get('alerta')}"
    assert umbrales.get('evacuacion') == 28.0, f"Umbral evacuación esperado 28.0, obtenido {umbrales.get('evacuacion')}"
    assert umbrales['alerta'] < umbrales['evacuacion'], "Alerta debe ser menor que Evacuación"
    print("   [OK] Puerto Iguazú verificado correctamente.")

def verify_all_stations_and_situation():
    """Verifica que el endpoint de todas las estaciones y situación general respeten los guardrails."""
    print("\n--- 4. VERIFICACIÓN DE SITUACIÓN Y GUARDRAILS GENERALES ---")
    stations = get_all_stations()
    assert len(stations) > 0, "No se recuperaron estaciones"
    
    for s in stations:
        th = s.get("umbrales", {})
        assert "vigilancia" not in th, f"[{s.get('codigo')}] vigilancia no permitida"
        assert "emergencia" not in th, f"[{s.get('codigo')}] emergencia no permitida"
        ale = th.get("alerta")
        eva = th.get("evacuacion")
        if ale is not None and eva is not None:
            assert ale < eva, f"[{s.get('codigo')}] Alerta ({ale}) >= Evacuación ({eva})"

    sit = get_situation_overview()
    conteo = sit.get('conteo_estados', {})
    print("   Conteo de estados oficiales:", conteo)
    assert 'vigilancia' not in conteo, "vigilancia no debe figurar en conteo de estados"
    assert 'emergencia' not in conteo, "emergencia no debe figurar en conteo de estados"
    
    valid_states = {'normal', 'alerta', 'evacuacion', 'sin_datos', 'desactivado'}
    for st_name in conteo.keys():
        assert st_name in valid_states, f"Estado hidrológico no reconocido: {st_name}"

    print("   [OK] Resumen de situación y catálogo general 100% alineados con reglas de integridad.")

if __name__ == '__main__':
    print("=========================================================")
    print("   AUDITORÍA DE INTEGRIDAD HIDROLÓGICA Y UMBRALES PNA    ")
    print("=========================================================")
    verify_station_thresholds_catalog()
    verify_database_thresholds_table()
    verify_puerto_iguazu_kpis()
    verify_all_stations_and_situation()
    print("\n--> [ÉXITO TOTAL] TODAS LAS VERIFICACIONES DE UMBRALES Y ESCALAS PASARON EN VERDE!")
