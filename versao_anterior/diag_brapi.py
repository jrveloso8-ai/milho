# -*- coding: utf-8 -*-
"""
diag_brapi.py — Diagnóstico pontual do formato de resposta da BRAPI.
Rode uma vez, me mande o output completo, e eu corrijo o parser
de listar_contratos_ccm_ativos() e contrato_wdo_vigente() no
brapi_milho.py de forma definitiva (sem mais tentativa e erro).

Uso:
    python diag_brapi.py
"""
import os
import json
import requests

TOKEN = os.environ.get("BRAPI_TOKEN")
if not TOKEN:
    print("ERRO: BRAPI_TOKEN não definido.")
    exit(1)

HEADERS = {"Authorization": f"Bearer {TOKEN}"}
BASE = "https://brapi.dev/api"

print("=" * 70)
print("1) /v2/futures/list?asset=CCM")
print("=" * 70)
r = requests.get(f"{BASE}/v2/futures/list", headers=HEADERS,
                  params={"asset": "CCM", "includeExpired": "false"})
print(f"Status: {r.status_code}")
print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:3000])

print()
print("=" * 70)
print("2) /v2/futures/list?asset=WDO")
print("=" * 70)
r2 = requests.get(f"{BASE}/v2/futures/list", headers=HEADERS,
                   params={"asset": "WDO", "includeExpired": "false"})
print(f"Status: {r2.status_code}")
print(json.dumps(r2.json(), ensure_ascii=False, indent=2)[:3000])

print()
print("=" * 70)
print("3) /v2/futures/term-structure?asset=CCM  (endpoint alternativo, se existir)")
print("=" * 70)
r3 = requests.get(f"{BASE}/v2/futures/term-structure", headers=HEADERS,
                   params={"asset": "CCM"})
print(f"Status: {r3.status_code}")
try:
    print(json.dumps(r3.json(), ensure_ascii=False, indent=2)[:3000])
except Exception as e:
    print(f"(resposta não-JSON ou erro: {e})")
    print(r3.text[:1000])
