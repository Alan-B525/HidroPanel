#!/usr/bin/env python3
"""
Acceso directo para ejecutar la descarga de datos de COPEL y ENGIE.
Ejecuta copel_scraper/descargar_copel.py
"""
import os
import sys

root_dir = os.path.dirname(os.path.abspath(__file__))
script_path = os.path.join(root_dir, "copel_scraper", "descargar_copel.py")

if __name__ == "__main__":
    import runpy
    sys.path.insert(0, os.path.join(root_dir, "copel_scraper"))
    runpy.run_path(script_path, run_name="__main__")
