#!/usr/bin/env python3
"""
app.py
Servidor Web Local para HidroPanel (Telemetría de Altura de Ríos)
- Sincronización automática periódica a las xx:10, xx:30, xx:50
- API REST con datos de altura redondeados a precisión real de 2 decimales
- Interfaz gráfica moderna, precisa e interactiva
"""

import sys
import os
import json
import sqlite3
import logging
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import socket

import sync_estaciones
import descargar_mapa_simepar

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("hidropanel_server")

DB_PATH = "hidrografia.db"
STATIC_DIR = os.path.join(os.path.dirname(__file__), "public")
DEFAULT_PORT = 8050

# Estado global de sincronización automática
LAST_AUTO_SYNC_TIME = None
NEXT_AUTO_SYNC_TIME = None


def seed_stations_catalog():
    """Registra o actualiza en la base de datos el catálogo limpio de estaciones con coordenadas y frecuencia."""
    sync_estaciones.init_db(DB_PATH)
    height_urls = sync_estaciones.load_height_urls()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    with conn:
        for u in height_urls:
            code = sync_estaciones.get_station_code_from_url(u)
            clean_name = sync_estaciones.get_clean_name(code)
            lat, lon = sync_estaciones.get_station_coords(code)
            freq = sync_estaciones.get_station_frequency(code)
            cursor.execute("""
                INSERT INTO estaciones (codigo, nombre, url, latitud, longitud, frecuencia_minutos, estado, ultimo_timestamp, total_registros)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDIENTE', NULL, 0)
                ON CONFLICT(codigo) DO UPDATE SET 
                    nombre = excluded.nombre,
                    latitud = coalesce(excluded.latitud, estaciones.latitud),
                    longitud = coalesce(excluded.longitud, estaciones.longitud),
                    frecuencia_minutos = coalesce(excluded.frecuencia_minutos, estaciones.frecuencia_minutos)
            """, (code, clean_name, u, lat, lon, freq))
            
    conn.close()


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def calculate_range_filter(cursor, station_id, rango):
    """Calcula la fecha de corte 'desde' según el rango seleccionado, sincronizado con la fecha global más reciente."""
    if rango == "todo":
        return None

    # Obtener fecha máxima global para que todas las estaciones compartan exactamente la misma ventana temporal
    cursor.execute("SELECT MAX(ultimo_timestamp) FROM estaciones")
    row = cursor.fetchone()
    max_ts_str = row[0] if row and row[0] else None

    if not max_ts_str:
        cursor.execute("SELECT MAX(timestamp) FROM mediciones WHERE estacion_id = ?", (station_id,))
        row = cursor.fetchone()
        max_ts_str = row[0] if row and row[0] else None

    if not max_ts_str:
        return None

    try:
        max_dt = datetime.strptime(max_ts_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    if rango == "24h":
        cutoff = max_dt - timedelta(hours=24)
    elif rango == "7d":
        cutoff = max_dt - timedelta(days=7)
    elif rango == "30d":
        cutoff = max_dt - timedelta(days=30)
    else:
        cutoff = None

    return cutoff.strftime("%Y-%m-%d %H:%M:%S") if cutoff else None


def start_background_scheduler():
    """
    Inicia un hilo en segundo plano que sincroniza con programación optimizada por frecuencia:
    - xx:10 -> TODAS las 55 estaciones (33 frecuentes + 22 horarias), al cumplirse la hora.
    - xx:30 -> SÓLO las 33 estaciones de 20 min (ahorro de 22 peticiones redundantes).
    - xx:50 -> SÓLO las 33 estaciones de 20 min (ahorro de 22 peticiones redundantes).
    """
    global LAST_AUTO_SYNC_TIME, NEXT_AUTO_SYNC_TIME

    def scheduler_loop():
        global LAST_AUTO_SYNC_TIME, NEXT_AUTO_SYNC_TIME
        logger.info("Planificador inteligente activo: xx:10 (todas), xx:30 y xx:50 (solo estaciones cada 20 min).")
        
        target_minutes = [10, 30, 50]

        while True:
            now = datetime.now()
            # Calcular el próximo minuto objetivo
            candidates = []
            for tm in target_minutes:
                target_dt = now.replace(minute=tm, second=0, microsecond=0)
                if target_dt <= now:
                    target_dt += timedelta(hours=1)
                candidates.append((target_dt, tm))
                
            next_sync_time, scheduled_min = min(candidates, key=lambda x: x[0])
            NEXT_AUTO_SYNC_TIME = next_sync_time.strftime("%H:%M:%S")
            sleep_seconds = max(1, (next_sync_time - now).total_seconds())

            tipo_desc = "COMPLETA (todas las 55 estaciones)" if scheduled_min == 10 else "RÁPIDA (solo 33 estaciones de 20 min)"
            logger.info(f"[AUTO-SYNC] Próxima actualización: {NEXT_AUTO_SYNC_TIME} (en {int(sleep_seconds)} s) [{tipo_desc}]")
            time.sleep(sleep_seconds)

            # Ejecutar sincronización
            try:
                exec_time = datetime.now().strftime("%H:%M:%S")
                if scheduled_min == 10:
                    logger.info(f"[AUTO-SYNC] Sincronización COMPLETA (horarias + 20 min) a las {exec_time}...")
                    urls = sync_estaciones.load_height_urls()
                else:
                    logger.info(f"[AUTO-SYNC] Sincronización RÁPIDA (solo 20 min) a las {exec_time}...")
                    urls = sync_estaciones.load_height_urls(frequency=20)

                results = sync_estaciones.run_sync(urls, db_path=DB_PATH, workers=6)
                total_new = sum(r.get("new_records", 0) for r in results if r.get("status") == "OK")
                LAST_AUTO_SYNC_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"[AUTO-SYNC] Sincronización ({len(urls)} estaciones) finalizada: +{total_new} registros nuevos.")
            except Exception as e:
                logger.error(f"[AUTO-SYNC] Error en sincronización programada: {e}")

            time.sleep(3)

    t = threading.Thread(target=scheduler_loop, daemon=True, name="AutoSyncScheduler")
    t.start()


