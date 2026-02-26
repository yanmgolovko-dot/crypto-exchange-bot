# bot/order_creation/dto.py
"""
Data Transfer Objects (DTO) для передачи данных между шагами создания заявки.
Содержит класс OrderCreationData, который хранит все собранные данные.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OrderCreationData:
    """
    Хранит все данные, собранные в процессе создания заявки.
    Поля заполняются последовательно на разных шагах.
    """
    user_id: int                       # ID пользователя в Telegram
    username: Optional[str] = None      # username пользователя
    crypto_type: Optional[str] = None   # выбранная криптовалюта ('BTC' или 'LTC')
    input_type: Optional[str] = None    # тип ввода ('rub' или 'crypto')
    amount: Optional[float] = None      # введённая сумма (в рублях или крипте)
    promo_code: Optional[str] = None    # введённый промокод (если есть)
    discount_percent: float = 0.0       # размер скидки по промокоду
    wallet_address: Optional[str] = None # адрес кошелька пользователя
    rate: Optional[float] = None        # курс на момент расчёта
    gross_amount: Optional[float] = None # итоговая сумма к оплате (с комиссией)
    net_amount: Optional[float] = None   # сумма к получению (без комиссии)
    amount_crypto: Optional[float] = None # количество криптовалюты к выдаче
    fee_percent: Optional[float] = None  # применённая комиссия (с учётом скидки)
    order_id: Optional[int] = None       # ID созданной заявки (внутренний)
    public_order_number: Optional[int] = None  # публичный номер заявки

    # Флаги для навигации "Назад"
    back_to_crypto: bool = False        # вернуться к выбору криптовалюты
    back_to_currency: bool = False      # вернуться к выбору валюты ввода
    back_to_main: bool = False          # вернуться в главное меню (обрабатывается отдельно)
    back_to_amount: bool = False        # вернуться к выбору суммы
    back_to_promo: bool = False         # вернуться к вводу промокода

    # Купон
    coupon_id: Optional[int] = None          # ID применённого купона
    coupon_code: Optional[str] = None        # код купона (для отображения)
    coupon_discount_type: Optional[str] = None  # 'percent' или 'fixed'
    coupon_discount_value: Optional[float] = None
    coupon_discount_on: Optional[str] = None    # 'order' или 'commission'