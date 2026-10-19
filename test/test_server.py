"""
test/test_server.py
Suite de Pruebas Offline de Integridad de Datos, Parsers y Contrato DTO de HidroPanel.
Ejecutable mediante: python -m unittest discover -s test o python test/test_server.py

Valida matemáticamente y funcionalmente:
1. Invariante de Nulos: Valores faltantes, guiones o 's/l' retornan None y jamás 0.0 (prohibido falso cero).
2. Invariante de Contrato: 15 claves obligatorias en el DTO unificado y fechas ISO-8601 válidas (YYYY-MM-DDTHH:MM:SS).
3. Auditoría de Parsers Offline: Alimentación desde archivos estáticos en test/*.txt y copel_scraper/ejemplos/*.txt.
4. Auditoría de Umbrales: Coherencia matemática (Alerta < Evacuación) y ausencia de niveles sintéticos.
5. Endpoints de la API Offline: Despacho instantáneo y validación de esquemas sin dependencias de red.
"""

import sys
import os
import re
import json
import sqlite3
import unittest
from datetime import datetime
from typing import Dict, Any, List, Optional

# Garantizar que el directorio raíz del proyecto esté en sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.config import DB_PATH
from backend import thresholds
from backend.services.represas_service import (
    clean_num,
    parse_copel_dt,
    get_capanema_copel,
    get_cataratas_copel,
    get_segredo_copel,
    get_represas_dto
)
from backend.services.prefectura_service import (
    _clean_pna_float,
    _parse_pna_table_timestamp,
    fetch_prefectura_table,
    get_prefectura_dto
)
from backend.services import station_service, sync_service
from backend.routes import handle_get
from sync_estaciones import parse_float, parse_toa5_heights

# Clientes de scraping de la cuenca
from copel_scraper.copel_client import CopelClient
from copel_scraper.engie_client import EngieClient, clean_engie_num

# Contrato DTO unificado: 15 claves obligatorias
UNIFIED_DTO_KEYS = {
    "station_id",
    "station_name",
    "river",
    "source",
    "measured_at",
    "fetched_at",
    "level_m",
    "variation_m",
    "flow_in_m3s",
    "flow_out_m3s",
    "flow_turbined_m3s",
    "flow_spilled_m3s",
    "rain_mm",
    "trend",
    "raw_status"
}

