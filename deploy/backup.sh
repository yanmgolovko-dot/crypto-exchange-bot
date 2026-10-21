#!/usr/bin/env bash
# Бэкап БД SQLite и папки с чеками.
# Запускается из cron раз в сутки.

set -euo pipefail

PROJECT_DIR="/opt/crypto-bot"
BACKUP_DIR="/opt/crypto-bot/backups"
DB_PATH="${PROJECT_DIR}/data/exchange.db"
RECEIPTS_DIR="${PROJECT_DIR}/data/receipts"
DATE="$(date +%Y-%m-%d_%H-%M-%S)"
KEEP_DAYS=7

mkdir -p "${BACKUP_DIR}"

# 1) Бэкап SQLite через VACUUM INTO — безопасно даже при работающем боте.
if [ -f "${DB_PATH}" ]; then
    DB_BACKUP="${BACKUP_DIR}/exchange_${DATE}.db"
    sqlite3 "${DB_PATH}" ".backup '${DB_BACKUP}'" 2>/dev/null || \
        sqlite3 "${DB_PATH}" "VACUUM INTO '${DB_BACKUP}'"
    gzip -f "${DB_BACKUP}"
    echo "[$(date)] DB backup: ${DB_BACKUP}.gz"
else
    echo "[$(date)] DB not found: ${DB_PATH}" >&2
fi

# 2) Бэкап чеков
if [ -d "${RECEIPTS_DIR}" ]; then
    RECEIPTS_ARCHIVE="${BACKUP_DIR}/receipts_${DATE}.tar.gz"
    tar -czf "${RECEIPTS_ARCHIVE}" -C "${PROJECT_DIR}/data" receipts
    echo "[$(date)] Receipts backup: ${RECEIPTS_ARCHIVE}"
fi

# 3) Ротация: удаляем бэкапы старше KEEP_DAYS
find "${BACKUP_DIR}" -type f -name "*.gz" -mtime +${KEEP_DAYS} -delete
echo "[$(date)] Old backups cleaned (keep ${KEEP_DAYS} days)"