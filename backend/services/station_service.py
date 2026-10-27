"""
backend/services/station_service.py
Lógica de negocio para procesamiento hidrológico, KPIs y contrato DTO unificado.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from ..database import get_db, calculate_range_cutoff
from ..thresholds import get_station_thresholds, calculate_station_status

logger = logging.getLogger("hidropanel.station_service")

STATION_RIVERS = {
    # Iguazú
    "PUERTO_IGUAZU": "Iguazú",
    "PUERTO_MACUCO-PAGEWNIVEL": "Iguazú",
    "PUNTA_PELIGRO-PAGEWNIVEL": "Iguazú",
    "CATARATAS": "Iguazú",
    "CAPANEMA": "Iguazú",

    # Paraguay
    "PILCOMAYO": "Paraguay",
    "DALMACIA": "Paraguay",
    "FORMOSA": "Paraguay",
    "LASPALMAS": "Paraguay",

    # Río de la Plata
    "BALIZAMITRE_LEVEL": "Río de la Plata",
    "BUENOSAIRES_PRIMERESPIGON": "Río de la Plata",
    "BUENOSAIRES": "Río de la Plata",
    "LAPLATA": "Río de la Plata",
    "MAGDALENA": "Río de la Plata",
    "OYARVIDESTARLINK": "Río de la Plata",
    "SANCLEMENTE": "Río de la Plata",
    "SPAR_236RADAR": "Río de la Plata"
}


def calculate_transmission_status(ultimo_timestamp: Optional[str], frecuencia_minutos: Optional[int], is_pna_source: bool = False) -> Dict[str, Any]:
    freq = frecuencia_minutos or 60
    if not ultimo_timestamp:
        return {
            "falla_reporte": True,
            "estado_transmision": "sin_datos",
            "horas_sin_reportar": None,
            "minutos_sin_reportar": None,
            "tiempo_sin_reportar_str": "Sin datos"
        }

    now = datetime.now()
    dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(ultimo_timestamp[:19], fmt)
            break
        except Exception:
            pass

    if dt is None:
        return {
            "falla_reporte": True,
            "estado_transmision": "sin_datos",
            "horas_sin_reportar": None,
            "minutos_sin_reportar": None,
            "tiempo_sin_reportar_str": "Sin datos"
        }

    diff_sec = max(0, (now - dt).total_seconds())
    diff_min = int(diff_sec / 60)
    diff_hours = round(diff_sec / 3600.0, 1)

    umbral_falla_horas = 8.0 if is_pna_source else (4.0 if freq <= 30 else max(4.0, (freq / 60.0) * 3.0))

    if diff_hours < 1.0:
        tiempo_str = f"hace {diff_min} min"
    elif diff_hours < 24.0:
        tiempo_str = f"hace {diff_hours:.1f} h"
    else:
        dias = int(diff_hours // 24)
        tiempo_str = f"hace {dias} d"

    if diff_hours >= umbral_falla_horas:
        estado = "falla"
        falla = True
    elif diff_min > freq * 2:
        estado = "demorado"
        falla = False
    else:
        estado = "online"
        falla = False

    return {
        "falla_reporte": falla,
        "estado_transmision": estado,
        "horas_sin_reportar": diff_hours,
        "minutos_sin_reportar": diff_min,
        "tiempo_sin_reportar_str": tiempo_str
    }


def get_all_stations() -> List[Dict[str, Any]]:
    with get_db() as conn:
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
                e.url,
                m.altura as ultima_altura
            FROM estaciones e
            LEFT JOIN mediciones m ON m.estacion_id = e.id AND m.timestamp = e.ultimo_timestamp
            ORDER BY e.nombre COLLATE NOCASE ASC
        """)
        rows = cursor.fetchall()

        pna_dict = {}
        try:
            cursor.execute("""
                SELECT mp.estacion_id, mp.altura as pna_altura, mp.timestamp as pna_timestamp, 
                       mp.estado_rio as pna_estado_rio, mp.puerto_pna
                FROM mediciones_prefectura mp
                JOIN (
                    SELECT estacion_id, MAX(timestamp) as max_ts
                    FROM mediciones_prefectura
                    GROUP BY estacion_id
                ) latest ON mp.estacion_id = latest.estacion_id AND mp.timestamp = latest.max_ts
            """)
            for p_row in cursor.fetchall():
                pna_dict[p_row["estacion_id"]] = dict(p_row)
        except Exception as e:
            logger.warning(f"Error consultando mediciones_prefectura: {e}")

    fetched_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    estaciones = []
    for r in rows:
        d = dict(r)
        agp_alt = round(d["ultima_altura"], 2) if d.get("ultima_altura") is not None else None
        agp_ts = d.get("ultimo_timestamp")
        
        p_info = pna_dict.get(d["id"], {})
        pna_alt = round(p_info["pna_altura"], 2) if p_info.get("pna_altura") is not None else None
        pna_ts = p_info.get("pna_timestamp")
        pna_estado = p_info.get("pna_estado_rio")
        pna_puerto = p_info.get("puerto_pna")

        # Normalización a ISO-8601
        m_at_iso = agp_ts.replace(" ", "T") if agp_ts else None

        # Tendencia normalizada
        trend_val = None
        if pna_estado:
            st_up = pna_estado.upper()
            if "CRECE" in st_up:
                trend_val = "CRECE"
            elif "BAJA" in st_up:
                trend_val = "BAJA"
            elif "ESTACIONARIO" in st_up:
                trend_val = "ESTACIONARIO"

        river_name = STATION_RIVERS.get(d["codigo"], "Paraná")

        # Detección precisa de fuente original (AGP, ONS, COPEL, etc.)
        raw_url = str(d.get("url") or "").strip()
        if raw_url.startswith("ONS:"):
            detected_source = "ONS"
        elif raw_url.startswith("COPEL:"):
            detected_source = "COPEL"
        elif raw_url.startswith("ENGIE:"):
            detected_source = "ENGIE"
        elif raw_url.startswith("ITAIPU:"):
            detected_source = "ITAIPU"
        else:
            detected_source = "AGP"

        # Inyección de claves de CONTRATO DTO UNIFICADO
        d["station_id"] = str(d["codigo"])
        d["station_name"] = str(d["nombre"])
        d["river"] = river_name
        d["source"] = detected_source
        d["measured_at"] = m_at_iso
        d["fetched_at"] = fetched_at
        d["level_m"] = agp_alt
        d["variation_m"] = None
        d["flow_in_m3s"] = None
        d["flow_out_m3s"] = None
        d["flow_turbined_m3s"] = None
        d["flow_spilled_m3s"] = None
        d["rain_mm"] = None
        d["trend"] = trend_val
        d["raw_status"] = "OPERATIVA"

        # Compatibilidad UI / Front
        d["agp_altura"] = agp_alt
        d["agp_timestamp"] = agp_ts
        d["pna_altura"] = pna_alt
        d["pna_timestamp"] = pna_ts
        d["pna_estado_rio"] = pna_estado
        d["pna_puerto"] = pna_puerto
        d["diferencia_agp_pna"] = round(agp_alt - pna_alt, 2) if (agp_alt is not None and pna_alt is not None) else None
        d["ultima_altura"] = agp_alt
        d["ultimo_timestamp"] = agp_ts
        d["fuente_reciente"] = detected_source

        thresholds = get_station_thresholds(d["codigo"])
        d["umbrales"] = thresholds
        d["alertas_activas"] = thresholds.get("alertas_activas", True)
        d["estado_hidrologico"] = calculate_station_status(agp_alt, thresholds, altura_pna=pna_alt, timestamp_pna=pna_ts)

        trans_info = calculate_transmission_status(agp_ts, d.get("frecuencia_minutos"), is_pna_source=False)
        d.update(trans_info)

        estaciones.append(d)

    return estaciones


