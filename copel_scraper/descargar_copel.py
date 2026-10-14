#!/usr/bin/env python3
"""
descargar_copel_excel.py
Descarga automatizada de telemetría hidrológica de COPEL MHB y ENGIE Brasil (Cuenca del Río Iguazú).
Genera los archivos TXT tabulados exactos para alimentar las macros de Excel:
- Cataratas.txt
- Capanema.txt
- Baixo Iguazú.txt (y Baixo Iguazu.txt)
- Caxias.txt
- segredo.txt
- Areia.txt
- TRACTEBEL Salto OSORIO.txt (y OSORIO.txt)
- TRACTEBEL Salto SANTIAGO.txt (y SANTIAGO.txt)

Regla de fechas:
- Desde 2 días atrás a las 00:00 hs hasta el último dato actual disponible.
- Orden cronológico inverso (dato más reciente al principio).
- Formato: Separado por tabulaciones (\\t), sin encabezados, salto de línea CRLF.
- Guarda los archivos en la misma carpeta donde reside el script / ejecutable.
"""

import os
import sys
import re
from datetime import datetime, timedelta

# Configuración de salida segura para consola Windows
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

# 6 Estaciones provistas por COPEL
COPEL_ESTACIONES = [
    {
        "query": "Hotel cataratas",
        "nombre": "Hotel Cataratas",
        "filenames": ["Cataratas.txt"]
    },
    {
        "query": "Porto capanema",
        "nombre": "Porto Capanema",
        "filenames": ["Capanema.txt"]
    },
    {
        "query": "Baixo iguazu",
        "nombre": "Baixo Iguaçu",
        "filenames": ["Baixo Iguazú.txt", "Baixo Iguazu.txt"]
    },
    {
        "query": "Salto caixias",
        "nombre": "Salto Caxias",
        "filenames": ["Caxias.txt"]
    },
    {
        "query": "segredo",
        "nombre": "Segredo",
        "filenames": ["segredo.txt"]
    },
    {
        "query": "foz areias",
        "nombre": "Foz do Areia",
        "filenames": ["Areia.txt"]
    }
]

# 2 Centrales provistas por ENGIE
ENGIE_CENTRALES = [
    {
        "code": "UHSO",
        "nombre": "Salto Osório",
        "filenames": ["TRACTEBEL Salto OSORIO.txt", "OSORIO.txt"]
    },
    {
        "code": "UHSS",
        "nombre": "Salto Santiago",
        "filenames": ["TRACTEBEL Salto SANTIAGO.txt", "SANTIAGO.txt"]
    }
]

def parse_copel_date(dt_str):
    """Parsea fecha en formato '09/10/26 08h' o '09/10/2026 08:00'."""
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
    """Escribe un archivo de texto con codificación UTF-8 y saltos CRLF."""
    with open(ruta_archivo, 'w', encoding='utf-8', newline='\r\n') as f:
        for linea in lineas:
            f.write(linea + '\r\n')

