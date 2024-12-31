import sqlite3
from typing import List, Optional
from datetime import datetime
from iris_db.models import Image, Object, Coordinate, ObjectType


class CoordinateRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, coordinate: Coordinate) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO coordinates (object_id, x, y, order_index)
            VALUES (?, ?, ?, ?)
        """, (coordinate.object_id, coordinate.x, coordinate.y, coordinate.order_index))
        coordinate.id = cursor.lastrowid
        self.conn.commit()
        return coordinate.id

    def update(self, coordinate: Coordinate) -> None:
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE coordinates
            SET object_id=?, x=?, y=?, order_index=?
            WHERE id=?
        """, (coordinate.object_id, coordinate.x, coordinate.y,
              coordinate.order_index, coordinate.id))
        self.conn.commit()

    def delete(self, coordinate_id: int) -> None:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM coordinates WHERE id=?", (coordinate_id,))
        self.conn.commit()

    def get_by_object_id(self, object_id: int) -> List[Coordinate]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, object_id, x, y, order_index
            FROM coordinates
            WHERE object_id = ?
            ORDER BY order_index
        """, (object_id,))

        return [
            Coordinate(
                id=row[0],
                object_id=row[1],
                x=row[2],
                y=row[3],
                order_index=row[4]
            )
            for row in cursor.fetchall()
        ]


class ObjectRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.coordinate_repo = CoordinateRepository(conn)

    def create(self, obj: Object) -> int:
        if not obj.validate_coordinates():
            raise ValueError(f"Invalid coordinates for object type {obj.object_type}")

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO objects (
                image_id, name, R1, R2, R3, R4, R5, R6, object_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (obj.image_id, obj.name, obj.R1, obj.R2, obj.R3,
              obj.R4, obj.R5, obj.R6, obj.object_type.value))

        obj.id = cursor.lastrowid

        # Сохраняем координаты
        for coord in obj.coordinates:
            coord.object_id = obj.id
            self.coordinate_repo.create(coord)

        self.conn.commit()
        return obj.id

    def update(self, obj: Object) -> None:
        if not obj.validate_coordinates():
            raise ValueError(f"Invalid coordinates for object type {obj.object_type}")

        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE objects
            SET image_id=?, name=?, R1=?, R2=?, R3=?, R4=?, R5=?, R6=?,
                object_type=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (obj.image_id, obj.name, obj.R1, obj.R2, obj.R3,
              obj.R4, obj.R5, obj.R6, obj.object_type.value, obj.id))

        # Удаляем старые координаты и сохраняем новые
        cursor.execute("DELETE FROM coordinates WHERE object_id=?", (obj.id,))
        for coord in obj.coordinates:
            coord.object_id = obj.id
            self.coordinate_repo.create(coord)

        self.conn.commit()

    def delete(self, object_id: int) -> None:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM objects WHERE id=?", (object_id,))
        self.conn.commit()

    def get_by_id(self, object_id: int) -> Optional[Object]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, image_id, name, R1, R2, R3, R4, R5, R6,
                   object_type, created_at, updated_at
            FROM objects
            WHERE id=?
        """, (object_id,))

        row = cursor.fetchone()
        if not row:
            return None

        coordinates = self.coordinate_repo.get_by_object_id(row[0])

        return Object(
            id=row[0],
            image_id=row[1],
            name=row[2],
            R1=row[3],
            R2=row[4],
            R3=row[5],
            R4=row[6],
            R5=row[7],
            R6=row[8],
            object_type=ObjectType(row[9]),
            created_at=datetime.fromisoformat(row[10]),
            updated_at=datetime.fromisoformat(row[11]),
            coordinates=coordinates
        )

    def get_by_image_id(self, image_id: int) -> List[Object]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, image_id, name, R1, R2, R3, R4, R5, R6,
                   object_type, created_at, updated_at
            FROM objects
            WHERE image_id=?
        """, (image_id,))

        objects = []
        for row in cursor.fetchall():
            coordinates = self.coordinate_repo.get_by_object_id(row[0])
            objects.append(Object(
                id=row[0],
                image_id=row[1],
                name=row[2],
                R1=row[3],
                R2=row[4],
                R3=row[5],
                R4=row[6],
                R5=row[7],
                R6=row[8],
                object_type=ObjectType(row[9]),
                created_at=datetime.fromisoformat(row[10]),
                updated_at=datetime.fromisoformat(row[11]),
                coordinates=coordinates
            ))
        return objects


class ImageRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.object_repo = ObjectRepository(conn)

    def create(self, image: Image) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO images (
                file_name, image_data, scale, mime_type, file_size
            ) VALUES (?, ?, ?, ?, ?)
        """, (image.file_name, image.image_data, image.scale,
              image.mime_type, image.file_size))

        image.id = cursor.lastrowid

        # Сохраняем объекты
        for obj in image.objects:
            obj.image_id = image.id
            self.object_repo.create(obj)

        self.conn.commit()
        return image.id

    def update(self, image: Image) -> None:
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE images
            SET file_name=?, image_data=?, scale=?, mime_type=?,
                file_size=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (image.file_name, image.image_data, image.scale,
              image.mime_type, image.file_size, image.id))

        # Обновляем объекты
        existing_objects = self.object_repo.get_by_image_id(image.id)
        existing_ids = {obj.id for obj in existing_objects if obj.id is not None}
        new_ids = {obj.id for obj in image.objects if obj.id is not None}

        # Удаляем объекты, которых нет в новом списке
        for obj_id in existing_ids - new_ids:
            self.object_repo.delete(obj_id)

        # Обновляем или создаем объекты
        for obj in image.objects:
            obj.image_id = image.id
            if obj.id is None:
                self.object_repo.create(obj)
            else:
                self.object_repo.update(obj)

        self.conn.commit()

    def delete(self, image_id: int) -> None:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM images WHERE id=?", (image_id,))
        self.conn.commit()

    def get_by_id(self, image_id: int) -> Optional[Image]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, file_name, image_data, scale, mime_type,
                   file_size, created_at, updated_at
            FROM images
            WHERE id=?
        """, (image_id,))

        row = cursor.fetchone()
        if not row:
            return None

        objects = self.object_repo.get_by_image_id(row[0])

        return Image(
            id=row[0],
            file_name=row[1],
            image_data=row[2],
            scale=row[3],
            mime_type=row[4],
            file_size=row[5],
            created_at=datetime.fromisoformat(row[6]),
            updated_at=datetime.fromisoformat(row[7]),
            objects=objects
        )

    def get_all(self) -> List[Image]:
        """Получает все изображения без загрузки данных изображений"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, file_name, scale, mime_type,
                   file_size, created_at, updated_at
            FROM images
        """)

        images = []
        for row in cursor.fetchall():
            objects = self.object_repo.get_by_image_id(row[0])
            images.append(Image(
                id=row[0],
                file_name=row[1],
                image_data=b"",  # Не загружаем данные изображения
                scale=row[2],
                mime_type=row[3],
                file_size=row[4],
                created_at=datetime.fromisoformat(row[5]),
                updated_at=datetime.fromisoformat(row[6]),
                objects=objects
            ))
        return images

    def get_image_data(self, image_id: int) -> Optional[bytes]:
        """Получает только данные изображения"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT image_data FROM images WHERE id=?", (image_id,))
        row = cursor.fetchone()
        return row[0] if row else None