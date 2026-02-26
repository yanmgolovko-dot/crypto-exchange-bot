# bot/handlers/__init__.py
from aiogram import Router

from .start import router as start_router
from .tickets import router as tickets_router
from .help import router as help_router
from .profile import router as profile_router
from .exchange import router as exchange_router
from .orders import router as orders_router
from .reviews import router as reviews_router
from .partner import router as partner_router  # новый роутер для партнёров
from .common import router as common_router

router = Router()
router.include_router(start_router)
router.include_router(tickets_router)
router.include_router(help_router)
router.include_router(profile_router)
router.include_router(exchange_router)
router.include_router(orders_router)
router.include_router(reviews_router)
router.include_router(partner_router)  # добавляем
router.include_router(common_router)

__all__ = ['router']