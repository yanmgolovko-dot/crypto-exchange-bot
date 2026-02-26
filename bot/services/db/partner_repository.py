# bot/services/db/partner_repository.py
import logging
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass
import aiosqlite
import json
from .base import BaseRepository, db_retry

logger = logging.getLogger(__name__)


@dataclass
class Partner:
    user_id: int
    referral_code: Optional[str]
    balance: float
    total_earned: float
    level: int
    is_active: bool
    created_at: str
    updated_at: str


@dataclass
class WithdrawRequest:
    id: int
    user_id: int
    amount: float
    payment_method: Optional[str]
    payment_details: Optional[str]
    status: str
    admin_comment: Optional[str]
    processed_by: Optional[int]
    created_at: str
    processed_at: Optional[str]


@dataclass
class PartnerSettings:
    id: int  # добавлено поле id
    enabled: bool
    max_levels: int
    level_rewards: List[Dict[str, Any]]
    commission_source: str
    min_withdraw: float
    withdraw_fee: float
    withdraw_fee_type: str
    auto_approve: bool
    updated_at: str


class PartnerRepository(BaseRepository):

    # ===== Partners =====
    @db_retry()
    async def add_partner(self, user_id: int, referral_code: str) -> bool:
        """Добавляет пользователя в партнёры."""
        logger.info(f"Добавление партнёра {user_id} с кодом {referral_code}")
        async with self.lock:
            await self.conn.execute("""
                INSERT OR IGNORE INTO partners (user_id, referral_code)
                VALUES (?, ?)
            """, (user_id, referral_code))
            await self.conn.commit()
            return True

    @db_retry()
    async def get_partner(self, user_id: int) -> Optional[Partner]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM partners WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                return Partner(**dict(row))
            return None

    @db_retry()
    async def get_all_partners(self) -> List[Partner]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM partners ORDER BY user_id"
            )
            rows = await cursor.fetchall()
            return [Partner(**dict(row)) for row in rows]

    @db_retry()
    async def update_partner_balance(self, user_id: int, amount: float) -> bool:
        """Увеличивает баланс и total_earned на amount."""
        async with self.lock:
            await self.conn.execute("""
                UPDATE partners
                SET balance = balance + ?, total_earned = total_earned + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (amount, amount, user_id))
            await self.conn.commit()
            return True

    @db_retry()
    async def set_partner_balance(self, user_id: int, new_balance: float) -> bool:
        """Устанавливает баланс (для ручной корректировки)."""
        async with self.lock:
            await self.conn.execute("""
                UPDATE partners
                SET balance = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (new_balance, user_id))
            await self.conn.commit()
            return True

    @db_retry()
    async def set_partner_active(self, user_id: int, is_active: bool) -> bool:
        async with self.lock:
            await self.conn.execute(
                "UPDATE partners SET is_active = ? WHERE user_id = ?",
                (is_active, user_id)
            )
            await self.conn.commit()
            return True

    # ===== Referral Tree =====
    @db_retry()
    async def add_referral_link(self, referrer_id: int, referred_id: int, level: int) -> bool:
        """Создаёт связь в дереве рефералов."""
        async with self.lock:
            await self.conn.execute("""
                INSERT OR IGNORE INTO referral_tree (referrer_id, referred_id, level)
                VALUES (?, ?, ?)
            """, (referrer_id, referred_id, level))
            await self.conn.commit()
            return True

    @db_retry()
    async def get_referrers_chain(self, user_id: int, max_level: int) -> List[Tuple[int, int]]:
        """Возвращает список (referrer_id, level) для пользователя до max_level."""
        async with self.lock:
            cursor = await self.conn.execute("""
                SELECT referrer_id, level FROM referral_tree
                WHERE referred_id = ? AND level <= ?
                ORDER BY level ASC
            """, (user_id, max_level))
            rows = await cursor.fetchall()
            return [(row[0], row[1]) for row in rows]

    @db_retry()
    async def get_downline_count(self, user_id: int, level: int = None) -> int:
        """Количество рефералов на определённом уровне (или всех)."""
        query = "SELECT COUNT(*) FROM referral_tree WHERE referrer_id = ?"
        params = [user_id]
        if level is not None:
            query += " AND level = ?"
            params.append(level)
        cursor = await self.conn.execute(query, params)
        count = (await cursor.fetchone())[0]
        return count

    # ===== Withdraw Requests =====
    @db_retry()
    async def create_withdraw_request(
        self,
        user_id: int,
        amount: float,
        payment_method: str,
        payment_details: str
    ) -> int:
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO withdraw_requests (user_id, amount, payment_method, payment_details)
                VALUES (?, ?, ?, ?)
            """, (user_id, amount, payment_method, payment_details))
            await self.conn.commit()
            return cursor.lastrowid

    @db_retry()
    async def get_withdraw_request(self, request_id: int) -> Optional[WithdrawRequest]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM withdraw_requests WHERE id = ?", (request_id,)
            )
            row = await cursor.fetchone()
            if row:
                return WithdrawRequest(**dict(row))
            return None

    @db_retry()
    async def get_pending_withdraw_requests(self) -> List[WithdrawRequest]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM withdraw_requests WHERE status = 'pending' ORDER BY created_at ASC"
            )
            rows = await cursor.fetchall()
            return [WithdrawRequest(**dict(row)) for row in rows]

    @db_retry()
    async def get_user_withdraw_requests(self, user_id: int) -> List[WithdrawRequest]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM withdraw_requests WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [WithdrawRequest(**dict(row)) for row in rows]

    @db_retry()
    async def approve_withdraw_request(self, request_id: int, admin_id: int) -> bool:
        async with self.lock:
            await self.conn.execute("""
                UPDATE withdraw_requests
                SET status = 'approved', processed_by = ?, processed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'pending'
            """, (admin_id, request_id))
            await self.conn.commit()
            return True

    @db_retry()
    async def reject_withdraw_request(self, request_id: int, admin_id: int, comment: str) -> bool:
        async with self.lock:
            await self.conn.execute("""
                UPDATE withdraw_requests
                SET status = 'rejected', processed_by = ?, admin_comment = ?, processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (admin_id, comment, request_id))
            await self.conn.commit()
            return True

    # ===== Partner Settings =====
    @db_retry()
    async def get_settings(self) -> PartnerSettings:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("SELECT * FROM partner_settings WHERE id = 1")
            row = await cursor.fetchone()
            if row:
                data = dict(row)
                data['level_rewards'] = json.loads(data['level_rewards'])
                return PartnerSettings(**data)
            # Если вдруг нет – возвращаем дефолт (но по идее есть)
            return PartnerSettings(
                id=1,
                enabled=True,
                max_levels=10,
                level_rewards=json.loads('[{"level":1,"type":"percent","value":10},{"level":2,"type":"percent","value":5}]'),
                commission_source='fee',
                min_withdraw=1000,
                withdraw_fee=0,
                withdraw_fee_type='fixed',
                auto_approve=False,
                updated_at=''
            )

    @db_retry()
    async def update_settings(self, settings: dict) -> bool:
        """settings должен содержать ключи из таблицы (кроме id, updated_at)."""
        set_clause = ", ".join([f"{k} = ?" for k in settings.keys()])
        values = list(settings.values()) + [1]
        async with self.lock:
            await self.conn.execute(f"""
                UPDATE partner_settings SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, values)
            await self.conn.commit()
            return True