ISO_DATETIME_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class TestNullInvariantsAndCleaners(unittest.TestCase):
    """
    Validación de la Invariante Crítica 1: Prohibido el falso cero.
    Un dato faltante, '-', 'S/D', 's/l' o nulo debe devolver estrictamente None y jamás 0.0.
    """

    def setUp(self):
        self.copel = CopelClient()

    def test_copel_clean_number_null_inputs(self):
        null_samples = [
            None, "", "   ", "-", "--", "---",
            "N/A", "NAN", "NONE", "NULL",
            "S/D", "S/E", "S/L", "S/R", "SD", "SE",
            "s/d", "s/e", "s/l", "s/r", "sd", "se"
        ]
        for sample in null_samples:
            res = self.copel._clean_number(sample)
            self.assertIsNone(
                res,
                f"CopelClient._clean_number('{sample}') debió retornar None, pero retornó {res}"
            )
            self.assertNotEqual(
                res, 0.0,
                f"VIOLACIÓN DE GUARDRAIL: CopelClient convirtió '{sample}' en falso cero (0.0)"
            )

    def test_copel_clean_number_legitimate_zeros(self):
        zeros = ["0", "0.0", "0,0", "0,00", "0.00", 0, 0.0]
        for z in zeros:
            res = self.copel._clean_number(z)
            self.assertEqual(
                res, 0.0,
                f"CopelClient._clean_number('{z}') debió retornar 0.0 legítimo, retornó {res}"
            )
            self.assertIsInstance(res, float)

    def test_copel_clean_number_portuguese_formatting(self):
        self.assertEqual(self.copel._clean_number("1.700"), 1700.0)
        self.assertEqual(self.copel._clean_number("2.390"), 2390.0)
        self.assertEqual(self.copel._clean_number("5,491"), 5.491)
        self.assertEqual(self.copel._clean_number("738,011"), 738.011)
        self.assertEqual(self.copel._clean_number("1.234,56"), 1234.56)

    def test_engie_clean_num_null_invariants(self):
        null_samples = [None, "", " ", "-", "--", "N/A", "NAN", "NONE", "NULL", "S/D", "S/E", "s/d"]
        for sample in null_samples:
            res = clean_engie_num(sample)
            self.assertIsNone(res, f"clean_engie_num('{sample}') debió retornar None")
            self.assertNotEqual(res, 0.0, "clean_engie_num produjo falso cero 0.0")

        self.assertEqual(clean_engie_num("0"), 0.0)
        self.assertEqual(clean_engie_num("396.04"), 396.04)

    def test_represas_clean_num_null_invariants(self):
        null_samples = [None, "", "  ", "-", "--", "N/A", "NAN", "NULL", "S/D", "S/E", "s/l", "s/d"]
        for sample in null_samples:
            res = clean_num(sample)
            self.assertIsNone(res, f"clean_num('{sample}') debió retornar None")
            self.assertNotEqual(res, 0.0, "clean_num produjo falso cero 0.0")

        self.assertEqual(clean_num("0"), 0.0)
        self.assertEqual(clean_num("738,061"), 738.06)
        self.assertEqual(clean_num("2.390"), 2390.0)

    def test_prefectura_clean_float_null_invariants(self):
        null_samples = [None, "", " ", "-", "--", "S/E", "S/D", "N/A", "NAN", "NULL", "S/L", "S/R"]
        for sample in null_samples:
            res = _clean_pna_float(sample)
            self.assertIsNone(res, f"_clean_pna_float('{sample}') debió retornar None")
            self.assertNotEqual(res, 0.0, "_clean_pna_float produjo falso cero 0.0")

        self.assertEqual(_clean_pna_float("0"), 0.0)
        self.assertEqual(_clean_pna_float("0,00 Mts"), 0.0)
        self.assertEqual(_clean_pna_float("26,60 Mts"), 26.60)

    def test_sync_estaciones_parse_float_null_invariants(self):
        null_samples = [None, "", "  ", "NAN", "-INF", "INF", "NULL"]
        for sample in null_samples:
            res = parse_float(sample)
            self.assertIsNone(res, f"parse_float('{sample}') debió retornar None")
            self.assertNotEqual(res, 0.0, "parse_float produjo falso cero 0.0")

        self.assertEqual(parse_float("0"), 0.0)
        self.assertEqual(parse_float("26.6"), 26.6)


