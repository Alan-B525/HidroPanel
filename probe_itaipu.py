#!/usr/bin/env python3
"""
probe_itaipu.py
Sonda de diagnóstico y captura de telemetría hidrológica de Itaipú Binacional.
Retorna registros validados bajo el CONTRATO DTO UNIFICADO.
"""

import sys
import os
import json
import ssl
import urllib.request
from datetime import datetime
from typing import Dict, Any, List, Optional

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

def probe_itaipu_dto() -> List[Dict[str, Any]]:
    """Consulta la telemetría oficial más reciente de Itaipú Binacional."""
    from backend.services.represas_service import get_hydraulic_summary, clean_num

    summary = get_hydraulic_summary()
    it = summary.get("itaipu", {})
    fetched_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    t_raw = it.get("fecha")
    if t_raw and " " in t_raw:
        measured_at = t_raw.replace(" ", "T")
    elif t_raw:
        measured_at = str(t_raw)
    else:
        measured_at = fetched_at

    record = {
        "station_id": "PNITAI",
        "station_name": "Itaipú Binacional",
        "river": "Paraná",
        "source": "ITAIPU",
        "measured_at": measured_at,
        "fetched_at": fetched_at,
        "level_m": clean_num(it.get("cota")),
        "variation_m": None,
        "flow_in_m3s": clean_num(it.get("afluente")),
        "flow_out_m3s": clean_num(it.get("defluente")),
        "flow_turbined_m3s": clean_num(it.get("turbinada")),
        "flow_spilled_m3s": clean_num(it.get("vertida")),
        "rain_mm": None,
        "trend": None,
        "raw_status": "OPERATIVA"
    }

    return [record]

if __name__ == "__main__":
    itaipu_records = probe_itaipu_dto()
    print(json.dumps(itaipu_records, indent=2, ensure_ascii=False))
