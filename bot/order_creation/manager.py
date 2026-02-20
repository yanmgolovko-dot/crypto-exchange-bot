# bot/order_creation/manager.py
import logging
from typing import Dict, Any, Optional
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from .dto import OrderCreationData
from .steps import OrderCreationStep, SelectCryptoStep
from .exceptions import OrderCreationError

logger = logging.getLogger(__name__)

class OrderCreationManager:
    def __init__(self, state: FSMContext, user_id: int, username: Optional[str]):
        self.state = state
        self.data = OrderCreationData(user_id=user_id, username=username)
        self.current_step: Optional[OrderCreationStep] = None

    async def start(self, message: Message, services: Dict[str, Any]):
        self.current_step = SelectCryptoStep(self.data, self.state)
        logger.info(f"[{self.data.user_id}] Запуск процесса создания заявки. Первый шаг: {self.current_step.__class__.__name__}")
        await self.current_step.display(message, services)

    async def handle_message(self, message: Message, services: Dict[str, Any]) -> bool:
        step_name = self.current_step.__class__.__name__
        logger.info(f"[{self.data.user_id}] Обработка сообщения на шаге {step_name}")
        try:
            completed = await self.current_step.process_message(message, services)
            if completed:
                logger.info(f"[{self.data.user_id}] Шаг {step_name} завершён.")
                next_step = await self.current_step.get_next_step()
                if next_step:
                    self.current_step = next_step
                    logger.info(f"[{self.data.user_id}] Переход к шагу {self.current_step.__class__.__name__}")
                    await self.current_step.display(message, services)
                    return False
                else:
                    logger.info(f"[{self.data.user_id}] Все шаги завершены.")
                    return True
            else:
                logger.info(f"[{self.data.user_id}] Шаг {step_name} ещё не завершён, ожидание дальнейших действий.")
                return False
        except OrderCreationError as e:
            logger.error(f"[{self.data.user_id}] Ошибка на шаге {step_name}: {e}", exc_info=True)
            raise

    async def handle_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        step_name = self.current_step.__class__.__name__
        logger.info(f"[{self.data.user_id}] Обработка callback {callback.data} на шаге {step_name}")
        try:
            completed = await self.current_step.process_callback(callback, services)
            if completed:
                logger.info(f"[{self.data.user_id}] Шаг {step_name} завершён (callback).")
                next_step = await self.current_step.get_next_step()
                if next_step:
                    self.current_step = next_step
                    logger.info(f"[{self.data.user_id}] Переход к шагу {self.current_step.__class__.__name__}")
                    await self.current_step.display(callback.message, services)
                    return False
                else:
                    logger.info(f"[{self.data.user_id}] Все шаги завершены.")
                    return True
            else:
                return False
        except OrderCreationError as e:
            logger.error(f"[{self.data.user_id}] Ошибка на шаге {step_name}: {e}", exc_info=True)
            raise