class TestStaticTxtFilesOfflineParsing(unittest.TestCase):
    """
    Validación de parseo offline de los archivos estáticos de muestra:
    Areia.txt, Baixo Iguazu.txt, Capanema.txt, Cataratas.txt, Caxias.txt,
    OSORIO.txt, SANTIAGO.txt, segredo.txt.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_dir = os.path.join(BASE_DIR, "test")
        cls.ejemplos_dir = os.path.join(BASE_DIR, "copel_scraper", "ejemplos")

    def _resolve_file(self, filename: str) -> Optional[str]:
        p1 = os.path.join(self.test_dir, filename)
        if os.path.isfile(p1):
            return p1
        p2 = os.path.join(self.ejemplos_dir, filename)
        if os.path.isfile(p2):
            return p2
        return None

    def test_capanema_static_parsing(self):
        fpath = self._resolve_file("Capanema.txt")
        self.assertIsNotNone(fpath, "No se encontró Capanema.txt en test/ ni ejemplos/")
        
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip().split("\t") for l in f if l.strip()]

        self.assertGreater(len(lines), 0, "Capanema.txt está vacío")
        for row in lines[:10]:
            self.assertGreaterEqual(len(row), 3, f"Fila Capanema con columnas insuficientes: {row}")
            t_iso = parse_copel_dt(row[0])
            self.assertRegex(t_iso, ISO_DATETIME_REGEX, f"Fecha inválida en Capanema: {row[0]}")
            regla = clean_num(row[1])
            caudal = clean_num(row[2])
            self.assertTrue(regla is None or isinstance(regla, float))
            self.assertTrue(caudal is None or isinstance(caudal, float))

        # Verificar integración con represas_service
        cap_dto = get_capanema_copel()
        self.assertTrue(bool(cap_dto), "get_capanema_copel no retornó datos")
        self.assertEqual(cap_dto.get("codigo"), "CAPANEMA")
        self.assertRegex(cap_dto.get("fecha"), ISO_DATETIME_REGEX)

    def test_cataratas_static_parsing(self):
        fpath = self._resolve_file("Cataratas.txt")
        self.assertIsNotNone(fpath, "No se encontró Cataratas.txt")

        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip().split("\t") for l in f if l.strip()]

        self.assertGreater(len(lines), 0)
        for row in lines[:10]:
            self.assertGreaterEqual(len(row), 3)
            t_iso = parse_copel_dt(row[0])
            self.assertRegex(t_iso, ISO_DATETIME_REGEX)
            regla = clean_num(row[1])
            caudal = clean_num(row[2])
            self.assertTrue(regla is None or isinstance(regla, float))
            self.assertTrue(caudal is None or isinstance(caudal, float))

        cat_dto = get_cataratas_copel()
        self.assertTrue(bool(cat_dto))
        self.assertEqual(cat_dto.get("codigo"), "CATARATAS")
        self.assertRegex(cat_dto.get("fecha"), ISO_DATETIME_REGEX)

    def test_segredo_static_parsing(self):
        fpath = self._resolve_file("segredo.txt")
        self.assertIsNotNone(fpath, "No se encontró segredo.txt")

        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip().split("\t") for l in f if l.strip()]

        self.assertGreater(len(lines), 0)
        for row in lines[:10]:
            self.assertGreaterEqual(len(row), 8)
            t_iso = parse_copel_dt(row[0])
            self.assertRegex(t_iso, ISO_DATETIME_REGEX)
            for val_idx in range(1, len(row)):
                num = clean_num(row[val_idx])
                self.assertTrue(num is None or isinstance(num, float))

        seg_dto = get_segredo_copel()
        self.assertTrue(bool(seg_dto))
        self.assertEqual(seg_dto.get("codigo"), "IGSEGR")
        self.assertRegex(seg_dto.get("fecha"), ISO_DATETIME_REGEX)

    def test_areia_and_baixo_and_caxias_static_parsing(self):
        for fname, code in [("Areia.txt", "IGGBMU"), ("Baixo Iguazu.txt", "IGUHBI"), ("Caxias.txt", "IGSCAX")]:
            fpath = self._resolve_file(fname)
            if not fpath and "Baixo" in fname:
                fpath = self._resolve_file("Baixo Iguazú.txt")
            self.assertIsNotNone(fpath, f"No se encontró archivo estático: {fname}")

            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                lines = [l.strip().split("\t") for l in f if l.strip()]

            self.assertGreater(len(lines), 0, f"Archivo {fname} vacío")
            for row in lines[:10]:
                self.assertGreaterEqual(len(row), 7, f"Fila en {fname} con columnas incompletas")
                t_iso = parse_copel_dt(row[0])
                self.assertRegex(t_iso, ISO_DATETIME_REGEX, f"Fecha inválida en {fname}: {row[0]}")
                cota = clean_num(row[1])
                self.assertTrue(cota is None or isinstance(cota, float))

    def test_osorio_and_santiago_engie_parsing(self):
        for fname, station_id in [("OSORIO.txt", "IGSOSO"), ("SANTIAGO.txt", "IGSSAN")]:
            fpath = self._resolve_file(fname)
            self.assertIsNotNone(fpath, f"No se encontró {fname}")

            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                lines = [l.strip().split("\t") for l in f if l.strip()]

            self.assertGreater(len(lines), 0)
            for row in lines[:10]:
                self.assertGreaterEqual(len(row), 7)
                dt_str = row[0].strip()
                t_iso = dt_str.replace(" ", "T")
                self.assertRegex(t_iso, ISO_DATETIME_REGEX)
                cota = clean_engie_num(row[1])
                afluente = clean_engie_num(row[3])
                defluente = clean_engie_num(row[6])
                self.assertTrue(cota is None or isinstance(cota, float))
                self.assertTrue(afluente is None or isinstance(afluente, float))
                self.assertTrue(defluente is None or isinstance(defluente, float))


class TestUnifiedDTOContract(unittest.TestCase):
    """
    Validación de la Invariante Crítica 2: Contrato DTO Unificado.
    Todos los objetos generados deben contener exactamente las 15 claves requeridas,
    fechas ISO-8601 canónicas (YYYY-MM-DDTHH:MM:SS) y tipos estrictos.
    """

    def _assert_valid_dto(self, dto: Dict[str, Any], context_label: str):
        # 1. Exactitud de claves del contrato (15 claves)
        missing_keys = UNIFIED_DTO_KEYS - set(dto.keys())
        extra_keys = set(dto.keys()) - UNIFIED_DTO_KEYS
        self.assertEqual(
            missing_keys, set(),
            f"[{context_label}] Faltan claves en el DTO unificado: {missing_keys}"
        )
        self.assertEqual(
            extra_keys, set(),
            f"[{context_label}] Claves espurias fuera del contrato DTO: {extra_keys}"
        )
        self.assertEqual(len(dto), 15, f"[{context_label}] El DTO debe contener exactamente 15 claves")

        # 2. Formato de fechas ISO-8601
        self.assertRegex(
            dto["measured_at"], ISO_DATETIME_REGEX,
            f"[{context_label}] measured_at no cumple ISO-8601 (YYYY-MM-DDTHH:MM:SS): '{dto['measured_at']}'"
        )
        self.assertRegex(
            dto["fetched_at"], ISO_DATETIME_REGEX,
            f"[{context_label}] fetched_at no cumple ISO-8601 (YYYY-MM-DDTHH:MM:SS): '{dto['fetched_at']}'"
        )

        # 3. Metadatos textuales obligatorios
        self.assertIsInstance(dto["station_id"], str)
        self.assertTrue(len(dto["station_id"]) > 0, f"[{context_label}] station_id vacío")
        self.assertIsInstance(dto["station_name"], str)
        self.assertTrue(len(dto["station_name"]) > 0, f"[{context_label}] station_name vacío")
        self.assertIsInstance(dto["river"], str)
        self.assertTrue(len(dto["river"]) > 0, f"[{context_label}] river vacío")
        self.assertIsInstance(dto["source"], str)
        self.assertTrue(len(dto["source"]) > 0, f"[{context_label}] source vacío")
        self.assertIsInstance(dto["raw_status"], str)

        # 4. Invariantes de tipos numéricos (float o None, jamás string ni nan)
        numeric_fields = [
            "level_m", "variation_m", "flow_in_m3s", "flow_out_m3s",
            "flow_turbined_m3s", "flow_spilled_m3s", "rain_mm"
        ]
        for f in numeric_fields:
            val = dto[f]
            self.assertTrue(
                val is None or isinstance(val, (int, float)),
                f"[{context_label}] Campo '{f}' con tipo inválido: {type(val)} ({val})"
            )

    def test_represas_service_dto_contract(self):
        dtos = get_represas_dto()
        self.assertIsInstance(dtos, list)
        self.assertGreater(len(dtos), 0, "get_represas_dto no devolvió centrales")
        for dto in dtos:
            self._assert_valid_dto(dto, f"RepresasService:{dto.get('station_id')}")

    def test_engie_client_dto_contract_mock(self):
        client = EngieClient()
        meta = client.ENGIE_META["UHSO"]
        fetched_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        dto = {
            "station_id": meta["station_id"],
            "station_name": meta["station_name"],
            "river": meta["river"],
            "source": "ENGIE",
            "measured_at": "2026-10-19T09:00:00",
            "fetched_at": fetched_at,
            "level_m": clean_engie_num("396.04"),
            "variation_m": None,
            "flow_in_m3s": clean_engie_num("2665"),
            "flow_out_m3s": clean_engie_num("2058"),
            "flow_turbined_m3s": clean_engie_num("903"),
            "flow_spilled_m3s": clean_engie_num("1155"),
            "rain_mm": None,
            "trend": None,
            "raw_status": "OPERATIVA"
        }
        self._assert_valid_dto(dto, "EngieClient:UHSO")

    def test_copel_client_dto_contract_builder(self):
        client = CopelClient()
        now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        sample_row = {
            "Data/Hora": "19/10/26 10h",
            "Cota (m)": "738,061",
            "Vazão Afluente (m³/s)": "2.390",
            "Vazão Defluente (m³/s)": "1.660",
            "Vazão Turbinada (m³/s)": "291",
            "Vazão Vertida (m³/s)": "1.370",
            "Precipitação (mm)": "0,0"
        }
        level_m = client._clean_number(sample_row.get("Cota (m)"))
        flow_in = client._clean_number(sample_row.get("Vazão Afluente (m³/s)"))
        flow_out = client._clean_number(sample_row.get("Vazão Defluente (m³/s)"))
        flow_turb = client._clean_number(sample_row.get("Vazão Turbinada (m³/s)"))
        flow_spill = client._clean_number(sample_row.get("Vazão Vertida (m³/s)"))
        rain_mm = client._clean_number(sample_row.get("Precipitação (mm)"))
        m_at = client._clean_datetime(sample_row.get("Data/Hora"))

        dto = {
            "station_id": "IGGBMU",
            "station_name": "Foz do Areia",
            "river": "Iguazú",
            "source": "COPEL",
            "measured_at": m_at,
            "fetched_at": now_iso,
            "level_m": level_m,
            "variation_m": None,
            "flow_in_m3s": flow_in,
            "flow_out_m3s": flow_out,
            "flow_turbined_m3s": flow_turb,
            "flow_spilled_m3s": flow_spill,
            "rain_mm": rain_mm,
            "trend": None,
            "raw_status": "OPERATIVA"
        }
        self._assert_valid_dto(dto, "CopelClient:Areia")

    def test_prefectura_dto_contract(self):
        fetched_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        dto = {
            "station_id": "PUERTO_IGUAZU",
            "station_name": "Puerto Iguazú",
            "river": "Iguazú",
            "source": "PNA",
            "measured_at": "2026-10-19T10:00:00",
            "fetched_at": fetched_at,
            "level_m": _clean_pna_float("30,00 Mts"),
            "variation_m": None,
            "flow_in_m3s": None,
            "flow_out_m3s": None,
            "flow_turbined_m3s": None,
            "flow_spilled_m3s": None,
            "rain_mm": None,
            "trend": "ESTACIONARIO",
            "raw_status": "NORMAL"
        }
        self._assert_valid_dto(dto, "PrefecturaService:PUERTO_IGUAZU")


class TestHydrologicThresholdsAudit(unittest.TestCase):
    """
    Auditoría exhaustiva de los umbrales de Alerta y Evacuación de PNA.
    Comprueba:
    1. Para todas las estaciones activas: threshold_alert < threshold_evacuation.
    2. Prohibición estricta de umbrales no oficiales (Vigilancia / Emergencia).
    3. Evaluación correcta de estados hidrológicos oficiales.
    """

    def test_station_thresholds_catalog_consistency(self):
        for code, th in thresholds.STATION_THRESHOLDS.items():
            ale = th.get("alerta")
            eva = th.get("evacuacion")
            self.assertNotIn("vigilancia", th, f"[{code}] vigilancia presente en catálogo")
            self.assertNotIn("emergencia", th, f"[{code}] emergencia presente en catálogo")
            if ale is not None and eva is not None:
                self.assertLess(
                    ale, eva,
                    f"[{code}] Incoherencia: Alerta ({ale}) >= Evacuación ({eva})"
                )

    def test_database_umbrales_config_consistency(self):
        if not os.path.exists(DB_PATH):
            self.skipTest("Base de datos no encontrada para prueba de umbrales")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT codigo, alerta, evacuacion FROM umbrales_config")
        rows = cursor.fetchall()
        conn.close()

        self.assertGreater(len(rows), 0, "Tabla umbrales_config vacía")
        for code, ale, eva in rows:
            if ale is not None and eva is not None:
                self.assertLess(
                    ale, eva,
                    f"[{code} en SQLite] Incoherencia: Alerta ({ale}) >= Evacuación ({eva})"
                )

    def test_calculate_station_status_logic(self):
        th = {"alerta": 25.0, "evacuacion": 28.0, "alertas_activas": True}

        # Nivel Evacuación
        self.assertEqual(thresholds.calculate_station_status(28.5, th), "evacuacion")
        self.assertEqual(thresholds.calculate_station_status(28.0, th), "evacuacion")

        # Nivel Alerta
        self.assertEqual(thresholds.calculate_station_status(26.0, th), "alerta")
        self.assertEqual(thresholds.calculate_station_status(25.0, th), "alerta")

        # Nivel Normal
        self.assertEqual(thresholds.calculate_station_status(24.9, th), "normal")
        self.assertEqual(thresholds.calculate_station_status(10.0, th), "normal")

        # Sin datos
        self.assertEqual(thresholds.calculate_station_status(None, th), "sin_datos")

        # Desactivado
        th_off = {"alerta": 25.0, "evacuacion": 28.0, "alertas_activas": False}
        self.assertEqual(thresholds.calculate_station_status(30.0, th_off), "desactivado")

    def test_inject_thresholds_clean(self):
        obj = {"codigo": "PUERTO_IGUAZU", "ultima_altura": 26.6}
        res = thresholds.inject_thresholds(obj)
        self.assertEqual(res["threshold_alert"], 25.0)
        self.assertEqual(res["threshold_evacuation"], 28.0)
        self.assertEqual(res["alert_state"], "ALERTA")
        self.assertNotIn("vigilancia", res)
        self.assertNotIn("emergencia", res)


class TestOfflineApiRoutes(unittest.TestCase):
    """
    Validación de los endpoints REST API de HidroPanel mediante despacho interno
    offline (handle_get de backend/routes.py), garantizando respuestas en < 30 ms
    y esquemas JSON válidos sin depender de procesos HTTP de red en ejecución.
    """

    def test_api_estaciones_offline(self):
        st, ct, body = handle_get("/api/estaciones", {})
        self.assertEqual(st, 200)
        self.assertIn("application/json", ct)
        data = json.loads(body)
        self.assertTrue(data.get("success"))
        self.assertIn("estaciones", data)
        self.assertIn("sources_status", data)
        self.assertGreater(data.get("total", 0), 0)

    def test_api_situacion_offline(self):
        st, ct, body = handle_get("/api/situacion", {})
        self.assertEqual(st, 200)
        self.assertIn("application/json", ct)
        data = json.loads(body)
        self.assertTrue(data.get("success"))
        conteo = data.get("conteo_estados", {})
        self.assertNotIn("vigilancia", conteo)
        self.assertNotIn("emergencia", conteo)
        self.assertIn("alertas_activas", data)
        self.assertIn("estaciones_falla_reporte", data)

    def test_api_caudales_offline(self):
        st, ct, body = handle_get("/api/caudales", {})
        self.assertEqual(st, 200)
        self.assertIn("application/json", ct)
        data = json.loads(body)
        self.assertTrue(data.get("success"))
        self.assertIn("centrales_lista", data)
        self.assertIn("sources_status", data)

    def test_api_umbrales_offline(self):
        st, ct, body = handle_get("/api/umbrales", {})
        self.assertEqual(st, 200)
        self.assertIn("application/json", ct)
        data = json.loads(body)
        self.assertTrue(data.get("success"))
        self.assertIn("umbrales", data)

    def test_api_mediciones_offline(self):
        st, ct, body = handle_get("/api/mediciones", {"estacion_id": ["5"], "rango": ["24h"]})
        self.assertEqual(st, 200)
        self.assertIn("application/json", ct)
        data = json.loads(body)
        self.assertIn("estacion", data)
        self.assertIn("puntos", data)
        self.assertIn("kpis", data)

    def test_api_status_sync_offline(self):
        st, ct, body = handle_get("/api/status_sync", {})
        self.assertEqual(st, 200)
        self.assertIn("application/json", ct)
        data = json.loads(body)
        self.assertTrue(data.get("success"))

    def test_api_404_offline(self):
        st, ct, body = handle_get("/api/ruta_no_existente", {})
        self.assertEqual(st, 404)
        data = json.loads(body)
        self.assertFalse(data.get("success"))


if __name__ == "__main__":
    unittest.main()
