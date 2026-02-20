# bot/order_creation/states.py
"""
Состояния FSM для процессов, связанных с заявками.
Используются как в модульной системе создания заявки (через OrderCreationManager),
так и для дополнительных операций (например, загрузка чека).
"""

from aiogram.fsm.state import State, StatesGroup


class ExchangeStates(StatesGroup):
    """
    Состояния для процесса создания заявки и загрузки чека.
    """
    # Основные шаги создания заявки (используются в order_creation/steps.py)
    selecting_crypto = State()          # выбор криптовалюты
    selecting_currency = State()        # выбор валюты ввода (рубли/крипта)
    selecting_amount = State()          # выбор предустановленной суммы
    entering_custom_amount = State()    # ввод своей суммы в рублях
    entering_crypto_amount = State()    # ввод суммы в крипте
    entering_promo = State()            # ввод промокода
    entering_wallet = State()           # ввод адреса кошелька
    waiting_for_payment = State()       # ожидание оплаты (после создания заявки)

    # Дополнительные операции
    uploading_receipt = State()          # загрузка чека