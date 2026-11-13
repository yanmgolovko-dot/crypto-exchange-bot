# bot/order_creation/dto.py
"""
Data Transfer Objects (DTO) для передачи данных между шагами создания заявки.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OrderCreationData:
    """Хранит все данные, собранные в процессе создания заявки."""
    user_id: int
    username: Optional[str] = None
    crypto_type: Optional[str] = None
    input_type: Optional[str] = None
    amount: Optional[float] = None
    promo_code: Optional[str] = None
    discount_percent: float = 0.0
    wallet_address: Optional[str] = None
    rate: Optional[float] = None
    gross_amount: Optional[float] = None
    net_amount: Optional[float] = None
    amount_crypto: Optional[float] = None
    fee_percent: Optional[float] = None
    order_id: Optional[int] = None
    public_order_number: Optional[int] = None

    # Финансовая разбивка (для финансовых записей)
    commission_rub: float = 0.0
    network_fee_rub: float = 0.0
    network_fee_crypto: float = 0.0

    # Флаги для навигации "Назад"
    back_to_crypto: bool = False
    back_to_currency: bool = False
    back_to_main: bool = False
    back_to_amount: bool = False
    back_to_promo: bool = False

    # Купон
    coupon_id: Optional[int] = None
    coupon_code: Optional[str] = None
    coupon_discount_type: Optional[str] = None
    coupon_discount_value: Optional[float] = None
    coupon_discount_on: Optional[str] = None