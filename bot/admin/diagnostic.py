import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.services.diagnostic import run_diagnostics
from bot.admin.main import is_admin

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "admin_diagnostic")
async def admin_diagnostic(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer("🔍 Запуск диагностики...", show_alert=False)
    status_msg = await callback.message.answer(
        "🔄 Запускаю диагностику системы, это может занять несколько секунд..."
    )

    try:
        result = await run_diagnostics(callback.from_user.id, callback.bot)
        await status_msg.edit_text(result.to_text(), parse_mode="HTML")

        if result.errors:
            logger.warning(f"Диагностика выявила ошибки: {result.errors}")
    except Exception as e:
        logger.exception("Ошибка при выполнении диагностики")
        await status_msg.edit_text(f"❌ Произошла ошибка при выполнении диагностики: {e}")