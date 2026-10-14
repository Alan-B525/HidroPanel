import urllib.request
import ssl
import csv
import io
import time
from urllib.parse import unquote

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

with open('url_stations.txt', 'r', encoding='utf-8') as f:
    urls = [line.strip() for line in f if line.strip() and not any(k in line.lower() for k in ['viento', 'visibilidad'])]

print(f'Probing {len(urls)} URLs...')

results = []
column_variants = {}

for i, url in enumerate(urls, 1):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
            raw = resp.read(2048).decode('utf-8', errors='replace')
            lines = raw.splitlines()
            if len(lines) >= 2:
                reader = csv.reader(lines)
                row0 = next(reader, [])
                row1 = next(reader, [])
                row2 = next(reader, []) if len(lines) > 2 else []
                row3 = next(reader, []) if len(lines) > 3 else []
                row4 = next(reader, []) if len(lines) > 4 else []
                cols_tuple = tuple(row1)
                column_variants.setdefault(cols_tuple, []).append(url)
                results.append({
                    'index': i,
                    'url': url,
                    'status': 'OK',
                    'header_type': row0[0] if row0 else 'EMPTY',
                    'station': row0[1] if len(row0) > 1 else '',
                    'table_name': row0[7] if len(row0) > 7 else '',
                    'columns': row1,
                    'sample_data': row4
                })
            else:
                results.append({'index': i, 'url': url, 'status': f'Too short ({len(lines)} lines)'})
    except Exception as e:
        results.append({'index': i, 'url': url, 'status': f'ERROR: {e}'})

print(f'\nTotal probed: {len(results)}')
ok_count = sum(1 for r in results if r.get('status') == 'OK')
print(f'Successful: {ok_count}/{len(urls)}')

print('\n--- Column Variants Found ---')
for cols, url_list in column_variants.items():
    print(f'\nColumns ({len(cols)} cols): {list(cols)}')
    print(f'Found in {len(url_list)} stations, e.g.: {url_list[0]}')

print('\n--- Errors/Issues ---')
for r in results:
    if r.get('status') != 'OK':
        print(f"[{r['index']}] {r['url']} -> {r['status']}")

print('\n--- All Stations Details ---')
for r in results:
    if r.get('status') == 'OK':
        print(f"[{r['index']:2d}] Station: '{r['station']}' | Table: '{r['table_name']}' | Cols: {r['columns'][:5]} | Sample: {r['sample_data'][:5]}")
