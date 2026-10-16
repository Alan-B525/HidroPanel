#!/usr/bin/env python3
"""
app.py
Punto de entrada principal para HidroPanel
Inicia el servidor backend modularizado con soporte multihilo, APIs REST y tareas en segundo plano.
"""

import sys
from backend.server import run_server
from backend.config import DEFAULT_PORT

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else DEFAULT_PORT
    run_server(port)
