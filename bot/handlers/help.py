# bot/handlers/help.py
"""
Обработчики для раздела помощи и поддержки.
Содержит функции для отображения меню помощи, ответов на часто задаваемые вопросы
и отправки контактной информации поддержки.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards import help_keyboard
from bot.utils.helpers import safe_edit_message, escape_html

# Настройка логгера для текущего модуля
logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "❓ Помощь")
async def help_menu(message: Message):
    """
    Обработчик нажатия кнопки «❓ Помощь» в главном меню.
    Отправляет пользователю список доступных разделов помощи в виде инлайн-кнопок.
    """
    user_id = message.from_user.id
    logger.info(f"[{user_id}] Пользователь открыл раздел помощи")

    text = (
        "❓ <b>Раздел помощи</b>\n\n"
        "Выберите интересующий вас вопрос:"
    )

    await message.answer(text, reply_markup=help_keyboard(), parse_mode="HTML")
    logger.debug(f"[{user_id}] Отправлено меню помощи с клавиатурой")


@router.message(F.text == "💬 Поддержка")
async def support(message: Message):
    """
    Обработчик нажатия кнопки «💬 Поддержка» в главном меню.
    Отправляет пользователю контактные данные службы поддержки.
    """
    user_id = message.from_user.id
    logger.info(f"[{user_id}] Пользователь запросил контакты поддержки")

    text = (
        "💬 <b>Поддержка</b>\n\n"
        "Если у вас возникли вопросы или проблемы, напишите нам:\n\n"
        # Используем кликабельные ссылки для удобства пользователей
        "💬 <a href='https://t.me/arb_p2'>@arb_p2</a>\n"
        "💬 <a href='https://t.me/BORZZ975'>@BORZZ975</a>\n\n"
        "⏱ Время работы поддержки: 24/7"
    )

    await message.answer(text, parse_mode="HTML")
    logger.debug(f"[{user_id}] Отправлены контакты поддержки")


@router.callback_query(F.data.startswith("help_"))
async def help_callback(callback: CallbackQuery):
    """
    Обработчик нажатий на инлайн-кнопки в разделе помощи.
    Извлекает тему из callback_data и отправляет соответствующий текст.
    """
    user_id = callback.from_user.id
    topic = callback.data.split("_", 1)[1]  # получаем тему (например, "how_to_buy")
    logger.info(f"[{user_id}] Пользователь выбрал тему помощи: {topic}")

    # Словарь с текстами для каждой темы
    texts = {
        "how_to_buy": (
            "📝 <b>Как купить криптовалюту</b>\n\n"
            "1. Нажмите «💰 Купить криптовалюту»\n"
            "2. Выберите криптовалюту (BTC или LTC)\n"
            "3. Выберите, в какой валюте ввести сумму: рубли или криптовалюта\n"
            "4. Введите желаемую сумму получения (в рублях или крипте)\n"
            "5. Система автоматически рассчитает итоговую сумму к оплате (округлённую до 100 рублей)\n"
            "6. Введите адрес вашего кошелька (поддерживаются все форматы, включая Bech32)\n"
            "7. Получите реквизиты для оплаты (автоматически или от администратора)\n"
            "8. Переведите нужную сумму на указанные реквизиты\n"
            "9. Отправьте PDF-чек об оплате\n"
            "10. Ожидайте поступления криптовалюты (5-15 минут)"
        ),
        "processing_time": (
            "⏱ <b>Время обработки</b>\n\n"
            "• Создание заявки: мгновенно\n"
            "• Проверка оплаты: 5-15 минут\n"
            "• Отправка криптовалюты: 1-5 минут\n\n"
            "В редких случаях при высокой нагрузке время может увеличиться."
        ),
        "payment_methods": (
            "💳 <b>Способы оплаты</b>\n\n"
            "Мы принимаем переводы на банковские карты или по номеру телефона.\n"
            "Реквизиты предоставляются при создании заявки.\n\n"
            "Поддерживаются переводы с карт любых банков РФ."
        ),
        "security": (
            "🔐 <b>Безопасность</b>\n\n"
            "• Все данные шифруются\n"
            "• Кошельки проверяются перед отправкой\n"
            "• Чеки хранятся в защищенном виде\n"
            "• Поддержка 24/7\n\n"
            "Если у вас есть сомнения, всегда можно обратиться в поддержку."
        )
    }

    # Получаем текст по теме или сообщение по умолчанию
    text = texts.get(topic, "Информация не найдена")
    logger.debug(f"[{user_id}] Текст для темы {topic} подготовлен")

    # Создаём клавиатуру для возврата в меню помощи
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="back_to_help")

    # Отправляем/редактируем сообщение с текстом и кнопкой возврата
    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    logger.debug(f"[{user_id}] Сообщение с темой {topic} отправлено")
    await callback.answer()


@router.callback_query(F.data == "back_to_help")
async def back_to_help(callback: CallbackQuery):
    """
    Обработчик кнопки «🔙 Назад» из подразделов помощи.
    Возвращает пользователя к основному меню помощи.
    """
    user_id = callback.from_user.id
    logger.info(f"[{user_id}] Пользователь вернулся в главное меню помощи")

    text = (
        "❓ <b>Раздел помощи</b>\n\n"
        "Выберите интересующий вас вопрос:"
    )
    # Заменяем текущее сообщение на меню помощи
    await safe_edit_message(callback.message, text, reply_markup=help_keyboard(), parse_mode="HTML")
    logger.debug(f"[{user_id}] Главное меню помощи восстановлено")
    await callback.answer()