# bot/admin/states.py
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
    searching_user = State()

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

    # Ручной режим (ввод реквизитов для оплаты рублями)
    entering_manual_payment_details = State()

    # Ввод адреса кошелька для P2P Sell
    entering_p2p_wallet_address = State()

    # Ввод хеша транзакции
    waiting_tx_hash = State()

    # Поиск заявки
    searching_order = State()

    # Купоны
    creating_coupon_code = State()
    creating_coupon_discount_type = State()
    creating_coupon_discount_value = State()
    creating_coupon_discount_on = State()
    creating_coupon_limits = State()
    creating_coupon_valid_days = State()
    creating_coupon_description = State()

    # Настройка приветственных купонов
    editing_welcome_discount_type = State()
    editing_welcome_value = State()
    editing_welcome_discount_on = State()
    editing_welcome_valid_days = State()
    editing_welcome_description = State()

    # Настройка купонов за активность
    adding_activity_threshold_orders = State()
    adding_activity_threshold_discount_type = State()
    adding_activity_threshold_value = State()
    adding_activity_threshold_discount_on = State()
    adding_activity_threshold_valid_days = State()
    editing_activity_threshold_index = State()

    setting_next_order_number = State()

    # Курсы обмена (P2P)
    waiting_for_new_rate = State()

    # Реферальные ссылки
    waiting_for_target_user = State()
    waiting_for_new_ref_code = State()