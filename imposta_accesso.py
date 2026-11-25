"""Imposta la password per aprire la dashboard dagli altri dispositivi della rete di casa.

Uso (terminale, una volta sola, e ogni volta che vuoi cambiarla):
    python imposta_accesso.py
Salva solo un hash PBKDF2 in accesso.json, mai la password in chiaro.
"""
import getpass, hashlib, json, os
from pathlib import Path

ACCESSO = Path(__file__).resolve().with_name("accesso.json")

p1 = getpass.getpass("Nuova password: ")
p2 = getpass.getpass("Ripeti password: ")
if p1 != p2:
    raise SystemExit("Le password non coincidono.")
if len(p1) < 8:
    raise SystemExit("Usa almeno 8 caratteri.")
sale = os.urandom(16)
iter_ = 300_000
h = hashlib.pbkdf2_hmac("sha256", p1.encode("utf-8"), sale, iter_)
ACCESSO.write_text(json.dumps({"sale": sale.hex(), "iter": iter_, "hash": h.hex()}), encoding="utf-8")
print("Password salvata. Riavvia 'Claude Code Analytics' dal Desktop.")
