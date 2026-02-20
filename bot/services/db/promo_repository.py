# bot/services/db/promo_repository.py
"""Репозиторий для работы с промокодами."""

import logging
from typing import Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

from .base import BaseRepository, db_retry
import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class PromoCode:
    id: int
    code: str
    discount_percent: float
    max_uses: int
    used_count: int
    valid_from: str
    valid_to: str
    is_active: bool
    created_by: int
    created_at: str          # добавлено поле created_at
    description: Optional[str]


class PromoRepository(BaseRepository):
    """
    Репозиторий для работы с таблицей promo_codes.
    Содержит методы для создания, получения, валидации и использования промокодов.
    """

    @db_retry()
    async def create_promo_code(self, code: str, discount_percent: float,
                                 max_uses: int = 100, valid_days: int = 30,
                                 created_by: int = None, description: str = None) -> int:
        """
        Создаёт новый промокод.
        :param code: код промокода (будет преобразован в верхний регистр)
        :param discount_percent: размер скидки в процентах
        :param max_uses: максимальное количество использований
        :param valid_days: срок действия в днях от текущего момента
        :param created_by: ID администратора, создавшего промокод
        :param description: описание
        :return: ID созданного промокода
        """
        code_upper = code.upper()
        logger.info(f"Создание промокода {code_upper}, скидка {discount_percent}%, макс. использований {max_uses}, дней {valid_days}")
        async with self.lock:
            valid_to = (datetime.now() + timedelta(days=valid_days)).isoformat()
            cursor = await self.conn.execute("""
                INSERT INTO promo_codes 
                (code, discount_percent, max_uses, valid_to, created_by, description)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (code_upper, discount_percent, max_uses, valid_to, created_by, description))
            await self.conn.commit()
            promo_id = cursor.lastrowid
            logger.info(f"Промокод создан, ID: {promo_id}")
            return promo_id

    @db_retry()
    async def get_promo_code(self, code: str) -> Optional[PromoCode]:
        """Получает промокод по его коду (без учёта регистра)."""
        code_upper = code.upper()
        logger.debug(f"Запрос промокода {code_upper}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM promo_codes WHERE code = ?", (code_upper,)
            )
            row = await cursor.fetchone()
            if row:
                logger.debug(f"Промокод {code_upper} найден, ID {row['id']}")
                return PromoCode(**dict(row))
            logger.debug(f"Промокод {code_upper} не найден")
            return None

    @db_retry()
    async def validate_promo_code(self, code: str, user_id: int) -> Tuple[bool, str, float]:
        """
        Проверяет, может ли пользователь применить указанный промокод.
        Возвращает (успех, сообщение, размер скидки).
        """
        logger.info(f"Валидация промокода {code} для пользователя {user_id}")
        promo = await self.get_promo_code(code)
        if not promo:
            logger.warning(f"Промокод {code} не найден")
            return False, "Промокод не найден", 0

        if not promo.is_active:
            logger.warning(f"Промокод {code} деактивирован")
            return False, "Промокод деактивирован", 0

        if promo.used_count >= promo.max_uses:
            logger.warning(f"Промокод {code} исчерпал лимит использований ({promo.used_count}/{promo.max_uses})")
            return False, "Лимит использований исчерпан", 0

        now = datetime.now().isoformat()
        if promo.valid_to < now:
            logger.warning(f"Срок действия промокода {code} истёк")
            return False, "Срок действия промокода истек", 0

        # Проверяем, не использовал ли уже пользователь этот промокод
        used_ids = await self.get_user_used_promo_ids(user_id)
        if promo.id in used_ids:
            logger.warning(f"Пользователь {user_id} уже использовал промокод {code}")
            return False, "Вы уже использовали этот промокод", 0

        logger.info(f"Промокод {code} валиден, скидка {promo.discount_percent}%")
        return True, "Промокод применен", promo.discount_percent

    @db_retry()
    async def use_promo_code(self, promo_id: int, user_id: int, order_id: int) -> bool:
        """
        Фиксирует использование промокода пользователем в рамках заказа.
        Увеличивает счётчик использований промокода.
        """
        logger.info(f"Применение промокода ID {promo_id} пользователем {user_id} для заказа #{order_id}")
        async with self.lock:
            await self.conn.execute("""
                INSERT INTO promo_usage (promo_id, user_id, order_id)
                VALUES (?, ?, ?)
            """, (promo_id, user_id, order_id))
            await self.conn.execute("""
                UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?
            """, (promo_id,))
            await self.conn.commit()
            logger.info(f"Промокод ID {promo_id} применён, использований теперь {promo_id}")
            return True

    @db_retry()
    async def get_all_promo_codes(self) -> List[PromoCode]:
        """Возвращает список всех промокодов (всех, независимо от активности)."""
        logger.debug("Запрос всех промокодов")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM promo_codes ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            promos = [PromoCode(**dict(row)) for row in rows]
            logger.debug(f"Получено {len(promos)} промокодов")
            return promos

    @db_retry()
    async def toggle_promo_code(self, promo_id: int, is_active: bool) -> bool:
        """Активирует или деактивирует промокод."""
        logger.info(f"Переключение активности промокода ID {promo_id} на {is_active}")
        async with self.lock:
            await self.conn.execute(
                "UPDATE promo_codes SET is_active = ? WHERE id = ?",
                (is_active, promo_id)
            )
            await self.conn.commit()
            logger.info(f"Промокод ID {promo_id} теперь {'активен' if is_active else 'неактивен'}")
            return True

    @db_retry()
    async def get_user_used_promo_ids(self, user_id: int) -> List[int]:
        """Возвращает список ID промокодов, которые уже использовал пользователь."""
        logger.debug(f"Запрос использованных промокодов пользователем {user_id}")
        async with self.lock:
            cursor = await self.conn.execute(
                "SELECT promo_id FROM promo_usage WHERE user_id = ?",
                (user_id,)
            )
            rows = await cursor.fetchall()
            promo_ids = [row[0] for row in rows]
            logger.debug(f"Пользователь {user_id} использовал {len(promo_ids)} промокодов")
            return promo_ids