def get_all_stations_dto() -> List[Dict[str, Any]]:
    """Retorna estrictamente el listado DTO con los 15 campos canónicos."""
    stations = get_all_stations()
    dto_keys = [
        "station_id", "station_name", "river", "source", "measured_at",
        "fetched_at", "level_m", "variation_m", "flow_in_m3s", "flow_out_m3s",
        "flow_turbined_m3s", "flow_spilled_m3s", "rain_mm", "trend", "raw_status"
    ]
    return [{k: st.get(k) for k in dto_keys} for st in stations]


def get_station_measurements(station_id: int, rango: str = "24h") -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, codigo, nombre, latitud, longitud, frecuencia_minutos, ultimo_timestamp, url FROM estaciones WHERE id = ?", (station_id,))
        station_row = cursor.fetchone()
        if not station_row:
            return None

        station_info = dict(station_row)
        raw_st_url = str(station_info.get("url") or "").strip()
        if raw_st_url.startswith("ONS:"):
            st_source = "ONS"
        elif raw_st_url.startswith("COPEL:"):
            st_source = "COPEL"
        elif raw_st_url.startswith("ENGIE:"):
            st_source = "ENGIE"
        elif raw_st_url.startswith("ITAIPU:"):
            st_source = "ITAIPU"
        else:
            st_source = "AGP"
        station_info["source"] = st_source
        thresholds = get_station_thresholds(station_info["codigo"])
        station_info["umbrales"] = thresholds

        cutoff_date = calculate_range_cutoff(cursor, station_id, rango, table_name="mediciones")
        where_clause = "WHERE estacion_id = ?"
        params: List[Any] = [station_id]
        if cutoff_date:
            where_clause += " AND timestamp >= ?"
            params.append(cutoff_date)

        cursor.execute(f"SELECT COUNT(*) FROM mediciones {where_clause}", params)
        total_in_range = cursor.fetchone()[0]

        puntos = []
        if total_in_range > 0:
            cursor.execute(f"SELECT timestamp, altura FROM mediciones {where_clause} ORDER BY timestamp ASC", params)
            raw_rows = cursor.fetchall()
            if len(raw_rows) > 35000:
                step = max(1, len(raw_rows) // 30000)
                selected_rows = raw_rows[::step]
                if selected_rows[-1] != raw_rows[-1]:
                    selected_rows.append(raw_rows[-1])
            else:
                selected_rows = raw_rows

            puntos = [{"t": row["timestamp"], "y": round(row["altura"], 2)} for row in selected_rows]

        cursor.execute(f"SELECT MAX(altura) as max_alt, MIN(altura) as min_alt, AVG(altura) as avg_alt FROM mediciones {where_clause}", params)
        stats_row = cursor.fetchone()
        max_alt = round(stats_row["max_alt"], 2) if stats_row["max_alt"] is not None else None
        min_alt = round(stats_row["min_alt"], 2) if stats_row["min_alt"] is not None else None
        avg_alt = round(stats_row["avg_alt"], 2) if stats_row["avg_alt"] is not None else None

        cursor.execute("SELECT altura, timestamp FROM mediciones WHERE estacion_id = ? ORDER BY timestamp DESC LIMIT 10", (station_id,))
        last_readings = cursor.fetchall()

        ultima_altura = round(last_readings[0]["altura"], 2) if len(last_readings) > 0 else None
        ultimo_ts = last_readings[0]["timestamp"] if len(last_readings) > 0 else None

        tendencia = "estable"
        velocidad_cm_hora = 0.0

        if len(last_readings) >= 2:
            diff = round(last_readings[0]["altura"] - last_readings[1]["altura"], 2)
            if diff >= 0.02:
                tendencia = "sube"
            elif diff <= -0.02:
                tendencia = "baja"

            try:
                t0 = datetime.strptime(last_readings[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
                t1 = datetime.strptime(last_readings[1]["timestamp"], "%Y-%m-%d %H:%M:%S")
                delta_horas = abs((t0 - t1).total_seconds()) / 3600.0
                if delta_horas > 0:
                    velocidad_cm_hora = round(((last_readings[0]["altura"] - last_readings[1]["altura"]) * 100.0) / delta_horas, 1)
            except Exception:
                pass

        variacion_24h = None
        if ultimo_ts:
            try:
                u_dt = datetime.strptime(ultimo_ts, "%Y-%m-%d %H:%M:%S")
                target_24h = (u_dt - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("SELECT altura FROM mediciones WHERE estacion_id = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (station_id, target_24h))
                row_24 = cursor.fetchone()
                if row_24 and ultima_altura is not None:
                    variacion_24h = round(ultima_altura - row_24["altura"], 2)
            except Exception:
                pass

        intervalo_minutos = station_info.get("frecuencia_minutos") or 20
        if len(last_readings) >= 2:
            try:
                t1_dt = datetime.strptime(last_readings[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
                t2_dt = datetime.strptime(last_readings[1]["timestamp"], "%Y-%m-%d %H:%M:%S")
                diff_m = round(abs((t1_dt - t2_dt).total_seconds()) / 60)
                if 1 <= diff_m <= 1440:
                    intervalo_minutos = diff_m
            except Exception:
                pass

        cursor.execute("SELECT timestamp, altura FROM mediciones WHERE estacion_id = ? ORDER BY timestamp DESC LIMIT 20", (station_id,))
        agp_map = {r["timestamp"]: round(r["altura"], 2) for r in cursor.fetchall()}

        cursor.execute("SELECT timestamp, altura, estado_rio FROM mediciones_prefectura WHERE estacion_id = ? ORDER BY timestamp DESC LIMIT 20", (station_id,))
        pna_map = {r["timestamp"]: {"altura": round(r["altura"], 2), "estado": r["estado_rio"]} for r in cursor.fetchall()}

        all_timestamps = sorted(set(list(agp_map.keys()) + list(pna_map.keys())), reverse=True)[:20]
        recientes = []
        for ts in all_timestamps:
            a_alt = agp_map.get(ts)
            p_obj = pna_map.get(ts, {})
            p_alt = p_obj.get("altura")
            p_est = p_obj.get("estado")
            diff_pna_agp = round(a_alt - p_alt, 2) if (a_alt is not None and p_alt is not None) else None
            row_alt = a_alt if a_alt is not None else p_alt
            recientes.append({
                "timestamp": ts,
                "altura": row_alt,
                "altura_agp": a_alt,
                "altura_pna": p_alt,
                "estado_pna": p_est,
                "diferencia": diff_pna_agp
            })

        for i in range(len(recientes) - 1):
            if recientes[i]["altura"] is not None and recientes[i+1]["altura"] is not None:
                recientes[i]["variacion"] = round(recientes[i]["altura"] - recientes[i+1]["altura"], 2)
            else:
                recientes[i]["variacion"] = None
        if recientes:
            recientes[-1]["variacion"] = None

        cutoff_pna = calculate_range_cutoff(cursor, station_id, rango, table_name="mediciones_prefectura")
        pna_where = "WHERE estacion_id = ?"
        pna_params: List[Any] = [station_id]
        if cutoff_pna:
            pna_where += " AND timestamp >= ?"
            pna_params.append(cutoff_pna)

        cursor.execute(f"SELECT timestamp, altura, estado_rio FROM mediciones_prefectura {pna_where} ORDER BY timestamp ASC", pna_params)
        puntos_pna = [{"t": r["timestamp"], "y": round(r["altura"], 2), "estado": r["estado_rio"]} for r in cursor.fetchall()]

        cursor.execute("SELECT altura, timestamp, estado_rio, puerto_pna FROM mediciones_prefectura WHERE estacion_id = ? ORDER BY timestamp DESC LIMIT 1", (station_id,))
        pna_last_row = cursor.fetchone()
        pna_last_alt = round(pna_last_row["altura"], 2) if pna_last_row and pna_last_row["altura"] is not None else None
        pna_last_ts = pna_last_row["timestamp"] if pna_last_row else None
        pna_last_estado = pna_last_row["estado_rio"] if pna_last_row else None
        pna_puerto_name = pna_last_row["puerto_pna"] if pna_last_row else None

        diferencia_agp_pna = round(ultima_altura - pna_last_alt, 2) if (ultima_altura is not None and pna_last_alt is not None) else None
        trans_info = calculate_transmission_status(ultimo_ts, station_info.get("frecuencia_minutos", 20), is_pna_source=False)
        estado_hidrologico = calculate_station_status(ultima_altura, thresholds, altura_pna=pna_last_alt, timestamp_pna=pna_last_ts)

    return {
        "success": True,
        "estacion": station_info,
        "kpis": {
            "ultima_altura": ultima_altura,
            "ultimo_timestamp": ultimo_ts,
            "agp_altura": ultima_altura,
            "agp_timestamp": ultimo_ts,
            "fuente_reciente": "AGP",
            "tendencia": tendencia,
            "velocidad_cm_hora": velocidad_cm_hora,
            "variacion_24h": variacion_24h,
            "max_altura": max_alt,
            "min_altura": min_alt,
            "promedio_altura": avg_alt,
            "estado_hidrologico": estado_hidrologico,
            "umbrales": thresholds,
            "alertas_activas": thresholds.get("alertas_activas", True),
            "falla_reporte": trans_info["falla_reporte"],
            "estado_transmision": trans_info["estado_transmision"],
            "horas_sin_reportar": trans_info["horas_sin_reportar"],
            "tiempo_sin_reportar_str": trans_info["tiempo_sin_reportar_str"],
            "total_puntos": len(puntos),
            "total_puntos_pna": len(puntos_pna),
            "intervalo_minutos": intervalo_minutos,
            "frecuencia_minutos": station_info.get("frecuencia_minutos", 20),
            "pna_altura": pna_last_alt,
            "pna_timestamp": pna_last_ts,
            "pna_estado_rio": pna_last_estado,
            "pna_puerto": pna_puerto_name,
            "diferencia_agp_pna": diferencia_agp_pna
        },
        "puntos": puntos,
        "puntos_pna": puntos_pna,
        "recientes": recientes
    }


def get_situation_overview() -> Dict[str, Any]:
    estaciones = get_all_stations()

    alertas_activas = []
    estaciones_falla_reporte = []
    conteo_estados = {
        "normal": 0, "alerta": 0, "evacuacion": 0, "sin_datos": 0, "desactivado": 0
    }

    estaciones_clave_codigos = ["PUERTO_IGUAZU", "PUERTO_LIBERTAD", "POSADAS", "CORRIENTES", "ROSARIO"]
    estaciones_clave = []

    for est in estaciones:
        st = est.get("estado_hidrologico", "normal")
        conteo_estados[st] = conteo_estados.get(st, 0) + 1

        pna_est = (est.get("pna_estado_rio") or "").upper()
        tendencia = "creciente" if "CRECE" in pna_est else ("bajante" if "BAJA" in pna_est else "estable")

        if est.get("alertas_activas", True) and st in ("alerta", "evacuacion"):
            alertas_activas.append({
                "id": est["id"],
                "codigo": est["codigo"],
                "nombre": est["nombre"],
                "altura": est["ultima_altura"],
                "pna_altura": est.get("pna_altura"),
                "pna_timestamp": est.get("pna_timestamp"),
                "pna_estado_rio": est.get("pna_estado_rio"),
                "tendencia": tendencia,
                "diferencia_agp_pna": est.get("diferencia_agp_pna"),
                "estado": st,
                "umbrales": est.get("umbrales", {}),
                "timestamp": est["ultimo_timestamp"],
                "falla_reporte": est.get("falla_reporte", False),
                "tiempo_sin_reportar_str": est.get("tiempo_sin_reportar_str")
            })

        if est.get("falla_reporte"):
            estaciones_falla_reporte.append({
                "id": est["id"],
                "codigo": est["codigo"],
                "nombre": est["nombre"],
                "ultima_altura": est.get("ultima_altura"),
                "ultimo_timestamp": est.get("ultimo_timestamp"),
                "frecuencia_minutos": est.get("frecuencia_minutos", 60),
                "horas_sin_reportar": est.get("horas_sin_reportar"),
                "tiempo_sin_reportar_str": est.get("tiempo_sin_reportar_str"),
                "alertas_activas": est.get("alertas_activas", True),
                "estado_hidrologico": st
            })

        if est["codigo"] in estaciones_clave_codigos:
            estaciones_clave.append(est)

    severidad_orden = {"evacuacion": 0, "alerta": 1}
    alertas_activas.sort(key=lambda x: severidad_orden.get(x["estado"], 99))
    estaciones_falla_reporte.sort(key=lambda x: (x.get("horas_sin_reportar") or 0), reverse=True)

    return {
        "success": True,
        "total_estaciones": len(estaciones),
        "conteo_estados": conteo_estados,
        "alertas_activas": alertas_activas,
        "total_alertas": len(alertas_activas),
        "estaciones_falla_reporte": estaciones_falla_reporte,
        "total_falla_reporte": len(estaciones_falla_reporte),
        "estaciones_clave": estaciones_clave
    }


def export_station_csv(station_id: int, rango: str = "todo", is_cota: bool = False, offset: float = 0.0) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT codigo, nombre FROM estaciones WHERE id = ?", (station_id,))
        row = cursor.fetchone()
        if not row:
            return None

        filename_base = row["codigo"]
        cutoff = calculate_range_cutoff(cursor, station_id, rango)
        where = "WHERE estacion_id = ?"
        params = [station_id]
        if cutoff:
            where += " AND timestamp >= ?"
            params.append(cutoff)

        cursor.execute(f"SELECT timestamp, altura FROM mediciones {where} ORDER BY timestamp ASC", params)
        rows = cursor.fetchall()

    today_str = datetime.now().strftime('%Y%m%d')
    if is_cota:
        csv_content = "fecha_hora,cota\n"
        for r in rows:
            val = round(r['altura'] + offset, 2)
            csv_content += f"{r['timestamp']},{val:.2f}\n"
        filename = f"{filename_base}_cota_{rango}_{today_str}.csv"
    else:
        csv_content = "fecha_hora,altura_metros\n"
        for r in rows:
            csv_content += f"{r['timestamp']},{round(r['altura'], 2):.2f}\n"
        filename = f"{filename_base}_{rango}_{today_str}.csv"

    return {
        "filename": filename,
        "content": csv_content
    }
