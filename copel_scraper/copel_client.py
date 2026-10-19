import re
import csv
import json
import os
import unicodedata
from datetime import datetime
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

COPEL_CANONICAL_MAP = {
    "foz do areia": ("IGGBMU", "Foz do Areia", "Iguazú", "Usina Hidrelétrica"),
    "areia": ("IGGBMU", "Foz do Areia", "Iguazú", "Usina Hidrelétrica"),
    "segredo": ("IGSEGR", "Segredo", "Iguazú", "Usina Hidrelétrica"),
    "gov ney braga": ("IGSEGR", "Segredo", "Iguazú", "Usina Hidrelétrica"),
    "salto santiago": ("IGSSAN", "Salto Santiago", "Iguazú", "Usina Hidrelétrica"),
    "santiago": ("IGSSAN", "Salto Santiago", "Iguazú", "Usina Hidrelétrica"),
    "salto osorio": ("IGSOSO", "Salto Osório", "Iguazú", "Usina Hidrelétrica"),
    "osorio": ("IGSOSO", "Salto Osório", "Iguazú", "Usina Hidrelétrica"),
    "salto caxias": ("IGSCAX", "Salto Caxias", "Iguazú", "Usina Hidrelétrica"),
    "caxias": ("IGSCAX", "Salto Caxias", "Iguazú", "Usina Hidrelétrica"),
    "baixo iguacu": ("IGUHBI", "Baixo Iguaçu", "Iguazú", "Usina Hidrelétrica"),
    "baixo iguazu": ("IGUHBI", "Baixo Iguaçu", "Iguazú", "Usina Hidrelétrica"),
    "porto capanema": ("CAPANEMA", "Porto Capanema", "Iguazú", "Posto Hidrométrico"),
    "capanema": ("CAPANEMA", "Porto Capanema", "Iguazú", "Posto Hidrométrico"),
    "hotel cataratas": ("CATARATAS", "Cataratas", "Iguazú", "Posto Hidrométrico"),
    "cataratas": ("CATARATAS", "Cataratas", "Iguazú", "Posto Hidrométrico"),
    "jordao": ("JDJORD", "Jordão", "Iguazú", "Usina Hidrelétrica"),
    "fundao": ("IGFND", "Fundão", "Iguazú", "Usina Hidrelétrica"),
    "santa clara": ("IGSCL", "Santa Clara", "Iguazú", "Usina Hidrelétrica")
}


