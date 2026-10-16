import re
import csv
import json
import os
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib3
import unicodedata

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CopelClient:
    """
    Cliente HTTP para la extracción de datos hidrológicos de la cuenca del Río Iguazú (COPEL MHB).
    Realiza las peticiones directamente contra el ciclo de vida de JSF / PrimeFaces
    sin requerir navegadores embebidos ni dependencias pesadas.
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

    def _clean_number(self, val_str):
        """Convierte números formateados en portugués/español (ej. 1.700 o 5,491) a float."""
        if not val_str or not isinstance(val_str, str):
            return None
        s = val_str.strip()
        if not s or s == '-' or s == '--':
            return None
        # Quitar separador de miles '.' y reemplazar coma decimal ',' por '.'
        s_clean = s.replace('.', '').replace(',', '.')
        try:
            return float(s_clean)
        except ValueError:
            return val_str

    def _clean_datetime(self, dt_str):
        """Convierte '08/10/26 11h' a formato ISO '2026-10-08 11:00:00' si es posible."""
        if not dt_str:
            return dt_str
        s = dt_str.strip()
        # Patrón típico: DD/MM/YY HHh o DD/MM/YYYY HH:MM
        m = re.match(r'^(\d{2})/(\d{2})/(\d{2,4})\s+(\d{1,2})h?$', s)
        if m:
            d, mth, y, h = m.groups()
            year = int(y)
            if year < 100:
                year += 2000
            return f"{year:04d}-{int(mth):02d}-{int(d):02d} {int(h):02d}:00:00"
        return s

    @staticmethod
    def _normalize_string(text):
        if not text:
            return ""
        # Quitar acentos, convertir a minúsculas
        t = ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower()
        # Variaciones comunes de escritura (iguazu -> iguacu, caixias -> caxias, areias -> areia)
        t = t.replace('iguazu', 'iguacu').replace('caixias', 'caxias').replace('areias', 'areia').replace('osorio', 'osorio')
        return re.sub(r'[^a-z0-9]', ' ', t).strip()

    def find_station(self, station_identifier):
        """Busca una estación por índice o nombre de forma tolerante a acentos y variaciones."""
        if not self._initialized:
            self.init_session()

        if isinstance(station_identifier, int) or (isinstance(station_identifier, str) and station_identifier.isdigit()):
            idx = int(station_identifier)
            if 0 <= idx < len(self.stations):
                return self.stations[idx]
            return None

        ident_norm = self._normalize_string(station_identifier)
        ident_words = ident_norm.split()

        # 1. Búsqueda exacta normalizada sobre short_name o title
        for st in self.stations:
            if ident_norm == self._normalize_string(st['short_name']) or ident_norm == self._normalize_string(st['title']):
                return st

        # 2. Búsqueda de todas las palabras contenidas en el título
        for st in self.stations:
            title_norm = self._normalize_string(st['title'])
            if all(w in title_norm for w in ident_words):
                return st

        # 3. Substring simple
        for st in self.stations:
            title_norm = self._normalize_string(st['title'])
            if ident_norm in title_norm or title_norm in ident_norm:
                return st

        return None

    def fetch_station_data(self, station_identifier, start_date=None, end_date=None, normalize=False):
        """
        Descarga los registros de una estación por índice o nombre.
        - station_identifier: int (ej. 33) o str (ej. 'União da Vitória' o 'Foz do Areia').
        - start_date, end_date: 'DD/MM/YYYY HH' (COPEL permite hasta ~6 días previos).
        - normalize: si True, formatea fechas a ISO y números a float.
        """
        if not self._initialized:
            self.init_session()

        target = self.find_station(station_identifier)
        if not target:
            raise ValueError(f"No se encontró la estación/central: '{station_identifier}'")

        idx = target['index']
        form_id = target['form_id']
        dialog_id = target['dialog_id']
        headers = self._ajax_headers()

        # Paso 1: Activar comando de la estación en el servidor
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

        # Paso 2: Cargar el diálogo dinámico
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

        # Paso 3: Si se especificaron fechas personalizadas, ejecutar actualización
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

        # Paso 4: Extraer y procesar registros
        raw_records = self._parse_table_data(xml_content)

        if normalize:
            processed_records = []
            for r in raw_records:
                norm_r = {}
                for col, val in r.items():
                    if 'data' in col.lower() or 'hora' in col.lower():
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

        # Deduplicar preservando orden
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
        """Guarda los registros obtenidos en un archivo CSV UTF-8 con BOM (compatible con Excel)."""
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
        """Guarda los datos estructurados en un archivo JSON."""
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data_dict, f, ensure_ascii=False, indent=2)
        return True
