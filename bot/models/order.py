from pydantic import BaseModel, Field, validator
from typing import Optional

class OrderCreate(BaseModel):
    user_id: int
    crypto_type: str
    amount: float
    input_type: str  # 'rub' or 'crypto'
    wallet_address: str
    promo_code: Optional[str] = None

    @validator('crypto_type')
    def validate_crypto_type(cls, v):
        if v not in ('BTC', 'LTC'):
            raise ValueError('crypto_type must be BTC or LTC')
        return v

    @validator('input_type')
    def validate_input_type(cls, v):
        if v not in ('rub', 'crypto'):
            raise ValueError('input_type must be rub or crypto')
        return v

    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('amount must be positive')
        return v