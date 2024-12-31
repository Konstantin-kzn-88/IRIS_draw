from pathlib import Path
from iris_db.database import DatabaseManager
from iris_db.models import Image, Object, Coordinate, ObjectType


def main():
    # Используем контекстный менеджер для работы с базой данных
    with DatabaseManager("test.db") as db:
        try:
            # Загружаем изображение из файла
            image = Image.from_file("test_plan.jpg", scale=1.0)

            # Создаем точечный объект
            point_object = Object(
                id=None,
                image_id=0,  # будет установлен при сохранении
                name="Point Object",
                R1=1.0, R2=2.0, R3=3.0, R4=4.0, R5=5.0, R6=6.0,
                object_type=ObjectType.POINT,
                coordinates=[
                    Coordinate(id=None, object_id=0, x=10.0, y=20.0, order_index=0)
                ]
            )

            # Создаем линейный объект
            linear_object = Object(
                id=None,
                image_id=0,
                name="Linear Object",
                R1=1.0, R2=2.0, R3=3.0, R4=4.0, R5=5.0, R6=6.0,
                object_type=ObjectType.LINEAR,
                coordinates=[
                    Coordinate(id=None, object_id=0, x=0.0, y=0.0, order_index=0),
                    Coordinate(id=None, object_id=0, x=10.0, y=10.0, order_index=1),
                    Coordinate(id=None, object_id=0, x=20.0, y=0.0, order_index=2)
                ]
            )

            # Добавляем объекты к изображению
            image.objects = [point_object, linear_object]

            # Сохраняем изображение в базу данных
            image_id = db.images.create(image)
            print(f"Created image with ID: {image_id}")

            # Получаем список всех изображений (без данных изображений)
            all_images = db.images.get_all()
            print(f"Total images in database: {len(all_images)}")

            # Получаем конкретное изображение с его объектами
            loaded_image = db.images.get_by_id(image_id)
            if loaded_image:
                print(f"Loaded image {loaded_image.file_name} with {len(loaded_image.objects)} objects")

                # Изменяем масштаб изображения
                loaded_image.scale = 2.0
                db.images.update(loaded_image)
                print("Updated image scale")

                # Получаем определенный объект
                obj = db.objects.get_by_id(loaded_image.objects[0].id)
                if obj:
                    print(f"Found object: {obj.name}")

                    # Изменяем параметры объекта
                    obj.name = "Updated Point Object"
                    db.objects.update(obj)
                    print("Updated object name")

                # Добавляем новый объект к существующему изображению
                new_object = Object(
                    id=None,
                    image_id=loaded_image.id,
                    name="New Object",
                    R1=1.0, R2=2.0, R3=3.0, R4=4.0, R5=5.0, R6=6.0,
                    object_type=ObjectType.POINT,
                    coordinates=[
                        Coordinate(id=None, object_id=0, x=15.0, y=25.0, order_index=0)
                    ]
                )
                db.objects.create(new_object)
                print("Added new object to image")

                # Сохраняем изображение в файл
                loaded_image.save_to_file("output.jpg")

                # Удаляем один из объектов
                db.objects.delete(loaded_image.objects[0].id)
                print("Deleted first object")

            # Удаляем изображение (каскадно удалит все связанные объекты и координаты)
            db.images.delete(image_id)
            print("Deleted image and all related objects")

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()