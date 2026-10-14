import requests
from datetime import datetime

class EngieClient:
    """
    Cliente para la API de telemetría de embalses de ENGIE Brasil
    (Salto Santiago y Salto Osório).
    """
    URL = "https://www.engie.com.br/wp-json/v1/telemetria/get-data"

    def __init__(self, timeout=20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Referer': 'https://www.engie.com.br/reservatorios/',
            'X-Requested-With': 'XMLHttpRequest'
        })

    def fetch_plant_data(self, plant_code, fecha_inicio=None):
        """
        Consulta datos para 'UHSS' (Salto Santiago) o 'UHSO' (Salto Osório).
        Retorna registros formateados para el archivo TXT de Tractebel/Engie:
        [dataHora, nivelReservatorio, percVolumeUtil, vazaoAfluente, vazaoTurbinada, vazaoVertida, vazaoDefluente]
        ordenados de más reciente a más antiguo (descendente).
        """
        params = {
            'action': 'getComplexoData',
            'complexo_uri': 'nivelDoReservatorioPorUsina',
            'nocache': 'false',
            f'body_json[cdUsina]': plant_code
        }

        resp = self.session.get(self.URL, params=params, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Error {resp.status_code} al consultar Engie ({plant_code})")

        data = resp.json()
        retorno = data.get('dados', {}).get('retorno', [])

        records = []
        for item in retorno:
            dt_str = item.get('dataHora', '').strip()
            if not dt_str:
                continue

            try:
                # dataHora format: '2026-10-09 08:00:00'
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            if fecha_inicio and dt < fecha_inicio:
                continue

            # Nivel
            nivel = item.get('nivelReservatorio', '')
            try:
                # Si es flotante limpio, formatear
                nivel_f = float(str(nivel).replace(',', '.'))
                # En el ejemplo: 396.56 o 396
                nivel_str = f"{nivel_f:.2f}".rstrip('0').rstrip('.') if '.' in f"{nivel_f:.2f}" else f"{nivel_f:.2f}"
                # Pero en el ejemplo: '396.56', '396.4'
                nivel_str = str(round(nivel_f, 2))
            except Exception:
                nivel_str = str(nivel)

            # Volume Util (en API viene en notación científica ej: 7.3189...E01)
            vol = item.get('percVolumeUtil', '')
            try:
                vol_f = float(str(vol).replace(',', '.'))
                vol_str = f"{vol_f:.2f}"
            except Exception:
                vol_str = str(vol)

            # Caudales: vazaoAfluente, vazaoTurbinada, vazaoVertida, vazaoDefluente
            v_afl = str(item.get('vazaoAfluente', ''))
            v_turb = str(item.get('vazaoTurbinada', ''))
            v_vert = str(item.get('vazaoVertida', ''))
            v_defl = str(item.get('vazaoDefluente', ''))

            row = [dt_str, nivel_str, vol_str, v_afl, v_turb, v_vert, v_defl]
            records.append((dt, row))

        # Ordenar descendente (más reciente primero)
        records.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in records]
