from backend.services.station_service import get_station_measurements, get_all_stations, get_situation_overview
from backend import thresholds

# 1. Puerto Iguazu
data = get_station_measurements(5)
kpis = data['kpis']
print('1. PUERTO IGUAZU KPIS:')
print(f"   AGP ultima_altura: {kpis['ultima_altura']} (Timestamp: {kpis['ultimo_timestamp']})")
print(f"   PNA pna_altura: {kpis['pna_altura']} (Timestamp: {kpis['pna_timestamp']})")
print(f"   falla_reporte: {kpis['falla_reporte']} | tiempo_sin_reportar: {kpis['tiempo_sin_reportar_str']}")
print(f"   umbrales: {kpis['umbrales']}")

assert kpis['ultima_altura'] == 26.6, f"Expected 26.6, got {kpis['ultima_altura']}"
assert kpis['pna_altura'] == 33.0, f"Expected 33.0, got {kpis['pna_altura']}"
assert kpis['falla_reporte'] is True, "Expected falla_reporte to be True"
assert 'vigilancia' not in kpis['umbrales'], "vigilancia should not be in umbrales"
assert 'emergencia' not in kpis['umbrales'], "emergencia should not be in umbrales"

# 2. get_all_stations
stations = get_all_stations()
ig = [s for s in stations if s['id'] == 5][0]
print('2. ALL_STATIONS IGUAZU:')
print(f"   ultima_altura: {ig['ultima_altura']} | falla_reporte: {ig['falla_reporte']}")
assert ig['ultima_altura'] == 26.6
assert ig['falla_reporte'] is True

# 3. get_situation_overview
sit = get_situation_overview()
print('3. CONTEO ESTADOS:', sit['conteo_estados'])
assert 'vigilancia' not in sit['conteo_estados']
assert 'emergencia' not in sit['conteo_estados']
failed_ids = [f['id'] for f in sit['estaciones_falla_reporte']]
assert 5 in failed_ids, "Puerto Iguazu should be listed in estaciones_falla_reporte"
print('   Puerto Iguazu correctly present in estaciones_falla_reporte!')

print('--> ALL TARGETED VERIFICATIONS PASSED!')
