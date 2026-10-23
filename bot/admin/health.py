# bot/admin/health.py
"""
Health-check для админов: /health.

Проверяет:
- доступность БД и размер файла;
- распределение заявок по статусам;
- доступность внешнего API курсов;
- свободное место на диске;
- размер папки data/receipts;
- uptime процесса с момента старта.
"""

import html
import logging
import os
import shutil
import time
from datetime import datetime
from typing import Optional

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.admin.main import is_admin
from bot.config.settings import config
from bot.services.db import db
from bot.services.crypto_api import crypto_api

logger = logging.getLogger(__name__)
router = Router()

# Корень проекта и папка с чеками
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_RECEIPTS_DIR = os.path.join(_PROJECT_ROOT, "data", "receipts")

# Порог «диск почти полон», в процентах занятого места
DISK_WARN_PERCENT = 90.0


def _human_size(num_bytes: float) -> str:
    """Человекочитаемый размер."""
    n = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def _human_duration(seconds: float) -> str:
    """Человекочитаемая длительность."""
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d:
        parts.append(f"{d}д")
    if h:
        parts.append(f"{h}ч")
    if m:
        parts.append(f"{m}м")
    parts.append(f"{s}с")
    return " ".join(parts)


def _status_emoji(ok: bool) -> str:
    return "✅" if ok else "❌"


async def _check_db() -> dict:
    """
    Проверяет БД:
    - выполняет SELECT 1;
    - считает заявки по статусам;
    - возвращает размер файла БД.
    """
    result = {
        "ok": False,
        "error": None,
        "size": 0,
        "counts": {},
    }
    try:
        # Простейший ping
        async with db.uow() as uow:
            cursor = await uow._connection.conn.execute("SELECT 1")
            await cursor.fetchone()

        # Распределение по статусам (только реально существующие)
        statuses = ("pending", "paid", "processing", "completed", "cancelled")
        counts = {}
        async with db.uow() as uow:
            for status in statuses:
                cursor = await uow._connection.conn.execute(
                    "SELECT COUNT(*) FROM exchange_orders WHERE status = ?", (status,)
                )
                row = await cursor.fetchone()
                counts[status] = int(row[0]) if row else 0

        result["counts"] = counts
        result["ok"] = True

        # Размер файла БД
        db_path = config.DB_PATH
        if not os.path.isabs(db_path):
            db_path = os.path.join(_PROJECT_ROOT, db_path)
        if os.path.exists(db_path):
            result["size"] = os.path.getsize(db_path)
    except Exception as e:
        logger.error(f"/health: ошибка проверки БД: {e}", exc_info=True)
        result["error"] = f"{type(e).__name__}: {e}"
    return result


async def _check_rates() -> dict:
    """
    Проверяет доступность внешнего API курсов:
    - получает BTC/RUB, LTC/RUB, USD/RUB с таймаутом (внутри crypto_api).
    """
    result = {
        "ok": False,
        "error": None,
        "btc": None,
        "ltc": None,
        "usd": None,
    }
    try:
        btc, ltc, usd = await _asyncio_gather_rates()
        result["btc"] = btc
        result["ltc"] = ltc
        result["usd"] = usd
        result["ok"] = all(v is not None for v in (btc, ltc, usd))
        if not result["ok"]:
            result["error"] = "Один или несколько курсов не получены"
    except Exception as e:
        logger.error(f"/health: ошибка проверки курсов: {e}", exc_info=True)
        result["error"] = f"{type(e).__name__}: {e}"
    return result


async def _asyncio_gather_rates():
    """Параллельно запрашивает три курса, чтобы /health не висел долго."""
    import asyncio
    btc_task = asyncio.create_task(_safe_call(crypto_api.get_btc_price_rub))
    ltc_task = asyncio.create_task(_safe_call(crypto_api.get_ltc_price_rub))
    usd_task = asyncio.create_task(_safe_call(crypto_api.get_usdt_rub))
    return await asyncio.gather(btc_task, ltc_task, usd_task)


async def _safe_call(fn) -> Optional[float]:
    try:
        return await fn()
    except Exception as e:
        logger.warning(f"/health: вызов {getattr(fn, '__name__', fn)} упал: {e}")
        return None


def _check_disk() -> dict:
    """Свободное место на разделе, где лежит проект."""
    try:
        usage = shutil.disk_usage(_PROJECT_ROOT)
        used_percent = (usage.used / usage.total) * 100 if usage.total else 0
        return {
            "ok": used_percent < DISK_WARN_PERCENT,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "used_percent": used_percent,
            "error": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "total": 0,
            "used": 0,
            "free": 0,
            "used_percent": 0,
            "error": f"{type(e).__name__}: {e}",
        }


