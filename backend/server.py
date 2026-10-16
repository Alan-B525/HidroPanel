"""
backend/server.py
Servidor Web Multihilo y Motor de APIs REST para HidroPanel
"""

import sys
import os
import mimetypes
import logging
import socket
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

import threading
from .config import STATIC_DIR, DEFAULT_PORT
from .database import seed_stations_catalog
from .services.sync_service import start_background_scheduler
from .services.simepar_service import start_simepar_daily_scheduler
from .services import prefectura_service
from . import routes

# Asegurar mimetypes esenciales
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/json", ".json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("hidropanel.server")


class HidroRequestHandler(SimpleHTTPRequestHandler):
    """Manejador HTTP robusto con separación de archivos estáticos y API REST."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_OPTIONS(self):
        """Pre-flight CORS."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            # Rutas de la API REST
            if path.startswith("/api/"):
                status_code, content_type, body = routes.handle_get(path, query)
                
                # Manejo de descargas CSV con cabeceras especiales
                if content_type.startswith("text/csv"):
                    filename = "export.csv"
                    if "filename=" in content_type:
                        parts = content_type.split("filename=")
                        content_type = parts[0].rstrip("; ")
                        filename = parts[1]

                    encoded = body.encode("utf-8") if isinstance(body, str) else body
                    self.send_response(status_code)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.send_header("Content-Length", str(len(encoded)))
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    self.wfile.write(encoded)
                    return

                # Manejo de imágenes (mapa SIMEPAR)
                if isinstance(body, bytes):
                    self.send_response(status_code)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                    return

                # Respuestas JSON o texto estándar
                encoded = body.encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(encoded)
                return

            # Archivos estáticos del Frontend
            return super().do_GET()

        except Exception as e:
            logger.exception(f"Error procesando GET {self.path}: {e}")
            try:
                err_body = f'{{"success": false, "error": "{str(e)}"}}'.encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(err_body)))
                self.end_headers()
                self.wfile.write(err_body)
            except Exception:
                pass

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            content_len = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_len) if content_len > 0 else b""

            status_code, content_type, body_str = routes.handle_post(path, body_bytes)
            encoded = body_str.encode("utf-8")

            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(encoded)

        except Exception as e:
            logger.exception(f"Error procesando POST {self.path}: {e}")
            try:
                err_body = f'{{"success": false, "error": "{str(e)}"}}'.encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(err_body)))
                self.end_headers()
                self.wfile.write(err_body)
            except Exception:
                pass

    def end_headers(self):
        # Política de caché inteligente para archivos estáticos
        if hasattr(self, "path") and not self.path.startswith("/api/"):
            if any(self.path.endswith(ext) for ext in [".css", ".js", ".svg", ".png", ".woff2"]):
                self.send_header("Cache-Control", "public, max-age=86400")
            elif self.path == "/" or self.path.endswith(".html"):
                self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()


class ReusableThreadingServer(ThreadingHTTPServer):
    allow_reuse_address = (sys.platform != "win32")
    daemon_threads = True


def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) != 0


def run_server(port: int = DEFAULT_PORT):
    """Inicia el servidor y los servicios en segundo plano."""
    logger.info("Verificando catálogo de estaciones...")
    seed_stations_catalog()

    logger.info("Iniciando planificador automático de telemetría...")
    start_background_scheduler()

    logger.info("Iniciando planificador diario de SIMEPAR...")
    start_simepar_daily_scheduler()

    logger.info("Iniciando sincronización oficial con Prefectura Naval Argentina...")
    t_pref = threading.Thread(target=lambda: prefectura_service.sync_prefectura_all(force_history=False), daemon=True, name="PrefecturaSyncInit")
    t_pref.start()

    # Selección de puerto disponible
    server_address = ('', port)
    try:
        httpd = ReusableThreadingServer(server_address, HidroRequestHandler)
    except OSError:
        while not is_port_available(port) and port < 8150:
            port += 1
        server_address = ('', port)
        httpd = ReusableThreadingServer(server_address, HidroRequestHandler)

    logger.info("=" * 70)
    logger.info(" HidroPanel 2.0 Servidor Profesional Activo")
    logger.info(f" Acceso Web: http://localhost:{port}")
    logger.info(f" Directorio Estáticos: {STATIC_DIR}")
    logger.info(" Sincronización programada: minutos xx:10, xx:30, xx:50")
    logger.info(" Descarga SIMEPAR: todos los días a las 07:00 AM")
    logger.info("=" * 70)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nDeteniendo servidor HidroPanel...")
        httpd.shutdown()