def ejecutar_extraccion(directorio_salida=None):
    if not directorio_salida:
        if getattr(sys, 'frozen', False):
            directorio_salida = os.path.dirname(sys.executable)
        else:
            # Si corre desde copel_scraper, guardar en la carpeta padre (raíz del proyecto)
            # o en la misma carpeta si está en la raíz
            parent_dir = os.path.dirname(current_dir)
            if os.path.basename(current_dir).lower() == "copel_scraper":
                directorio_salida = parent_dir
            else:
                directorio_salida = current_dir

    os.makedirs(directorio_salida, exist_ok=True)

    print("=" * 80)
    print(" EXTRACCIÓN DE TELEMETRÍA HIDROLÓGICA (COPEL MHB + ENGIE)")
    print(" Generación de archivos TXT para macro Excel")
    print("=" * 80)

    now = datetime.now()
    # Regla: dos días hacia atrás desde las 00 horas
    fecha_inicio = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"Hora de consulta:       {now.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Rango de datos a traer: Desde {fecha_inicio.strftime('%d/%m/%Y 00:00:00')} hasta el dato actual")
    print(f"Carpeta de salida:      {directorio_salida}\n")

    resumen = []

    # -------------------------------------------------------------
    # 1. CONSULTAR ESTACIONES DE COPEL
    # -------------------------------------------------------------
    print("[1/2] Consultando portal COPEL MHB...")
    client_copel = CopelClient()

    for item in COPEL_ESTACIONES:
        q = item["query"]
        nombre = item["nombre"]
        print(f"  -> {nombre:<18} ...", end=" ", flush=True)

        try:
            res = client_copel.fetch_station_data(q, normalize=False)
            raw_records = res['records']

            # Filtrar registros >= fecha_inicio
            filtrados = []
            for r in raw_records:
                vals = list(r.values()) if isinstance(r, dict) else list(r)
                if not vals:
                    continue
                dt_str = vals[0]
                dt = parse_copel_date(dt_str)
                if dt and dt >= fecha_inicio:
                    linea_txt = "\t".join(str(v) for v in vals)
                    filtrados.append((dt, linea_txt))

            # Orden cronológico inverso (más reciente arriba)
            filtrados.sort(key=lambda x: x[0], reverse=True)
            lineas_finales = [f[1] for f in filtrados]

            # Guardar en todos los nombres configurados
            for fname in item["filenames"]:
                ruta = os.path.join(directorio_salida, fname)
                escribir_archivo_txt(lineas_finales, ruta)

            n_regs = len(lineas_finales)
            print(f"[OK] {n_regs} registros -> {', '.join(item['filenames'])}")

            resumen.append({
                "fuente": "COPEL",
                "nombre": nombre,
                "archivos": ", ".join(item["filenames"]),
                "registros": n_regs,
                "ultima": filtrados[0][1].split('\t')[0] if filtrados else "N/A"
            })

        except Exception as e:
            print(f"[ERROR] {e}")

    # -------------------------------------------------------------
    # 2. CONSULTAR CENTRALES DE ENGIE (Salto Osório y Salto Santiago)
    # -------------------------------------------------------------
    print("\n[2/2] Consultando portal ENGIE Brasil...")
    client_engie = EngieClient()

    for item in ENGIE_CENTRALES:
        code = item["code"]
        nombre = item["nombre"]
        print(f"  -> {nombre:<18} ({code}) ...", end=" ", flush=True)

        try:
            rows = client_engie.fetch_plant_data(code, fecha_inicio)
            lineas_finales = ["\t".join(r) for r in rows]

            for fname in item["filenames"]:
                ruta = os.path.join(directorio_salida, fname)
                escribir_archivo_txt(lineas_finales, ruta)

            n_regs = len(lineas_finales)
            print(f"[OK] {n_regs} registros -> {', '.join(item['filenames'])}")

            resumen.append({
                "fuente": "ENGIE",
                "nombre": nombre,
                "archivos": ", ".join(item["filenames"]),
                "registros": n_regs,
                "ultima": rows[0][0] if rows else "N/A"
            })

        except Exception as e:
            print(f"[ERROR] {e}")

    # -------------------------------------------------------------
    # RESUMEN EN PANTALLA
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f" RESUMEN DE ARCHIVOS TXT GENERADOS (Al {now.strftime('%d/%m/%Y %H:%M')})")
    print("=" * 80)
    print(f"{'Fuente':<7} | {'Estación / Central':<18} | {'Archivos TXT':<32} | {'Filas':<5} | {'Último Dato'}")
    print("-" * 80)
    for r in resumen:
        print(f"{r['fuente']:<7} | {r['nombre']:<18} | {r['archivos']:<32} | {r['registros']:<5} | {r['ultima']}")
    print("=" * 80)
    print(f"Proceso completado. Archivos actualizados en:")
    print(f"👉 {directorio_salida}\n")

if __name__ == "__main__":
    dir_arg = None
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        dir_arg = sys.argv[1]
    ejecutar_extraccion(dir_arg)
