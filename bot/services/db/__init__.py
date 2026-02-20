from .database import Database

# Создаём единственный экземпляр базы данных
db = Database()

__all__ = ['db']