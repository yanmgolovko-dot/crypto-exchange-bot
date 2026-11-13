# check_legacy.py
"""Проверка, что в проекте не осталось ссылок на удалённую логику комиссии сети."""
import pathlib

KEYS = [
    "waiting_network_fee",
    "get_recommended_fee",
    "MAX_FEE_SAT",
    "force_fee_sat",
    "client_network_fee",
    "network_fee_worker",
]

root = pathlib.Path("bot")
found = False
for path in root.rglob("*.py"):
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for lineno, line in enumerate(text.splitlines(), 1):
        for key in KEYS:
            if key in line:
                print(f"{path}:{lineno}: [{key}] {line.strip()}")
                found = True

if not found:
    print("OK: совпадений нет")