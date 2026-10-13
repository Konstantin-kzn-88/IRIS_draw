import sqlite3
import re
from collections import defaultdict
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

        if version < 2:
            with self.conn:
                self._split_legacy_point_arrays()
                self.conn.execute("PRAGMA user_version = 2")

    def _split_legacy_point_arrays(self):
        """Разделяет прежние группы на точки, сохраняя радиусы и координаты."""
        arrays = self.conn.execute("""
            SELECT id, image_id, name, R1, R2, R3, R4, R5, R6, created_at, updated_at
            FROM objects WHERE object_type = 'point' AND id IN (
                SELECT object_id FROM coordinates GROUP BY object_id HAVING COUNT(*) > 1
            ) ORDER BY id
        """).fetchall()
        if not arrays:
            return
        used_names = defaultdict(set)
        for image_id, name in self.conn.execute("SELECT image_id, name FROM objects"):
            used_names[image_id].add(name)
        next_numbers = {
            image_id: max(
                (int(match.group(1)) for name in names
                 if (match := re.fullmatch(r"массив_(\d+)", name))), default=0
            ) + 1 for image_id, names in used_names.items()
        }
        for row in arrays:
            object_id, image_id, original_name = row[:3]
            coordinate_ids = [coord[0] for coord in self.conn.execute(
                "SELECT id FROM coordinates WHERE object_id = ? ORDER BY order_index, id",
                (object_id,)
            )]
            # ID исходного объекта и первой координаты остаются прежними.
            self.conn.execute("UPDATE coordinates SET order_index = 0 WHERE id = ?",
                              (coordinate_ids[0],))
            for index, coordinate_id in enumerate(coordinate_ids[1:], start=2):
                if re.fullmatch(r"массив_(\d+)", original_name):
                    name = f"массив_{next_numbers[image_id]}"
                    next_numbers[image_id] += 1
                else:
                    suffix = index
                    name = f"{original_name}_{suffix}"
                    while name in used_names[image_id]:
                        suffix += 1
                        name = f"{original_name}_{suffix}"
                used_names[image_id].add(name)
                cursor = self.conn.execute("""
                    INSERT INTO objects (image_id, name, R1, R2, R3, R4, R5, R6,
                                         object_type, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'point', ?, ?)
                """, (image_id, name, *row[3:9], row[9], row[10]))
                self.conn.execute(
                    "UPDATE coordinates SET object_id = ?, order_index = 0 WHERE id = ?",
                    (cursor.lastrowid, coordinate_id)
                )

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
