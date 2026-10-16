import requests

tests = [
    ('/', 200),
    ('/api/estaciones', 200),
    ('/api/situacion', 200),
    ('/api/caudales', 200),
    ('/api/status_sync', 200),
    ('/api/mapa_simepar', 200),
    ('/api/umbrales', 200),
    ('/api/mediciones?estacion_id=1&rango=24h', 200),
]

all_passed = True
print("--- TEST DE ENDPOINTS DEL SERVIDOR ---")
for path, expected_code in tests:
    url = f'http://127.0.0.1:8050{path}'
    try:
        resp = requests.get(url, timeout=10)
        passed = (resp.status_code == expected_code)
        if not passed:
            all_passed = False
        print(f"[GET] {path:<40} -> Status {resp.status_code} (OK={passed}), Type: {resp.headers.get('Content-Type')}, Bytes: {len(resp.content)}")
    except Exception as e:
        all_passed = False
        print(f"[GET] {path:<40} -> Error: {e}")

if all_passed:
    print("\n[OK] TODOS LOS ENDPOINTS FUNCIONAN CORRECTAMENTE!")
else:
    print("\n[ERROR] ALGUNOS ENDPOINTS FALLARON.")