def start_simepar_daily_scheduler():
    """Hilo en segundo plano que descarga el mapa SIMEPAR todos los días a las 07:00 AM (mapa del día anterior)."""
    def scheduler_loop():
        logger.info("Planificador diario de SIMEPAR activo: descarga programada todos los días a las 07:00 AM.")
        while True:
            now = datetime.now()
            # El mapa 'ontem' de SIMEPAR corresponde a las lluvias del día anterior
            yesterday = (now - timedelta(days=1)).date()
            yesterday_str = yesterday.strftime("%Y-%m-%d")
            yesterday_file = os.path.join(descargar_mapa_simepar.OUTPUT_DIR, f"{yesterday_str}.png")

            # Si hoy ya pasaron las 07:00 y el mapa de ayer aún no se ha descargado, descargarlo ahora
            if now.hour >= 7 and not os.path.exists(yesterday_file):
                try:
                    logger.info(f"[SIMEPAR] Descargando mapa de precipitación para la fecha de ayer ({yesterday_str})...")
                    descargar_mapa_simepar.download_simepar_map(yesterday)
                except Exception as e:
                    logger.error(f"[SIMEPAR] Error descargando mapa de ayer: {e}")

            # Calcular la próxima ejecución a las 07:00:00 AM
            target_7am = now.replace(hour=7, minute=0, second=0, microsecond=0)
            if target_7am <= now:
                target_7am += timedelta(days=1)

            wait_seconds = max(5, (target_7am - datetime.now()).total_seconds())
            logger.info(f"[SIMEPAR] Próxima descarga de mapa: {target_7am.strftime('%Y-%m-%d %H:%M:%S')} (en {int(wait_seconds)} s)")
            time.sleep(wait_seconds)

            try:
                target_date = (datetime.now() - timedelta(days=1)).date()
                logger.info(f"[SIMEPAR] Ejecutando descarga programada diaria de las 07:00 AM (mapa de ayer {target_date})...")
                descargar_mapa_simepar.download_simepar_map(target_date)
            except Exception as e:
                logger.error(f"[SIMEPAR] Error en descarga de las 07:00 AM: {e}")

            time.sleep(120)

    t = threading.Thread(target=scheduler_loop, daemon=True, name="SimeparScheduler")
    t.start()


