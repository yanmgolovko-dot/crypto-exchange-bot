# bot/handlers/spin.py
import logging
import json
import random
import string
from aiogram import Router, F
from aiogram.types import Message

from bot.services.db import db

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "🎰 Колесо Фортуны")
async def spin_wheel(message: Message):
    user_id = message.from_user.id
    
    # 1. Проверяем наличие спинов
    spins = await db.get_available_spins(user_id)
    if spins <= 0:
        await message.answer(
            "❌ У вас нет доступных прокруток.\n\n"
            "🎁 Прокрутки даются за каждые N успешных обменов! "
            "Совершайте обмены, чтобы получить шанс выиграть приз."
        )
        return

    # 2. Списываем спин
    success = await db.use_spin(user_id)
    if not success:
        await message.answer("❌ Ошибка. Попробуйте позже.")
        return

    # 3. Отправляем кубик
    dice_msg = await message.answer_dice(emoji="🎰")
    value = dice_msg.dice.value  # Значение от 1 до 64
    
    logger.info(f"[SPIN] Пользователь {user_id} крутит колесо. Выпало: {value}")

    # 4. Читаем конфиг призов
    prizes_json = await db.get_setting('spin_prizes', '[]')
    try:
        prizes = json.loads(prizes_json)
    except Exception:
        prizes = []

    # 5. Ищем выигрыш
    won_prize = None
    for p in prizes:
        if p['min'] <= value <= p['max']:
            won_prize = p
            break

    if not won_prize:
        won_prize = {"type": "nothing", "text": "Пусто"}

    # 6. Обрабатываем выигрыш
    prize_text = won_prize.get('text', 'Неизвестно')
    
    if won_prize['type'] == 'coupon':
        discount = won_prize['value']
        code = f"SPIN{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"
        await db.create_coupon(
            code=code,
            discount_type='percent',
            discount_value=discount,
            discount_on='commission',
            max_uses_total=1,
            max_uses_per_user=1,
            owner_id=user_id,
            coupon_type='spin',
            description=f"Выигрыш в колесе фортуны (слот {value})"
        )
        prize_text = f"🎫 <b>Купон на скидку {discount}%</b>\nКод: <code>{code}</code> (уже в вашем профиле)"

    elif won_prize['type'] == 'balance':
        amount = won_prize['value']
        await db.add_bonus_balance(user_id, amount)
        prize_text = f"💰 <b>{amount} ₽</b> зачислено на ваш бонусный баланс!"

    elif won_prize['type'] == 'nothing':
        prize_text = "😢 Пусто. Попробуйте в следующий раз!"

    # 7. Отправляем результат
    spins_left = await db.get_available_spins(user_id)
    
    text = (
        f"🎰 <b>Колесо Фортуны</b>\n\n"
        f"Выпало число: <b>{value}</b>\n\n"
        f"🎁 <b>Ваш приз:</b>\n{prize_text}\n\n"
    )
    if spins_left > 0:
        text += f"🎟 У вас осталось прокруток: <b>{spins_left}</b>"
    else:
        text += f"🎟 Прокруток больше нет. Совершайте обмены, чтобы заработать еще!"

    await message.answer(text, parse_mode="HTML")