"""Функции резервного копирования БД"""

import os
import shutil
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def backup_db(db_path: str) -> str:
    """
    Создаёт резервную копию файла БД в папку backups с меткой времени.
    Возвращает путь к созданной копии.
    """
    try:
        if not os.path.exists(db_path):
            logger.warning("Файл БД не найден, резервное копирование невозможно")
            return ""
        backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"exchange_backup_{timestamp}.db"
        backup_path = os.path.join(backup_dir, backup_filename)
        shutil.copy2(db_path, backup_path)
        logger.info(f"Резервная копия БД создана: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии БД: {e}")
        return ""