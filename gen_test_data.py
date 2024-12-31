from pathlib import Path
import random
from iris_db.database import DatabaseManager
from iris_db.models import Image, Object, Coordinate, ObjectType

def generate_test_data(db_path: str, image_paths: list[str]):
    """
    Генерирует тестовые данные для базы данных

    Args:
        db_path: путь к файлу базы данных
        image_paths: список путей к тестовым изображениям
    """
    with DatabaseManager(db_path) as db:
        for image_path in image_paths:
            # Создаем изображение
            image = Image.from_file(image_path, scale=1.0)

            # Генерируем набор тестовых объектов
            objects = []

            # Добавляем точечные объекты
            for i in range(3):
                point_obj = Object(
                    id=None,
                    image_id=0,
                    name=f"Точечный объект {i+1}",
                    R1=random.uniform(1.0, 10.0),
                    R2=random.uniform(1.0, 10.0),
                    R3=random.uniform(1.0, 10.0),
                    R4=random.uniform(1.0, 10.0),
                    R5=random.uniform(1.0, 10.0),
                    R6=random.uniform(1.0, 10.0),
                    object_type=ObjectType.POINT,
                    coordinates=[
                        Coordinate(
                            id=None,
                            object_id=0,
                            x=random.uniform(0, 1000),
                            y=random.uniform(0, 1000),
                            order_index=0
                        )
                    ]
                )
                objects.append(point_obj)

            # Добавляем линейные объекты
            for i in range(2):
                points = []
                for j in range(3):
                    points.append(
                        Coordinate(
                            id=None,
                            object_id=0,
                            x=random.uniform(0, 1000),
                            y=random.uniform(0, 1000),
                            order_index=j
                        )
                    )

                linear_obj = Object(
                    id=None,
                    image_id=0,
                    name=f"Линейный объект {i+1}",
                    R1=random.uniform(1.0, 10.0),
                    R2=random.uniform(1.0, 10.0),
                    R3=random.uniform(1.0, 10.0),
                    R4=random.uniform(1.0, 10.0),
                    R5=random.uniform(1.0, 10.0),
                    R6=random.uniform(1.0, 10.0),
                    object_type=ObjectType.LINEAR,
                    coordinates=points
                )
                objects.append(linear_obj)

            # Добавляем стационарные объекты (замкнутые многоугольники)
            for i in range(2):
                # Создаем замкнутый многоугольник
                points = []
                num_points = random.randint(4, 6)  # От 4 до 6 точек
                center_x = random.uniform(200, 800)
                center_y = random.uniform(200, 800)
                radius = random.uniform(50, 150)

                for j in range(num_points):
                    angle = (2 * 3.14159 * j) / num_points
                    x = center_x + radius * math.cos(angle)
                    y = center_y + radius * math.sin(angle)
                    points.append(
                        Coordinate(
                            id=None,
                            object_id=0,
                            x=x,
                            y=y,
                            order_index=j
                        )
                    )

                # Замыкаем многоугольник
                points.append(
                    Coordinate(
                        id=None,
                        object_id=0,
                        x=points[0].x,
                        y=points[0].y,
                        order_index=len(points)
                    )
                )

                stationary_obj = Object(
                    id=None,
                    image_id=0,
                    name=f"Стационарный объект {i+1}",
                    R1=random.uniform(1.0, 10.0),
                    R2=random.uniform(1.0, 10.0),
                    R3=random.uniform(1.0, 10.0),
                    R4=random.uniform(1.0, 10.0),
                    R5=random.uniform(1.0, 10.0),
                    R6=random.uniform(1.0, 10.0),
                    object_type=ObjectType.STATIONARY,
                    coordinates=points
                )
                objects.append(stationary_obj)

            # Добавляем объекты к изображению
            image.objects = objects

            # Сохраняем изображение с объектами в базу данных
            image_id = db.images.create(image)
            print(f"Создано изображение с ID: {image_id} и {len(objects)} объектами")

if __name__ == "__main__":
    import math

    # Путь к базе данных
    db_path = "test.db"

    # Список тестовых изображений
    image_paths = [
        "test_plan.jpg",
        "test_plan2.jpg"
    ]

    # Генерируем тестовые данные
    generate_test_data(db_path, image_paths)