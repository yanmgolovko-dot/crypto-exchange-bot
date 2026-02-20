#!/usr/bin/env python3
"""
Скрипт для запуска Telegram бота обменника криптовалют
"""

import asyncio
import sys
import os
import traceback

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("Ошибка при запуске:")
        traceback.print_exc()
        sys.exit(1)