class CopelClient:
    """
    Cliente HTTP para la extracción de datos hidrológicos de la cuenca del Río Iguazú (COPEL MHB).
    Realiza las peticiones directamente contra el ciclo de vida de JSF / PrimeFaces.
    Garantiza blindaje contra falsos ceros y salida normalizada al contrato DTO.
    """
    BASE_URL = "https://www.copel.com/mhbweb/paginas/bacia-iguacu.jsf"

    def __init__(self, timeout=35):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'es-ES,es;q=0.9,pt-BR;q=0.8,pt;q=0.7,en;q=0.6',
        })
        self.view_state = None
        self.stations = []
        self._initialized = False

    def _extract_view_state(self, html_or_xml):
        m = re.search(r'javax\.faces\.ViewState.*?><!\[CDATA\[(.*?)\]\]>', html_or_xml)
        if m:
            return m.group(1)
        m = re.search(r'name=["\']javax\.faces\.ViewState["\'][^>]*?value=["\']([^"\']+)["\']', html_or_xml)
        if m:
            return m.group(1)
        m = re.search(r'value=["\']([^"\']+)["\'][^>]*?name=["\']javax\.faces\.ViewState["\']', html_or_xml)
        if m:
            return m.group(1)
        return self.view_state

    def init_session(self):
        """Inicializa la sesión JSF y carga el catálogo de estaciones y centrales."""
        resp = self.session.get(self.BASE_URL, verify=False, timeout=self.timeout)
        resp.encoding = 'utf-8'
        self.view_state = self._extract_view_state(resp.text)
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        dialogs = soup.find_all('form', id=lambda x: x and 'formDialog' in x)
        
        self.stations = []
        for idx, d in enumerate(dialogs):
            fid = d.get('id', '')
            title_elem = d.find('span', class_='ui-dialog-title')
            title = title_elem.get_text(strip=True) if title_elem else f"Estacion_{idx}"
            
            is_usina = any(k in title.lower() for k in ["usina", "uhe", "derivação", "desvio"])
            tipo = "Usina Hidrelétrica" if is_usina else "Posto Hidrométrico"
            
            short_name = title.split(' - ')[0].strip()
            self.stations.append({
                'index': idx,
                'form_id': fid,
                'dialog_id': f"{fid}:janela",
                'title': title,
                'tipo': tipo,
                'short_name': short_name
            })
            
        self._initialized = True
        return self.stations

    def list_stations(self):
        """Retorna la lista de todas las estaciones y centrales disponibles."""
        if not self._initialized:
            self.init_session()
        return self.stations

    def _ajax_headers(self):
        return {
            'Accept': 'application/xml, text/xml, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Faces-Request': 'partial/ajax',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': self.BASE_URL,
            'Origin': 'https://www.copel.com'
        }

    def _clean_number(self, val_str: Any) -> Optional[float]:
        """
        Convierte números formateados ('1.700', '5,491', '738,011') a float.
        REGLA DE NEGOCIO 2: Prohibido el falso cero.
        Valores vacíos, '-', 'S/D', 's/l', 'N/A' o errores retornan estrictamente None.
        """
        if val_str is None:
            return None
        if isinstance(val_str, (int, float)):
            import math
            if math.isnan(val_str) or math.isinf(val_str):
                return None
            return round(float(val_str), 3)

        s = str(val_str).strip()
        if not s or s.upper() in ('-', '--', 'N/A', 'NAN', 'NONE', 'NULL', 'S/D', 'S/E', 'S/L', 'S/R', 'SD', 'SE'):
            return None

        # Reemplazos numéricos según formato portugués/español
        if ',' in s and '.' in s:
            if s.rfind(',') > s.rfind('.'):  # 1.234,56
                s = s.replace('.', '').replace(',', '.')
            else:  # 1,234.56
                s = s.replace(',', '')
        elif ',' in s:
            s = s.replace(',', '.')
        elif '.' in s:
            parts = s.split('.')
            if len(parts) == 2 and len(parts[1]) == 3 and parts[0].isdigit() and int(parts[0]) > 0:
                s = parts[0] + parts[1]

        try:
            return round(float(s), 3)
        except (ValueError, TypeError):
            return None

    def _clean_datetime(self, dt_str: Any) -> Optional[str]:
        """Convierte '08/10/26 11h' a formato ISO-8601 canónico 'YYYY-MM-DDTHH:MM:SS'."""
        if not dt_str:
            return None
        s = str(dt_str).strip()
        m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{2,4})(?:[T\s](\d{1,2})(?::(\d{2}))?(?::\d{2})?)?h?$', s)
        if m:
            d, mth, y, h, mi = m.groups()
            year = int(y)
            if year < 100:
                year += 2000
            hour = int(h) if h is not None else 0
            minute = int(mi) if mi is not None else 0
            return f"{year:04d}-{int(mth):02d}-{int(d):02d}T{hour:02d}:{minute:02d}:00"

        if " " in s and len(s) >= 19:
            return s[:19].replace(" ", "T")
        if "T" in s and len(s) >= 19:
            return s[:19]
        return s

    @staticmethod
    def _normalize_string(text):
        if not text:
            return ""
        t = ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()
        t = t.replace('iguazu', 'iguacu').replace('caixias', 'caxias').replace('areias', 'areia')
        return re.sub(r'[^a-z0-9]', ' ', t).strip()

    def find_station(self, station_identifier):
        if not self._initialized:
            self.init_session()

        if isinstance(station_identifier, int) or (isinstance(station_identifier, str) and station_identifier.isdigit()):
            idx = int(station_identifier)
            if 0 <= idx < len(self.stations):
                return self.stations[idx]
            return None

        ident_norm = self._normalize_string(station_identifier)
        ident_words = ident_norm.split()

        for st in self.stations:
            if ident_norm == self._normalize_string(st['short_name']) or ident_norm == self._normalize_string(st['title']):
                return st

        for st in self.stations:
            title_norm = self._normalize_string(st['title'])
            if all(w in title_norm for w in ident_words):
                return st

        for st in self.stations:
            title_norm = self._normalize_string(st['title'])
            if ident_norm in title_norm or title_norm in ident_norm:
                return st

        return None

    def fetch_station_data(self, station_identifier, start_date=None, end_date=None, normalize=False):
        if not self._initialized:
            self.init_session()

        target = self.find_station(station_identifier)
        if not target:
            raise ValueError(f"No se encontró la estación/central: '{station_identifier}'")

        idx = target['index']
        form_id = target['form_id']
        dialog_id = target['dialog_id']
        headers = self._ajax_headers()

        cmd_payload = {
            'javax.faces.partial.ajax': 'true',
            'javax.faces.source': f'form:j_idt73:{idx}:j_idt74',
            'javax.faces.partial.execute': f'form:j_idt73:{idx}:j_idt74',
            f'form:j_idt73:{idx}:j_idt74': f'form:j_idt73:{idx}:j_idt74',
            'form': 'form',
            'javax.faces.ViewState': self.view_state
        }
        r_cmd = self.session.post(self.BASE_URL, headers=headers, data=cmd_payload, verify=False, timeout=self.timeout)
        self.view_state = self._extract_view_state(r_cmd.text)

        load_payload = {
            'javax.faces.partial.ajax': 'true',
            'javax.faces.source': dialog_id,
            'javax.faces.partial.execute': dialog_id,
            'javax.faces.partial.render': dialog_id,
            f'{dialog_id}_contentLoad': 'true',
            form_id: form_id,
            'javax.faces.ViewState': self.view_state
        }
        r_dlg = self.session.post(self.BASE_URL, headers=headers, data=load_payload, verify=False, timeout=self.timeout)
        self.view_state = self._extract_view_state(r_dlg.text)
        xml_content = r_dlg.text

        if start_date and end_date:
            btn_id = f'{form_id}:j_idt173'
            update_payload = {
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': btn_id,
                'javax.faces.partial.execute': form_id,
                'javax.faces.partial.render': f'{form_id}:tabela {form_id}:mensagem',
                btn_id: btn_id,
                form_id: form_id,
                f'{form_id}:dataInicialPonto_input': start_date,
                f'{form_id}:dataFinalPonto_input': end_date,
                'javax.faces.ViewState': self.view_state
            }
            r_upd = self.session.post(self.BASE_URL, headers=headers, data=update_payload, verify=False, timeout=self.timeout)
            self.view_state = self._extract_view_state(r_upd.text)
            xml_content = r_upd.text

        raw_records = self._parse_table_data(xml_content)

        if normalize:
            processed_records = []
            for r in raw_records:
                norm_r = {}
                for col, val in r.items():
                    if any(k in col.lower() for k in ('data', 'hora')):
                        norm_r[col] = self._clean_datetime(val)
                    else:
                        norm_r[col] = self._clean_number(val)
                processed_records.append(norm_r)
            records = processed_records
        else:
            records = raw_records

        return {
            'station_index': idx,
            'station_title': target['title'],
            'station_tipo': target['tipo'],
            'short_name': target['short_name'],
            'total_records': len(records),
            'records': records
        }

    def fetch_station_dto(self, station_identifier, start_date=None, end_date=None) -> List[Dict[str, Any]]:
        """
        Retorna la lista de registros estructurados según el CONTRATO DTO UNIFICADO:
        - station_id, station_name, river, source, measured_at, fetched_at,
          level_m, variation_m, flow_in_m3s, flow_out_m3s, flow_turbined_m3s,
          flow_spilled_m3s, rain_mm, trend, raw_status.
        """
        res = self.fetch_station_data(station_identifier, start_date=start_date, end_date=end_date, normalize=False)
        short_norm = self._normalize_string(res.get('short_name', ''))
        
        canon_info = COPEL_CANONICAL_MAP.get(short_norm)
        if not canon_info:
            for k, v in COPEL_CANONICAL_MAP.items():
                if k in short_norm or short_norm in k:
                    canon_info = v
                    break

        if canon_info:
            station_id, station_name, river, _ = canon_info
        else:
            station_id = re.sub(r'[^A-Z0-9_]', '_', res.get('short_name', 'COPEL').upper())
            station_name = res.get('short_name', 'Estación COPEL')
            river = "Iguazú"

        fetched_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        dto_list: List[Dict[str, Any]] = []

        for row in res.get('records', []):
            dt_raw = None
            level_m = None
            flow_in = None
            flow_out = None
            flow_turb = None
            flow_spill = None
            rain_mm = None

            for col_name, val in row.items():
                c_low = col_name.lower()
                clean_v = self._clean_number(val)
                if any(k in c_low for k in ('data', 'hora')):
                    dt_raw = val
                elif 'montante' in c_low or 'r\xe9gua' in c_low or 'regla' in c_low or 'n\xedvel' in c_low or 'nivel' in c_low:
                    if 'jusante' not in c_low:
                        level_m = clean_v
                elif 'afluente' in c_low:
                    flow_in = clean_v
                elif 'defluente' in c_low or 'vaz\xe3o' in c_low or 'caudal' in c_low:
                    flow_out = clean_v
                elif 'turbinada' in c_low:
                    flow_turb = clean_v
                elif 'vertida' in c_low:
                    flow_spill = clean_v
                elif 'precipita\xe7\xe3o' in c_low or 'chuva' in c_low:
                    if 'acumulada' not in c_low:
                        rain_mm = clean_v

            measured_at = self._clean_datetime(dt_raw) or fetched_at

            dto_list.append({
                "station_id": station_id,
                "station_name": station_name,
                "river": river,
                "source": "COPEL",
                "measured_at": measured_at,
                "fetched_at": fetched_at,
                "level_m": level_m,
                "variation_m": None,
                "flow_in_m3s": flow_in,
                "flow_out_m3s": flow_out,
                "flow_turbined_m3s": flow_turb,
                "flow_spilled_m3s": flow_spill,
                "rain_mm": rain_mm,
                "trend": None,
                "raw_status": "OPERATIVA"
            })

        return dto_list

    def _parse_table_data(self, xml_text):
        cdata_blocks = re.findall(r'<!\[CDATA\[(.*?)\]\]>', xml_text, re.DOTALL)
        records = []
        headers = []

        for block in cdata_blocks:
            if '<table' in block or '<tr' in block:
                soup = BeautifulSoup(block, 'html.parser')
                tables = soup.find_all('table')
                for t in tables:
                    for tr in t.find_all('tr'):
                        ths = [th.get_text(strip=True) for th in tr.find_all('th')]
                        if ths:
                            headers = ths
                            continue
                        tds = [td.get_text(strip=True) for td in tr.find_all('td')]
                        if tds:
                            if len(tds) == 1 and "nenhum registro" in tds[0].lower():
                                continue
                            if headers and len(headers) == len(tds):
                                row_dict = dict(zip(headers, tds))
                                records.append(row_dict)

        unique_records = []
        seen = set()
        for r in records:
            key = tuple(r.items())
            if key not in seen:
                seen.add(key)
                unique_records.append(r)

        return unique_records

    @staticmethod
    def save_csv(data_dict, file_path):
        records = data_dict.get('records', [])
        if not records:
            return False
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        keys = list(records[0].keys())
        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(records)
        return True

    @staticmethod
    def save_json(data_dict, file_path):
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data_dict, f, ensure_ascii=False, indent=2)
        return True