class HidroHandler(SimpleHTTPRequestHandler):
    """Manejador HTTP para la API REST y los archivos estáticos."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/" or path == "/index.html":
                return super().do_GET()

            elif path == "/api/estaciones":
                self.handle_get_estaciones()

            elif path == "/api/mediciones":
                self.handle_get_mediciones(query)

            elif path == "/api/status_sync":
                self.handle_get_status_sync()

            elif path == "/api/export":
                self.handle_export_csv(query)

            elif path == "/api/mapa_simepar" or path.startswith("/api/mapa_simepar/"):
                self.handle_get_mapa_simepar(path)

            else:
                return super().do_GET()
        except Exception as e:
            logger.exception(f"Error en GET {getattr(self, 'path', '')}: {e}")
            try:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            except Exception:
                pass

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/sync":
                self.handle_post_sync()
            elif path == "/api/sync_mapa_simepar":
                self.handle_post_sync_mapa_simepar()
            else:
                self.send_error(404, "Endpoint no encontrado")
        except Exception as e:
            logger.exception(f"Error en POST {getattr(self, 'path', '')}: {e}")
            try:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            except Exception:
                pass

    def handle_get_estaciones(self):
        """Devuelve el listado de estaciones con nombres limpios y última altura."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                e.id, 
                e.codigo, 
                e.nombre, 
                e.latitud,
                e.longitud,
                e.frecuencia_minutos,
                e.ultimo_timestamp, 
                e.total_registros, 
                m.altura as ultima_altura
            FROM estaciones e
            LEFT JOIN mediciones m ON m.estacion_id = e.id AND m.timestamp = e.ultimo_timestamp
            ORDER BY e.nombre COLLATE NOCASE ASC
        """)
        
        rows = []
        for r in cursor.fetchall():
            d = dict(r)
            if d.get("ultima_altura") is not None:
                d["ultima_altura"] = round(d["ultima_altura"], 2)
            rows.append(d)
        conn.close()

        self.send_json_response({"success": True, "estaciones": rows})

    def handle_get_mediciones(self, query):
        """Devuelve las mediciones de una estación con redondeo consistente."""
        station_id_str = query.get("estacion_id", [None])[0]
        rango = query.get("rango", ["24h"])[0]

        if not station_id_str:
            self.send_json_response({"success": False, "error": "Falta parámetro estacion_id"}, 400)
            return

        try:
            station_id = int(station_id_str)
        except ValueError:
            self.send_json_response({"success": False, "error": "ID de estación inválido"}, 400)
            return

        conn = get_db_connection()
        cursor = conn.cursor()

        # Datos de estación
        cursor.execute("SELECT id, codigo, nombre, latitud, longitud, frecuencia_minutos, ultimo_timestamp FROM estaciones WHERE id = ?", (station_id,))
        station_row = cursor.fetchone()
        if not station_row:
            conn.close()
            self.send_json_response({"success": False, "error": "Estación no encontrada"}, 404)
            return

        station_info = dict(station_row)

        # Filtro de fecha
        cutoff_date = calculate_range_filter(cursor, station_id, rango)
        where_clause = "WHERE estacion_id = ?"
        params = [station_id]
        if cutoff_date:
            where_clause += " AND timestamp >= ?"
            params.append(cutoff_date)

        cursor.execute(f"SELECT COUNT(*) FROM mediciones {where_clause}", params)
        total_in_range = cursor.fetchone()[0]

        # Lectura de puntos completos (sin truncamiento agresivo)
        puntos = []
        if total_in_range > 0:
            cursor.execute(f"""
                SELECT timestamp, altura 
                FROM mediciones 
                {where_clause} 
                ORDER BY timestamp ASC
            """, params)
            raw_rows = cursor.fetchall()

            # Preservar datos completos:
            # En rangos estándar (24h, 7d, 30d) o conjuntos de hasta 35.000 puntos se entrega el 100% íntegro.
            # En 'todo' masivo (>35.000 registros), se conserva una muestra de 30.000 puntos de ultra alta fidelidad.
            if len(raw_rows) > 35000:
                step = max(1, len(raw_rows) // 30000)
                selected_rows = raw_rows[::step]
                if selected_rows[-1] != raw_rows[-1]:
                    selected_rows.append(raw_rows[-1])
            else:
                selected_rows = raw_rows

            puntos = [{"t": row["timestamp"], "y": round(row["altura"], 2)} for row in selected_rows]

        # KPIs
        cursor.execute(f"""
            SELECT 
                MAX(altura) as max_alt, 
                MIN(altura) as min_alt, 
                AVG(altura) as avg_alt
            FROM mediciones 
            {where_clause}
        """, params)
        stats_row = cursor.fetchone()
        max_alt = round(stats_row["max_alt"], 2) if stats_row["max_alt"] is not None else None
        min_alt = round(stats_row["min_alt"], 2) if stats_row["min_alt"] is not None else None
        avg_alt = round(stats_row["avg_alt"], 2) if stats_row["avg_alt"] is not None else None

        # Tendencia con 2 últimas lecturas
        cursor.execute("""
            SELECT altura, timestamp 
            FROM mediciones 
            WHERE estacion_id = ? 
            ORDER BY timestamp DESC 
            LIMIT 4
        """, (station_id,))
        last_readings = cursor.fetchall()
        
        ultima_altura = round(last_readings[0]["altura"], 2) if len(last_readings) > 0 else None
        ultimo_ts = last_readings[0]["timestamp"] if len(last_readings) > 0 else None
        
        tendencia = "estable"
        if len(last_readings) >= 2:
            diff = round(last_readings[0]["altura"] - last_readings[1]["altura"], 2)
            if diff >= 0.02:
                tendencia = "sube"
            elif diff <= -0.02:
                tendencia = "baja"

        # Estimar intervalo de frecuencia de muestreo de la estación
        intervalo_minutos = station_info.get("frecuencia_minutos") or 20
        if len(last_readings) >= 2:
            try:
                t1 = datetime.strptime(last_readings[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
                t2 = datetime.strptime(last_readings[1]["timestamp"], "%Y-%m-%d %H:%M:%S")
                diff_m = round(abs((t1 - t2).total_seconds()) / 60)
                if 1 <= diff_m <= 1440:
                    intervalo_minutos = diff_m
            except Exception:
                pass

        # Últimas 15 mediciones para tabla
        cursor.execute("""
            SELECT timestamp, altura 
            FROM mediciones 
            WHERE estacion_id = ? 
            ORDER BY timestamp DESC 
            LIMIT 15
        """, (station_id,))
        recientes = [{"timestamp": r["timestamp"], "altura": round(r["altura"], 2)} for r in cursor.fetchall()]

        conn.close()

        self.send_json_response({
            "success": True,
            "estacion": station_info,
            "kpis": {
                "ultima_altura": ultima_altura,
                "ultimo_timestamp": ultimo_ts,
                "tendencia": tendencia,
                "max_altura": max_alt,
                "min_altura": min_alt,
                "promedio_altura": avg_alt,
                "total_puntos": len(puntos),
                "intervalo_minutos": intervalo_minutos,
                "frecuencia_minutos": station_info.get("frecuencia_minutos", 20)
            },
            "puntos": puntos,
            "recientes": recientes
        })

    def handle_get_status_sync(self):
        """Devuelve el estado del programador de sincronización automática."""
        global LAST_AUTO_SYNC_TIME, NEXT_AUTO_SYNC_TIME
        self.send_json_response({
            "success": True,
            "last_auto_sync": LAST_AUTO_SYNC_TIME,
            "next_auto_sync": NEXT_AUTO_SYNC_TIME
        })

    def handle_post_sync(self):
        """Ejecuta sincronización invocada desde el botón Actualizar."""
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        conn = get_db_connection()
        cursor = conn.cursor()

        if data.get("all"):
            freq_filter = data.get("frequency")
            if freq_filter:
                cursor.execute("SELECT url, codigo FROM estaciones WHERE frecuencia_minutos = ?", (freq_filter,))
            else:
                cursor.execute("SELECT url, codigo FROM estaciones")
            urls = [r["url"] for r in cursor.fetchall()]
            conn.close()

            logger.info(f"Sincronizando {len(urls)} estaciones desde la web...")
            results = sync_estaciones.run_sync(urls, db_path=DB_PATH, workers=6)
            total_new = sum(r.get("new_records", 0) for r in results if r.get("status") == "OK")

            self.send_json_response({
                "success": True,
                "total_new_records": total_new,
                "results": results
            })

        elif "estacion_id" in data:
            st_id = data["estacion_id"]
            cursor.execute("SELECT url, codigo, nombre FROM estaciones WHERE id = ?", (st_id,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                self.send_json_response({"success": False, "error": "Estación no encontrada"}, 404)
                return

            logger.info(f"Sincronizando estación {row['nombre']} ({row['codigo']}) desde la web...")
            res = sync_estaciones.sync_station({"url": row["url"], "code": row["codigo"]}, db_path=DB_PATH)

            self.send_json_response({
                "success": res.get("status") == "OK",
                "results": [res],
                "error": res.get("error")
            })
        else:
            conn.close()
            self.send_json_response({"success": False, "error": "Parámetro inválido"}, 400)

    def handle_export_csv(self, query):
        """Descarga de CSV con registros de la estación."""
        station_id_str = query.get("estacion_id", [None])[0]
        rango = query.get("rango", ["todo"])[0]

        if not station_id_str:
            self.send_error(400, "Falta estacion_id")
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT codigo, nombre FROM estaciones WHERE id = ?", (int(station_id_str),))
        row = cursor.fetchone()
        if not row:
            conn.close()
            self.send_error(404, "Estación no encontrada")
            return

        filename_base = row["codigo"]
        cutoff = calculate_range_filter(cursor, int(station_id_str), rango)
        
        where = "WHERE estacion_id = ?"
        params = [int(station_id_str)]
        if cutoff:
            where += " AND timestamp >= ?"
            params.append(cutoff)

        cursor.execute(f"SELECT timestamp, altura FROM mediciones {where} ORDER BY timestamp ASC", params)
        rows = cursor.fetchall()
        conn.close()

        is_cota = query.get("cota", ["0"])[0] == "1"
        try:
            offset = float(query.get("offset", ["0.0"])[0])
        except Exception:
            offset = 0.0

        if is_cota:
            csv_content = "fecha_hora,cota\n"
            for r in rows:
                val = round(r['altura'] + offset, 2)
                csv_content += f"{r['timestamp']},{val:.2f}\n"
            filename = f"{filename_base}_cota_{rango}_{datetime.now().strftime('%Y%m%d')}.csv"
        else:
            csv_content = "fecha_hora,altura_metros\n"
            for r in rows:
                csv_content += f"{r['timestamp']},{round(r['altura'], 2):.2f}\n"
            filename = f"{filename_base}_{rango}_{datetime.now().strftime('%Y%m%d')}.csv"

        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", str(len(csv_content.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(csv_content.encode("utf-8"))

    def handle_get_mapa_simepar(self, path):
        """Maneja la lista de mapas o entrega la imagen solicitada."""
        output_dir = descargar_mapa_simepar.OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)

        if path == "/api/mapa_simepar":
            archivos = [f for f in os.listdir(output_dir) if f.endswith(".png")]
            fechas = sorted([f[:-4] for f in archivos], reverse=True)
            ultima = fechas[0] if fechas else None
            self.send_json_response({
                "success": True,
                "fechas": fechas,
                "ultima_fecha": ultima,
                "url": f"/api/mapa_simepar/{ultima}.png" if ultima else None
            })
        else:
            filename = os.path.basename(path)
            if not filename.endswith(".png"):
                filename += ".png"
            file_path = os.path.join(output_dir, filename)

            if not os.path.exists(file_path):
                # Fallback al mapa más reciente si el solicitado no existe
                archivos = sorted([f for f in os.listdir(output_dir) if f.endswith(".png")], reverse=True)
                if archivos:
                    file_path = os.path.join(output_dir, archivos[0])
                else:
                    self.send_error(404, "No hay mapas de SIMEPAR disponibles")
                    return

            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_error(500, f"Error leyendo archivo de mapa: {e}")

    def handle_post_sync_mapa_simepar(self):
        """Descarga bajo demanda el mapa actual de SIMEPAR."""
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            if content_len > 0:
                self.rfile.read(content_len)

            logger.info("Descargando mapa SIMEPAR bajo demanda desde API...")
            filepath = descargar_mapa_simepar.download_simepar_map()
            if filepath:
                filename = os.path.basename(filepath)
                fecha = filename[:-4]
                self.send_json_response({
                    "success": True,
                    "fecha": fecha,
                    "filename": filename,
                    "url": f"/api/mapa_simepar/{filename}"
                })
            else:
                self.send_json_response({"success": False, "error": "Fallo al descargar imagen de SIMEPAR"}, 500)
        except Exception as e:
            self.send_json_response({"success": False, "error": str(e)}, 500)

    def send_json_response(self, data, status_code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


class ReusableThreadingServer(ThreadingHTTPServer):
    allow_reuse_address = True


def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) != 0


def run_server(port: int = DEFAULT_PORT):
    seed_stations_catalog()
    
    # Iniciar programador automático de fondo (xx:10, xx:30, xx:50)
    start_background_scheduler()

    # Iniciar programador diario de SIMEPAR (07:00 AM)
    start_simepar_daily_scheduler()

    server_address = ('', port)
    try:
        httpd = ReusableThreadingServer(server_address, HidroHandler)
    except OSError:
        while not is_port_available(port) and port < 8100:
            port += 1
        server_address = ('', port)
        httpd = ReusableThreadingServer(server_address, HidroHandler)

    logger.info("=" * 70)
    logger.info(f" HidroPanel activo exitosamente!")
    logger.info(f" Acceso local: http://localhost:{port}")
    logger.info(f" Base de datos: {os.path.abspath(DB_PATH)}")
    logger.info(f" Sincronización automática: a las xx:10, xx:30, xx:50")
    logger.info(" Presione Ctrl+C en la consola para detener el servidor.")
    logger.info("=" * 70)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nDeteniendo servidor...")
        httpd.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else DEFAULT_PORT
    run_server(port)