def _check_receipts_dir() -> dict:
    """Суммарный размер и количество файлов в data/receipts."""
    try:
        if not os.path.isdir(_RECEIPTS_DIR):
            return {"ok": True, "files": 0, "size": 0, "error": None, "exists": False}
        files = 0
        size = 0
        for name in os.listdir(_RECEIPTS_DIR):
            path = os.path.join(_RECEIPTS_DIR, name)
            if os.path.isfile(path):
                files += 1
                size += os.path.getsize(path)
        return {"ok": True, "files": files, "size": size, "error": None, "exists": True}
    except Exception as e:
        return {
            "ok": False,
            "files": 0,
            "size": 0,
            "error": f"{type(e).__name__}: {e}",
            "exists": False,
        }


def _get_uptime_seconds() -> Optional[float]:
    """
    Uptime процесса. Берём PROCESS_START_TIME из bot.main,
    если он там определён. Иначе None.
    """
    try:
        from bot.main import PROCESS_START_TIME
        return max(0.0, time.time() - PROCESS_START_TIME)
    except Exception:
        return None


@router.message(Command("health"))
async def cmd_health(message: Message):
    """Health-check бота. Только для админов."""
    admin_id = message.from_user.id
    if not await is_admin(admin_id):
        # Не раскрываем существование команды неадминам
        logger.warning(f"[HEALTH] Попытка /health от неадмина {admin_id}")
        await message.answer("⛔ Команда доступна только администраторам.")
        return

    logger.info(f"[HEALTH] Запрос /health от админа {admin_id}")

    started_at = time.time()
    db_result = await _check_db()
    rates_result = await _check_rates()
    disk_result = _check_disk()
    receipts_result = _check_receipts_dir()
    uptime = _get_uptime_seconds()
    elapsed = time.time() - started_at

    overall_ok = (
        db_result["ok"]
        and rates_result["ok"]
        and disk_result["ok"]
        and receipts_result["ok"]
    )
    status = "🟢 <b>OK</b>" if overall_ok else "🟡 <b>Есть проблемы</b>"

    lines = [f"{status} | <b>Health-check</b>", ""]

    # --- БД ---
    if db_result["ok"]:
        counts = db_result["counts"]
        counts_str = " · ".join(
            f"{k}: {v}" for k, v in counts.items() if v
        ) or "нет заявок"
        lines.append(
            f"{_status_emoji(True)} <b>БД</b> — OK, "
            f"размер {_human_size(db_result['size'])}"
        )
        lines.append(f"   <i>{html.escape(counts_str)}</i>")
    else:
        lines.append(
            f"{_status_emoji(False)} <b>БД</b> — ошибка: "
            f"{html.escape(str(db_result['error'])[:200])}"
        )

    # --- Курсы ---
    if rates_result["ok"]:
        lines.append(
            f"{_status_emoji(True)} <b>Курсы</b> — "
            f"BTC {rates_result['btc']:,.0f} ₽ · "
            f"LTC {rates_result['ltc']:,.0f} ₽ · "
            f"USD {rates_result['usd']:.2f} ₽"
        )
    else:
        lines.append(
            f"{_status_emoji(False)} <b>Курсы</b> — "
            f"{html.escape(str(rates_result['error'])[:200] or 'не получены')}"
        )

    # --- Диск ---
    if disk_result["error"] is None:
        lines.append(
            f"{_status_emoji(disk_result['ok'])} <b>Диск</b> — "
            f"свободно {_human_size(disk_result['free'])} "
            f"({disk_result['used_percent']:.1f}% занято)"
        )
    else:
        lines.append(
            f"{_status_emoji(False)} <b>Диск</b> — ошибка: "
            f"{html.escape(str(disk_result['error'])[:200])}"
        )

    # --- Чеки ---
    if receipts_result["ok"]:
        if receipts_result["exists"]:
            lines.append(
                f"{_status_emoji(True)} <b>Чеки</b> — "
                f"{receipts_result['files']} файлов, "
                f"{_human_size(receipts_result['size'])}"
            )
        else:
            lines.append(
                f"{_status_emoji(True)} <b>Чеки</b> — папка пустая или отсутствует"
            )
    else:
        lines.append(
            f"{_status_emoji(False)} <b>Чеки</b> — ошибка: "
            f"{html.escape(str(receipts_result['error'])[:200])}"
        )

    # --- Uptime и время ответа ---
    lines.append("")
    if uptime is not None:
        lines.append(f"⏱ Uptime: {_human_duration(uptime)}")
    else:
        lines.append("⏱ Uptime: n/a (PROCESS_START_TIME не найден)")
    lines.append(f"🕒 Проверка заняла {elapsed * 1000:.0f} мс")
    lines.append(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    await message.answer("\n".join(lines), parse_mode="HTML")
    logger.info(f"[HEALTH] Ответ отправлен, общее состояние: {'OK' if overall_ok else 'PROBLEMS'}")