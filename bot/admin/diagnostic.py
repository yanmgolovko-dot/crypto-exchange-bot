# bot/admin/diagnostic.py
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.services.diagnostic import run_diagnostics
from bot.admin.main import is_admin
from bot.utils.helpers import safe_edit_message, escape_html

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "admin_diagnostic")
async def admin_diagnostic(callback: CallbackQuery):
    """
    Запускает диагностику системы по нажатию на кнопку в админ-панели.
    """
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        logger.warning(f"[ADMIN {admin_id}] Попытка запуска диагностики без прав")
        return

    logger.info(f"[ADMIN {admin_id}] Запуск диагностики системы")
    await callback.answer("🔍 Запуск диагностики...", show_alert=False)
    status_msg = await callback.message.answer(
        "🔄 Запускаю диагностику системы, это может занять несколько секунд..."
    )

    try:
        result = await run_diagnostics(callback.from_user.id, callback.bot)
        await safe_edit_message(status_msg, result.to_text(), parse_mode="HTML")
        logger.info(f"[ADMIN {admin_id}] Диагностика завершена, ошибок: {len(result.errors)}")
        if result.errors:
            logger.warning(f"[ADMIN {admin_id}] Диагностика выявила ошибки: {result.errors}")
    except Exception as e:
        logger.exception(f"[ADMIN {admin_id}] Ошибка при выполнении диагностики: {e}")
        error_text = f"❌ Произошла ошибка при выполнении диагностики: {escape_html(str(e))}"
        await safe_edit_message(status_msg, error_text, parse_mode="HTML")