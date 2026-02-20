from aiogram import Router
from .main import router as main_router
from .orders import router as orders_router
from .finance import router as finance_router
from .settings import router as settings_router
from .users import router as users_router
from .promocodes import router as promocodes_router
from .bank import router as bank_router
from .wallets import router as wallets_router
from .diagnostic import router as diagnostic_router   # новый импорт

router = Router()
router.include_router(main_router)
router.include_router(orders_router)
router.include_router(finance_router)
router.include_router(settings_router)
router.include_router(users_router)
router.include_router(promocodes_router)
router.include_router(bank_router)
router.include_router(wallets_router)
router.include_router(diagnostic_router)   # добавляем