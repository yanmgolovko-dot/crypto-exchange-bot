# bot/admin/__init__.py
from aiogram import Router
from .main import router as main_router
from .orders import router as orders_router
from .finance import router as finance_router
from .users import router as users_router
from .wallets import router as wallets_router
from .marketing import router as marketing_router
from .fake import router as fake_router
from .settings import router as settings_router
from .diagnostic import router as diagnostic_router
from .tickets import router as tickets_router
from .broadcast import router as broadcast_router
from .admins import router as admins_router
from .health import router as health_router
from .rates import router as rates_router
from .ref_links import router as ref_links_router

router = Router()
router.include_router(main_router)
router.include_router(orders_router)
router.include_router(finance_router)
router.include_router(users_router)
router.include_router(wallets_router)
router.include_router(marketing_router)
router.include_router(fake_router)
router.include_router(settings_router)
router.include_router(diagnostic_router)
router.include_router(tickets_router)
router.include_router(broadcast_router)
router.include_router(admins_router)
router.include_router(health_router)
router.include_router(rates_router)
router.include_router(ref_links_router)

__all__ = ['router']