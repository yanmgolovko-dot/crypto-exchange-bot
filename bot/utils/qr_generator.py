# bot/utils/qr_generator.py
"""
Генератор QR-кодов для реферальных ссылок.
Использует библиотеку qrcode[pil].
"""

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_qr_bytes(data: str) -> Optional[io.BytesIO]:
    """
    Генерирует красивый QR-код (PNG) и возвращает BytesIO.
    При ошибке (нет qrcode/Pillow) возвращает None — вызывающий код
    должен прислать хотя бы текстовую ссылку.
    """
    if not data:
        return None

    try:
        import qrcode
        from qrcode.image.styledpil import StyledPilImage
        from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
        from qrcode.image.styles.colormasks import SolidFillColorMask
    except ImportError as e:
        logger.warning(f"QR-библиотека недоступна: {e}. Установите: pip install 'qrcode[pil]'")
        return None

    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=12,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
            color_mask=SolidFillColorMask(
                back_color=(255, 255, 255),
                front_color=(24, 24, 28),  # почти чёрный
            ),
        )

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf
    except Exception as e:
        logger.exception(f"Ошибка генерации QR-кода: {e}")
        return None