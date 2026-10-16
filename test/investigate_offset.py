import urllib.request
import ssl
import sqlite3
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

STATIONS_TO_INVESTIGATE = [
    ("POSADAS", "80", "Posadas"),
    ("ITUZAINGO", "90", "Ituzaingó"),
    ("CORRIENTES", "130", "Corrientes"),
    ("BARRANQUERAS", "140", "Barranqueras"),
    ("BELLAVISTA", "170", "Bella Vista"),
    ("GOYA", "190", "Goya"),
    ("SANTAFE", "240", "Santa Fe"),
    ("PARANA", "250", "Paraná"),
    ("ROSARIO", "280", "Rosario"),
    ("VILLA_CONSTITUCION", "300", "Villa Constitución"),
    ("SAN_NICOLAS", "310", "San Nicolás"),
    ("SAN_PEDRO", "320", "San Pedro"),
    ("BARADERO_LEVEL", "330", "Baradero"),
    ("ZARATE", "340", "Zárate"),
    ("PUERTO_IGUAZU", "20", "Puerto Iguazú"),
    ("EL_DORADO", "40", "El Dorado"),
    ("PUERTO_LIBERTAD", "30", "Puerto Libertad")
]

conn = sqlite3.connect("hidrografia.db")

def parse_pna_history(port_id):
    url = f"https://contenidosweb.prefecturanaval.gob.ar/alturas/?page=historico&tiempo=7&id={port_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
            soup = BeautifulSoup(resp.read(), "html.parser")
    except Exception as e:
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
            m = re.match(r"(\d{4}-\d{2}-\d{2})\s*(\d{2}:\d{2})", raw_dt)
            if m:
                dt_str = f"{m.group(1)} {m.group(2)}:00"
                try:
                    val = float(raw_val)
                    records.append((dt_str, val))
                except ValueError:
                    pass
    return records

results = []

for code, pna_id, name in STATIONS_TO_INVESTIGATE:
    pna_records = parse_pna_history(pna_id)
    if not pna_records:
        continue

    cur = conn.cursor()
    cur.execute("SELECT id FROM estaciones WHERE codigo = ?", (code,))
    row = cur.fetchone()
    if not row:
        continue
    st_id = row[0]

    diffs = []
    pairs = []

    for p_dt, p_val in pna_records:
        target_dt = datetime.strptime(p_dt, "%Y-%m-%d %H:%M:%S")
        min_dt = (target_dt - timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S")
        max_dt = (target_dt + timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("""
            SELECT altura, timestamp, ABS(strftime('%s', timestamp) - strftime('%s', ?)) as delta_sec
            FROM mediciones
            WHERE estacion_id = ? AND timestamp BETWEEN ? AND ? AND altura BETWEEN -5 AND 50
            ORDER BY delta_sec ASC
            LIMIT 1
        """, (p_dt, st_id, min_dt, max_dt))
        agp_row = cur.fetchone()

        if agp_row:
            agp_val, agp_dt, delta_s = agp_row
            diff = round(agp_val - p_val, 3)
            # Descartar saltos extremos por pérdida de sensor
            if abs(diff) < 20:
                diffs.append(diff)
                pairs.append((p_dt, p_val, agp_val, diff))

    if diffs:
        mean_diff = sum(diffs) / len(diffs)
        variance = sum((d - mean_diff) ** 2 for d in diffs) / len(diffs)
        std_dev = variance ** 0.5
        min_d = min(diffs)
        max_d = max(diffs)
        results.append({
            "code": code,
            "name": name,
            "pna_id": pna_id,
            "count": len(diffs),
            "mean": mean_diff,
            "std": std_dev,
            "min": min_d,
            "max": max_d,
            "sample_pna": pairs[0][1],
            "sample_agp": pairs[0][2],
            "sample_diff": pairs[0][3]
        })

conn.close()

print(f"{'Estación':<20} | {'PNA ID':<6} | {'Muestras':<8} | {'Media Dif (m)':<13} | {'StdDev (m)':<10} | {'Mín / Máx (m)':<16} | {'Diagnóstico':<25}")
print("=" * 115)
for r in results:
    if r["std"] < 0.08 and abs(r["mean"]) < 0.10:
        diag = "IDENTICA (Mismo cero)"
    elif r["std"] < 0.12 and abs(r["mean"]) >= 0.10:
        diag = f"OFFSET FIJO ({r['mean']:+.2f} m)"
    elif abs(r["mean"]) > 2.0:
        diag = f"ESCALA DISTINTA ({r['mean']:+.2f} m)"
    else:
        diag = "DESVIACION VARIABLE"

    print(f"{r['name']:<20} | {r['pna_id']:<6} | {r['count']:<8} | {r['mean']:+12.3f} | {r['std']:9.3f} | [{r['min']:+5.2f}, {r['max']:+5.2f}] | {diag:<25}")
