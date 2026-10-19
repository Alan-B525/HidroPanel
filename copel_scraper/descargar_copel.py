#!/usr/bin/env python3
"""
copel_scraper/descargar_copel.py
Descarga automatizada de telemetría de COPEL MHB y ENGIE Brasil (Cuenca del Río Iguazú).
Genera archivos TXT tabulados exactos para Excel y copel_engie_dto.json con el contrato unificado.
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from copel_client import CopelClient
from engie_client import EngieClient

COPEL_ESTACIONES = [
    {"query": "Hotel cataratas", "nombre": "Hotel Cataratas", "filenames": ["Cataratas.txt"]},
    {"query": "Porto capanema", "nombre": "Porto Capanema", "filenames": ["Capanema.txt"]},
    {"query": "Baixo iguazu", "nombre": "Baixo Iguaçu", "filenames": ["Baixo Iguazú.txt", "Baixo Iguazu.txt"]},
    {"query": "Salto caixias", "nombre": "Salto Caxias", "filenames": ["Caxias.txt"]},
    {"query": "segredo", "nombre": "Segredo", "filenames": ["segredo.txt"]},
    {"query": "foz areias", "nombre": "Foz do Areia", "filenames": ["Areia.txt"]}
]

ENGIE_CENTRALES = [
    {"code": "UHSO", "nombre": "Salto Osório", "filenames": ["TRACTEBEL Salto OSORIO.txt", "OSORIO.txt"]},
    {"code": "UHSS", "nombre": "Salto Santiago", "filenames": ["TRACTEBEL Salto SANTIAGO.txt", "SANTIAGO.txt"]}
]

def parse_copel_date(dt_str):
    if not dt_str:
        return None
    s = dt_str.strip()
    m = re.match(r'^(\d{2})/(\d{2})/(\d{2,4})\s+(\d{1,2})h?$', s)
    if m:
        d, mth, y, h = m.groups()
        year = int(y)
        if year < 100:
            year += 2000
        return datetime(year, int(mth), int(d), int(h))
    return None

def escribir_archivo_txt(lineas, ruta_archivo):
    with open(ruta_archivo, 'w', encoding='utf-8', newline='\r\n') as f:
        for linea in lineas:
            f.write(linea + '\r\n')

def ejecutar_extraccion(directorio_salida=None, solo_cataratas=True):
    if not directorio_salida:
        parent_dir = os.path.dirname(current_dir) if os.path.basename(current_dir).lower() == "copel_scraper" else current_dir
        data_candidate = os.path.join(parent_dir, "data")
        directorio_salida = data_candidate if os.path.isdir(data_candidate) else parent_dir

    os.makedirs(directorio_salida, exist_ok=True)
    now = datetime.now()
    fecha_inicio = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)

    client_copel = CopelClient()
    client_engie = EngieClient()
    todos_los_dtos = []

    estaciones_a_consultar = [e for e in COPEL_ESTACIONES if any(k in e["query"].lower() for k in ["cataratas", "capanema", "segredo"])] if solo_cataratas else COPEL_ESTACIONES

    for item in estaciones_a_consultar:
        q = item["query"]
        try:
            res = client_copel.fetch_station_data(q, normalize=False)
            dtos = client_copel.fetch_station_dto(q)
            todos_los_dtos.extend(dtos)

            filtrados = []
            for r in res['records']:
                vals = list(r.values()) if isinstance(r, dict) else list(r)
                if not vals:
                    continue
                dt = parse_copel_date(vals[0])
                if dt and dt >= fecha_inicio:
                    filtrados.append((dt, "\t".join(str(v) for v in vals)))

            filtrados.sort(key=lambda x: x[0], reverse=True)
            lineas_finales = [f[1] for f in filtrados]

            for fname in item["filenames"]:
                ruta = os.path.join(directorio_salida, fname)
                escribir_archivo_txt(lineas_finales, ruta)
        except Exception as e:
            print(f"[COPEL ERROR] {item['nombre']}: {e}")

    if not solo_cataratas:
        for item in ENGIE_CENTRALES:
            code = item["code"]
            try:
                dtos = client_engie.fetch_plant_dto(code, fecha_inicio)
                todos_los_dtos.extend(dtos)
                rows = client_engie.fetch_plant_data(code, fecha_inicio)
                lineas_finales = ["\t".join(r) for r in rows]
                for fname in item["filenames"]:
                    ruta = os.path.join(directorio_salida, fname)
                    escribir_archivo_txt(lineas_finales, ruta)
            except Exception as e:
                print(f"[ENGIE ERROR] {item['nombre']}: {e}")

    # Guardar snapshot JSON con el contrato DTO unificado
    dto_json_path = os.path.join(directorio_salida, "copel_engie_dto.json")
    try:
        with open(dto_json_path, "w", encoding="utf-8") as f:
            json.dump(todos_los_dtos, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        print(f"[DTO ERROR] Guardando snapshot JSON: {ex}")

if __name__ == "__main__":
    dir_arg = None
    solo_cataratas_arg = True
    for arg in sys.argv[1:]:
        if arg == "--all":
            solo_cataratas_arg = False
        elif not arg.startswith("-"):
            dir_arg = arg
    ejecutar_extraccion(dir_arg, solo_cataratas=solo_cataratas_arg)
