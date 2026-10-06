import sqlite3
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

        try:
            # Включаем поддержку foreign keys
            self.conn.execute("PRAGMA foreign_keys = ON")

            # Создаем таблицы
            self._create_tables()
        except Exception:
            self.conn.close()
            raise

        # Инициализируем репозитории
        self.images = ImageRepository(self.conn)
        self.objects = ObjectRepository(self.conn)
        self.coordinates = CoordinateRepository(self.conn)

    def _create_tables(self):
        """Создает все необходимые таблицы в базе данных"""
        cursor = self.conn.cursor()
        cursor.executescript(CREATE_TABLES_SQL)
        self.conn.commit()

        # До версии 1 импорт записывал 1.0 как служебное значение, а результат
        # измерения масштаба не сохранялся. Выполняем преобразование один раз,
        # чтобы новые измерения ровно 1 м/пиксель оставались действительными.
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            with self.conn:
                self.conn.execute("UPDATE images SET scale = NULL WHERE scale = 1.0")
                self.conn.execute("PRAGMA user_version = 1")

    def close(self):
        """Закрывает соединение с базой данных"""
        self.conn.close()

    def clear_plans(self) -> None:
        """Удаляет все планы, объекты и координаты одной транзакцией."""
        with self.conn:
            self.conn.execute("DELETE FROM images")

    def vacuum(self) -> None:
        """
        Выполняет VACUUM для оптимизации базы данных.
        Это освобождает неиспользуемое пространство и дефрагментирует базу данных.
        """
        try:
            # VACUUM выполняется после завершения транзакции удаления.
            # Контроль внешних ключей остается включенным и при ошибке VACUUM.
            self.conn.execute("VACUUM")
        except sqlite3.Error as e:
            print(f"Ошибка при выполнении VACUUM: {e}")
            raise

    def __enter__(self):
        """Поддержка контекстного менеджера"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Закрывает соединение при выходе из контекстного менеджера"""
        self.close()
