# database_handler.py
import sys
from pathlib import Path

from iris_db.database import DatabaseManager
from iris_db.models import Image


def get_database_path(app_directory=None):
    """Находит единственную базу рядом с программой независимо от рабочей папки."""
    if app_directory is None:
        app_directory = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent.parent
        )
    app_directory = Path(app_directory).resolve()
    databases = sorted(
        path for path in app_directory.iterdir()
        if path.is_file() and path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}
    )
    if len(databases) > 1:
        names = ", ".join(path.name for path in databases)
        raise ValueError(
            f"Рядом с программой найдено несколько баз данных: {names}. "
            "Оставьте в папке программы только используемую базу данных."
        )
    return databases[0] if databases else app_directory / "iris.db"


class DatabaseHandler:
    def __init__(self, parent=None):
        self.parent = parent
        self.connection = False
        self.current_db_path = None
        self.last_error = None

    def connect_to_database(self):
        """Автоматически открывает базу рядом с программой или создает iris.db."""
        self.close()
        self.last_error = None
        try:
            file_path = str(get_database_path())
            with DatabaseManager(file_path):
                pass
            self.current_db_path = file_path
            self.connection = True
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"Ошибка при подключении к базе данных: {e}")
            return False

    def save_plan(self, plan_name, image_data, plan_path):
        """
        Сохраняет план в базу данных

        Args:

            plan_name (str): Имя файла плана
            image_data (bytes): Бинарные данные изображения
            plan_path - путь к изображению


        Returns:
            int: ID добавленного плана или None в случае ошибки
        """
        if not self.connection:
            print("Нет подключения к базе данных")
            return None

        try:
            with DatabaseManager(self.current_db_path) as db:
                # Загружаем изображение из файла
                image = Image.from_file(plan_path, scale=None)
                # Сохраняем изображение в базу данных
                image_id = db.images.create(image)
                print(f"Created image with ID: {image_id}")
                return image_id
        except Exception as e:
            print(f"Ошибка при сохранении плана: {e}")
            return None

    def close(self):
        """Сбрасывает подключение; соединения отдельных операций уже закрыты."""
        self.connection = False
        self.current_db_path = None

    def vacuum_database(self) -> bool:
        """
        Выполняет оптимизацию базы данных с помощью VACUUM.

        Returns:
            bool: True если операция выполнена успешно, False в случае ошибки
        """
        if not self.connection or not self.current_db_path:
            print("Нет подключения к базе данных")
            return False

        try:
            with DatabaseManager(self.current_db_path) as db:
                db.vacuum()
            return True
        except Exception as e:
            print(f"Ошибка при выполнении VACUUM: {e}")
            return False
