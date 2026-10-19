import requests
from datetime import datetime
from typing import Dict, Any, List, Optional

def clean_engie_num(val: Any) -> Optional[float]:
    """Convierte números formateados a float o retorna None (prohibido el falso cero)."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        import math
        if math.isnan(val) or math.isinf(val):
            return None
        return round(float(val), 2)
    s = str(val).strip()
    if not s or s.upper() in ('-', '--', 'N/A', 'NAN', 'NONE', 'NULL', 'S/D', 'S/E'):
        return None
    s = s.replace(',', '.')
    try:
        return round(float(s), 2)
    except (ValueError, TypeError):
        return None


class EngieClient:
    """
    Cliente para la API de telemetría de embalses de ENGIE Brasil
    (Salto Santiago y Salto Osório).
    Garantiza blindaje contra falsos ceros y exportación DTO unificada.
    """
    URL = "https://www.engie.com.br/wp-json/v1/telemetria/get-data"

    ENGIE_META = {
        "UHSS": {
            "station_id": "IGSSAN",
            "station_name": "Salto Santiago",
            "river": "Iguazú"
        },
        "UHSO": {
            "station_id": "IGSOSO",
            "station_name": "Salto Osório",
            "river": "Iguazú"
        }
    }

    def __init__(self, timeout=20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Referer': 'https://www.engie.com.br/reservatorios/',
            'X-Requested-With': 'XMLHttpRequest'
        })

    def fetch_plant_dto(self, plant_code: str, fecha_inicio: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Retorna registros conforme al CONTRATO DTO UNIFICADO de HidroPanel.
        """
        params = {
            'action': 'getComplexoData',
            'complexo_uri': 'nivelDoReservatorioPorUsina',
            'nocache': 'false',
            'body_json[cdUsina]': plant_code
        }

        resp = self.session.get(self.URL, params=params, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Error {resp.status_code} al consultar Engie ({plant_code})")

        data = resp.json()
        retorno = data.get('dados', {}).get('retorno', [])
        meta = self.ENGIE_META.get(plant_code.upper(), {
            "station_id": plant_code.upper(),
            "station_name": f"Engie {plant_code}",
            "river": "Iguazú"
        })

        fetched_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        dto_list: List[Dict[str, Any]] = []

        for item in retorno:
            dt_str = item.get('dataHora', '').strip()
            if not dt_str:
                continue

            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            if fecha_inicio and dt < fecha_inicio:
                continue

            measured_at = dt.strftime("%Y-%m-%dT%H:%M:%S")

            dto_list.append({
                "station_id": meta["station_id"],
                "station_name": meta["station_name"],
                "river": meta["river"],
                "source": "ENGIE",
                "measured_at": measured_at,
                "fetched_at": fetched_at,
                "level_m": clean_engie_num(item.get('nivelReservatorio')),
                "variation_m": None,
                "flow_in_m3s": clean_engie_num(item.get('vazaoAfluente')),
                "flow_out_m3s": clean_engie_num(item.get('vazaoDefluente')),
                "flow_turbined_m3s": clean_engie_num(item.get('vazaoTurbinada')),
                "flow_spilled_m3s": clean_engie_num(item.get('vazaoVertida')),
                "rain_mm": None,
                "trend": None,
                "raw_status": "OPERATIVA"
            })

        dto_list.sort(key=lambda x: x["measured_at"], reverse=True)
        return dto_list

    def fetch_plant_data(self, plant_code, fecha_inicio=None):
        """
        Compatibilidad retroactiva con macros Excel:
        [dataHora, nivelReservatorio, percVolumeUtil, vazaoAfluente, vazaoTurbinada, vazaoVertida, vazaoDefluente]
        """
        dtos = self.fetch_plant_dto(plant_code, fecha_inicio=fecha_inicio)
        records = []
        for d in dtos:
            dt_s = d["measured_at"].replace("T", " ")
            nivel_s = str(d["level_m"]) if d["level_m"] is not None else ""
            v_afl = str(d["flow_in_m3s"]) if d["flow_in_m3s"] is not None else ""
            v_turb = str(d["flow_turbined_m3s"]) if d["flow_turbined_m3s"] is not None else ""
            v_vert = str(d["flow_spilled_m3s"]) if d["flow_spilled_m3s"] is not None else ""
            v_defl = str(d["flow_out_m3s"]) if d["flow_out_m3s"] is not None else ""
            vol_s = ""

            records.append([dt_s, nivel_s, vol_s, v_afl, v_turb, v_vert, v_defl])

        return records
