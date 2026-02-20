# bot/order_creation/exceptions.py
"""
Специфичные исключения для процесса создания заявки.
"""

class OrderCreationError(Exception):
    """Базовое исключение для всех ошибок создания заявки."""
    pass

class ValidationError(OrderCreationError):
    """Ошибка валидации введённых данных (например, неверный адрес, сумма вне лимитов)."""
    pass

class StepError(OrderCreationError):
    """Ошибка выполнения шага (например, не удалось получить курс)."""
    pass