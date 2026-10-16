import urllib.request
import ssl
import sqlite3
import unicodedata
import re
import sys
import os
sys.path.insert(0, os.path.abspath('.'))
from bs4 import BeautifulSoup

def norm(text):
    if not text:
        return ''
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-zA-Z0-9]', '', text).upper()

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    'https://contenidosweb.prefecturanaval.gob.ar/alturas/index.php',
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
)

with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
    soup = BeautifulSoup(resp.read(), 'html.parser')

table = soup.find('table')
rows = table.find_all('tr')
pna = {}
for r in rows[1:]:
    cols = [td.get_text(strip=True) for td in r.find_all(['td', 'th'])]
    if len(cols) >= 12:
        puerto = cols[0]
        rio = cols[1]
        alt = cols[2].replace(',', '.')
        fecha = cols[4] if len(cols) > 4 else ''
        hora = cols[5] if len(cols) > 5 else ''
        estado_rio = cols[6] if len(cols) > 6 else ''
        alerta = cols[10].replace(',', '.')
        evac = cols[11].replace(',', '.')
        
        alt_val = float(alt) if alt not in ('-', '', 'S/E') else None
        al_val = float(alerta) if alerta not in ('-', '', 'S/E') else None
        ev_val = float(evac) if evac not in ('-', '', 'S/E') else None
        
        pna[norm(puerto)] = {
            'puerto': puerto,
            'rio': rio,
            'altura': alt_val,
            'fecha': fecha,
            'hora': hora,
            'estado_rio': estado_rio,
            'alerta': al_val,
            'evacuacion': ev_val,
        }

conn = sqlite3.connect('hidrografia.db')
c = conn.cursor()
c.execute('''
    SELECT e.id, e.codigo, e.nombre, m.altura, m.timestamp
    FROM estaciones e
    LEFT JOIN (
        SELECT estacion_id, altura, timestamp
        FROM mediciones
        WHERE (estacion_id, timestamp) IN (
            SELECT estacion_id, MAX(timestamp)
            FROM mediciones
            GROUP BY estacion_id
        )
    ) m ON e.id = m.estacion_id
''')
agp_stations = c.fetchall()
conn.close()

from backend.services.prefectura_service import PNA_PORT_MAPPING

comparisons = []
for st_id, codigo, nombre, agp_alt, agp_ts in agp_stations:
    code_upper = codigo.upper().strip()
    match = None
    aliases = PNA_PORT_MAPPING.get(code_upper, []) + [nombre, code_upper]
    for a in aliases:
        na = norm(a)
        if na in pna:
            match = pna[na]
            break
    if not match:
        norm_n = norm(nombre)
        for pk, pv in pna.items():
            if pk == norm_n or (len(pk) >= 5 and pk in norm_n) or (len(norm_n) >= 5 and norm_n in pk):
                match = pv
                break

    if match:
        diff = round(agp_alt - match['altura'], 2) if (agp_alt is not None and match['altura'] is not None) else None
        comparisons.append({
            'codigo': codigo,
            'nombre': nombre,
            'puerto_pna': match['puerto'],
            'rio': rio,
            'agp_alt': agp_alt,
            'agp_ts': agp_ts,
            'pna_alt': match['altura'],
            'pna_ts': f"{match['fecha']} {match['hora']}",
            'pna_estado': match['estado_rio'],
            'diff': diff,
            'alerta': match['alerta'],
            'evac': match['evacuacion']
        })

print(f"Total estaciones comparadas: {len(comparisons)}")
print(f"{'Estacion (AGP)':<22} | {'Puerto (PNA)':<18} | {'AGP (m)':<7} | {'PNA (m)':<7} | {'Dif(AGP-PNA)':<12} | {'Alerta':<6} | {'Evac':<6} | {'Hora PNA':<12}")
print("-" * 105)
for item in comparisons:
    agp_s = f"{item['agp_alt']:6.2f}" if item['agp_alt'] is not None else "   N/D"
    pna_s = f"{item['pna_alt']:6.2f}" if item['pna_alt'] is not None else "   N/D"
    dif_s = f"{item['diff']:+6.2f} m" if item['diff'] is not None else "     N/D"
    al_s = f"{item['alerta']:5.2f}" if item['alerta'] is not None else "    -"
    ev_s = f"{item['evac']:5.2f}" if item['evac'] is not None else "    -"
    print(f"{item['nombre']:<22} | {item['puerto_pna']:<18} | {agp_s} | {pna_s} | {dif_s:<12} | {al_s} | {ev_s} | {item['pna_ts']}")
