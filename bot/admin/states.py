from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    # Настройки
    changing_fee = State()
    changing_min = State()
    changing_max = State()

    # Банковские карты
    adding_bank_card = State()
    adding_bank_name = State()
    adding_bank_holder = State()
    adding_bank_limit = State()

    # Промокоды
    creating_promo_code = State()
    creating_promo_discount = State()
    creating_promo_uses = State()
    creating_promo_days = State()

    # Пользователи
    banning_user = State()
    banning_reason = State()
    unbanning_user = State()
    searching_user = State()          # состояние для поиска пользователя

    # Рассылка
    sending_broadcast = State()

    # Финансы
    adding_expense = State()
    adding_expense_desc = State()

    # Кошельки
    adding_wallet_type = State()
    adding_wallet_address = State()
    adding_wallet_key = State()
    adding_wallet_label = State()
    sending_crypto = State()

    # Сообщение клиенту
    sending_message_to_user = State()

    # Ручной режим (ввод реквизитов)
    entering_manual_payment_details = State()

    # Ввод хеша транзакции
    waiting_tx_hash = State()

    # Поиск заявки
    searching_order = State()