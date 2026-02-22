# bot/services/db/coupon_repository.py

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from dataclasses import dataclass
import aiosqlite
from .base import BaseRepository, db_retry

logger = logging.getLogger(__name__)


@dataclass
class Coupon:
    id: int
    code: str
    discount_type: str          # 'percent' или 'fixed'
    discount_value: float
    discount_on: str             # 'order' или 'commission'
    max_uses_total: Optional[int]
    max_uses_per_user: Optional[int]
    used_count: int
    min_order_amount: float
    valid_from: Optional[str]
    valid_to: Optional[str]
    is_active: bool
    created_by: Optional[int]
    created_at: str
    description: Optional[str]
    owner_id: Optional[int] = None      # новое поле – владелец (если купон персональный)
    coupon_type: str = 'generic'        # новое поле – тип купона (welcome, activity, promo, generic)


class CouponRepository(BaseRepository):
    """
    Репозиторий для работы с купонами.
    Содержит методы создания, валидации, использования и получения.
    """

    @db_retry()
    async def create_coupon(
        self,
        code: str,
        discount_type: str,
        discount_value: float,
        discount_on: str = 'order',
        max_uses_total: int = None,
        max_uses_per_user: int = None,
        min_order_amount: float = 0,
        valid_days: int = 30,
        created_by: int = None,
        description: str = None,
        owner_id: int = None,           # новый параметр
        coupon_type: str = 'generic'    # новый параметр
    ) -> int:
        """
        Создаёт новый купон.
        :param code: код купона (будет преобразован в верхний регистр)
        :param discount_type: 'percent' или 'fixed'
        :param discount_value: величина скидки
        :param discount_on: 'order' или 'commission'
        :param max_uses_total: общее максимальное количество использований (None – безлимит)
        :param max_uses_per_user: сколько раз может использовать один пользователь
        :param min_order_amount: минимальная сумма заказа для применения
        :param valid_days: срок действия в днях от текущего момента (если None – бессрочно)
        :param created_by: ID администратора, создавшего купон
        :param description: описание
        :param owner_id: ID пользователя, которому принадлежит купон (если персональный)
        :param coupon_type: тип купона ('welcome', 'activity', 'promo', 'generic')
        :return: ID созданного купона
        """
        code_upper = code.upper()
        logger.info(f"Создание купона {code_upper}, тип {discount_type}, значение {discount_value}, на {discount_on}, владелец {owner_id}, тип купона {coupon_type}")

        async with self.lock:
            valid_to = None
            if valid_days:
                valid_to = (datetime.now() + timedelta(days=valid_days)).isoformat()

            cursor = await self.conn.execute("""
                INSERT INTO coupons 
                (code, discount_type, discount_value, discount_on, max_uses_total,
                 max_uses_per_user, min_order_amount, valid_to, created_by, description,
                 owner_id, coupon_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                code_upper, discount_type, discount_value, discount_on,
                max_uses_total, max_uses_per_user, min_order_amount,
                valid_to, created_by, description,
                owner_id, coupon_type
            ))
            await self.conn.commit()
            coupon_id = cursor.lastrowid
            logger.info(f"Купон создан, ID: {coupon_id}")
            return coupon_id

    @db_retry()
    async def get_coupon(self, code: str) -> Optional[Coupon]:
        """Получает купон по коду (без учёта регистра)."""
        code_upper = code.upper()
        logger.debug(f"Запрос купона {code_upper}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM coupons WHERE code = ?", (code_upper,)
            )
            row = await cursor.fetchone()
            if row:
                logger.debug(f"Купон {code_upper} найден")
                return Coupon(**dict(row))
            logger.debug(f"Купон {code_upper} не найден")
            return None

    @db_retry()
    async def get_coupon_by_id(self, coupon_id: int) -> Optional[Coupon]:
        """Получает купон по ID."""
        logger.debug(f"Запрос купона по ID {coupon_id}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM coupons WHERE id = ?", (coupon_id,)
            )
            row = await cursor.fetchone()
            if row:
                return Coupon(**dict(row))
            return None

    @db_retry()
    async def validate_coupon(
        self,
        code: str,
        user_id: int,
        order_amount: float
    ) -> Tuple[bool, str, Optional[Coupon]]:
        """
        Проверяет, может ли пользователь применить указанный купон.
        Возвращает (успех, сообщение, объект купона или None).
        """
        logger.info(f"Валидация купона {code} для пользователя {user_id}, сумма {order_amount}")
        coupon = await self.get_coupon(code)
        if not coupon:
            return False, "Купон не найден", None

        if not coupon.is_active:
            return False, "Купон деактивирован", coupon

        # Проверка персонального купона
        if coupon.owner_id is not None and coupon.owner_id != user_id:
            return False, "Этот купон предназначен для другого пользователя", coupon

        now = datetime.now().isoformat()
        if coupon.valid_to and coupon.valid_to < now:
            return False, "Срок действия купона истёк", coupon

        if coupon.max_uses_total is not None and coupon.used_count >= coupon.max_uses_total:
            return False, "Лимит использований купона исчерпан", coupon

        if coupon.max_uses_per_user is not None:
            async with self.lock:
                cursor = await self.conn.execute(
                    "SELECT COUNT(*) FROM coupon_usage WHERE coupon_id = ? AND user_id = ?",
                    (coupon.id, user_id)
                )
                user_uses = (await cursor.fetchone())[0]
                if user_uses >= coupon.max_uses_per_user:
                    return False, "Вы уже использовали этот купон", coupon

        if order_amount < coupon.min_order_amount:
            return False, f"Минимальная сумма заказа для этого купона: {coupon.min_order_amount} ₽", coupon

        logger.info(f"Купон {code} валиден")
        return True, "Купон может быть применён", coupon

    @db_retry()
    async def use_coupon(self, coupon_id: int, user_id: int, order_id: int) -> bool:
        """
        Фиксирует использование купона в заказе.
        Увеличивает счётчик использований.
        """
        logger.info(f"Применение купона ID {coupon_id} пользователем {user_id} для заказа #{order_id}")
        async with self.lock:
            await self.conn.execute("""
                INSERT INTO coupon_usage (coupon_id, user_id, order_id)
                VALUES (?, ?, ?)
            """, (coupon_id, user_id, order_id))
            await self.conn.execute("""
                UPDATE coupons SET used_count = used_count + 1 WHERE id = ?
            """, (coupon_id,))
            await self.conn.commit()
            logger.info(f"Купон ID {coupon_id} применён")
            return True

    @db_retry()
    async def get_all_coupons(self) -> List[Coupon]:
        """Возвращает список всех купонов."""
        logger.debug("Запрос всех купонов")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM coupons ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            coupons = [Coupon(**dict(row)) for row in rows]
            logger.debug(f"Получено {len(coupons)} купонов")
            return coupons

    @db_retry()
    async def get_user_coupons(self, user_id: int) -> List[Coupon]:
        """
        Возвращает все купоны, принадлежащие пользователю (owner_id = user_id)
        или общие купоны (owner_id IS NULL), но которые ещё не использованы пользователем.
        """
        logger.debug(f"Запрос купонов для пользователя {user_id}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            # Получаем все купоны, которые либо общие, либо персональные для этого пользователя
            cursor = await self.conn.execute("""
                SELECT c.* FROM coupons c
                LEFT JOIN coupon_usage cu ON c.id = cu.coupon_id AND cu.user_id = ?
                WHERE (c.owner_id IS NULL OR c.owner_id = ?)
                  AND c.is_active = 1
                  AND (c.valid_to IS NULL OR c.valid_to > datetime('now'))
                  AND (c.max_uses_total IS NULL OR c.used_count < c.max_uses_total)
                  AND (c.max_uses_per_user IS NULL OR cu.id IS NULL)
                ORDER BY c.created_at DESC
            """, (user_id, user_id))
            rows = await cursor.fetchall()
            coupons = [Coupon(**dict(row)) for row in rows]
            logger.debug(f"Получено {len(coupons)} доступных купонов")
            return coupons

    @db_retry()
    async def toggle_coupon(self, coupon_id: int, is_active: bool) -> bool:
        """Активирует или деактивирует купон."""
        logger.info(f"Переключение активности купона ID {coupon_id} на {is_active}")
        async with self.lock:
            await self.conn.execute(
                "UPDATE coupons SET is_active = ? WHERE id = ?",
                (is_active, coupon_id)
            )
            await self.conn.commit()
            logger.info(f"Купон ID {coupon_id} теперь {'активен' if is_active else 'неактивен'}")
            return True