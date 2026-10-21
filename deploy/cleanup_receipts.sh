#!/usr/bin/env bash
# Удаляет PDF-чеки старше N дней. По умолчанию — 30.
# Запускается из cron раз в неделю.

set -euo pipefail

RECEIPTS_DIR="/opt/crypto-bot/data/receipts"
KEEP_DAYS=30

if [ ! -d "${RECEIPTS_DIR}" ]; then
    echo "[$(date)] Receipts dir not found: ${RECEIPTS_DIR}" >&2
    exit 0
fi

BEFORE=$(find "${RECEIPTS_DIR}" -type f -name "*.pdf" | wc -l)
find "${RECEIPTS_DIR}" -type f -name "*.pdf" -mtime +${KEEP_DAYS} -delete
AFTER=$(find "${RECEIPTS_DIR}" -type f -name "*.pdf" | wc -l)

echo "[$(date)] Receipts cleanup: ${BEFORE} -> ${AFTER} (deleted $((BEFORE - AFTER)) files older than ${KEEP_DAYS} days)"