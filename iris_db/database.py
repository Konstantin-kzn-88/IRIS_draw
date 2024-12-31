import sqlite3
from typing import Optional
from pathlib import Path
from iris_db.schema import CREATE_TABLES_SQL
from iris_db.repositories import ImageRepository, ObjectRepository, CoordinateRepository


class DatabaseManager:
    def __init__(self, db_path: str):
        """
        Инициализирует подключение к базе данных и создает все необходимые таблицы

        Args:
            db_path: путь к файлу базы данных SQLite
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)

        # Включаем поддержку foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")

        # Создаем таблицы
        self._create_tables()

        # Инициализируем репозитории
        self.images = ImageRepository(self.conn)
        self.objects = ObjectRepository(self.conn)
        self.coordinates = CoordinateRepository(self.conn)

    def _create_tables(self):
        """Создает все необходимые таблицы в базе данных"""
        cursor = self.conn.cursor()
        cursor.executescript(CREATE_TABLES_SQL)
        self.conn.commit()

    def close(self):
        """Закрывает соединение с базой данных"""
        self.conn.close()

    def vacuum(self) -> None:
        """
        Выполняет VACUUM для оптимизации базы данных.
        Это освобождает неиспользуемое пространство и дефрагментирует базу данных.
        """
        try:
            # Отключаем foreign keys временно, так как VACUUM не работает с включенными foreign keys
            self.conn.execute("PRAGMA foreign_keys = OFF")

            # Выполняем VACUUM
            self.conn.execute("VACUUM")

            # Включаем foreign keys обратно
            self.conn.execute("PRAGMA foreign_keys = ON")

            # Выполняем commit для применения изменений
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Ошибка при выполнении VACUUM: {e}")
            raise

    def __enter__(self):
        """Поддержка контекстного менеджера"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Закрывает соединение при выходе из контекстного менеджера"""
        self.close()