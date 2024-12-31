# database_handler.py
import sqlite3
from PySide6.QtWidgets import QFileDialog
from iris_db.database import DatabaseManager
from iris_db.models import Image, Object, Coordinate, ObjectType


class DatabaseHandler:
    def __init__(self, parent=None):
        self.parent = parent
        self.connection = None
        self.current_db_path = None

    def create_database(self):
        """Создает новую базу данных"""
        file_path, _ = QFileDialog.getSaveFileName(
            self.parent,
            "Создать базу данных",
            "",
            "База данных (*.db)"
        )
        if file_path:
            if not file_path.endswith('.db'):
                file_path += '.db'

            try:
                _ = DatabaseManager(file_path)._create_tables()
                self.current_db_path = file_path
                self.connection = True
                return True
            except Exception as e:
                print(f"Ошибка при создании базы данных: {e}")
                return False
        return False

    def connect_to_database(self):
        """Подключается к существующей базе данных"""
        file_path, _ = QFileDialog.getOpenFileName(
            self.parent,
            "Открыть базу данных",
            "",
            "База данных (*.db)"
        )

        if file_path:
            try:
                _ = DatabaseManager(file_path)
                self.current_db_path = file_path
                self.connection = True
                return True
            except Exception as e:
                print(f"Ошибка при подключении к базе данных: {e}")
                return False
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
                image = Image.from_file(plan_path, scale=1.0)
                # Сохраняем изображение в базу данных
                image_id = db.images.create(image)
                print(f"Created image with ID: {image_id}")
                return image_id
        except Exception as e:
            print(f"Ошибка при сохранении плана: {e}")
            return None

    def close(self):
        """Закрывает соединение с базой данных"""
        if self.connection:
            self.connection.close()
            self.connection = None
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