# bot/utils/backup.py
"""Функции резервного копирования базы данных."""

import os
import shutil
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def backup_db(db_path: str) -> str:
    """
    Создаёт резервную копию файла БД в папку backups с меткой времени.
    :param db_path: путь к файлу базы данных
    :return: путь к созданной копии или пустую строку при ошибке
    """
    logger.info(f"Запуск резервного копирования для {db_path}")
    try:
        if not os.path.exists(db_path):
            logger.warning(f"Файл БД не найден: {db_path}, резервное копирование невозможно")
            return ""

        # Создаём папку backups рядом с файлом БД
        backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        logger.debug(f"Папка для бэкапов: {backup_dir}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"exchange_backup_{timestamp}.db"
        backup_path = os.path.join(backup_dir, backup_filename)

        shutil.copy2(db_path, backup_path)
        logger.info(f"Резервная копия успешно создана: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии БД: {e}", exc_info=True)
        return ""