from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QMessageBox
from iris_db.models import Object, Coordinate
from iris_db.database import DatabaseManager
from .temp_drawing import TempDrawingManager


class EditCoordinatesManager:
    """Класс для управления редактированием координат объекта"""

    def __init__(self, main_window):
        self.main_window = main_window
        self.current_object = None
        self.temp_coordinates = []
        self.is_editing = False
        self.temp_drawing = TempDrawingManager(main_window.view.scene())

    def start_editing_coordinates(self, object_id: int):
        """Начинает процесс редактирования координат объекта"""
        try:
            with DatabaseManager(self.main_window.db_handler.current_db_path) as db:
                self.current_object = db.objects.get_by_id(object_id)
                if not self.current_object:
                    raise ValueError("Объект не найден")

                self.is_editing = True
                self.temp_coordinates = []

                # Включаем отслеживание мыши
                self.main_window.view.setMouseTracking(True)

                # Скрываем текущий объект на плане
                if object_id in self.main_window.object_items:
                    self.main_window.object_items[object_id].set_visible(False)

                # Начинаем рисование нового объекта
                self.temp_drawing.start_drawing(
                    self.current_object.object_type.value,
                    QPointF(0, 0)  # Начальная точка будет обновлена при первом клике
                )

                # Показываем сообщение в статусбаре
                self.main_window.statusBar().showMessage(
                    "Кликайте для добавления новых координат. Двойной клик для завершения."
                )

        except Exception as e:
            QMessageBox.critical(
                self.main_window,
                "Ошибка",
                f"Не удалось начать редактирование координат: {str(e)}"
            )
            self.cancel_editing()

    def handle_mouse_move(self, scene_pos: QPointF):
        """Обрабатывает движение мыши при редактировании"""
        if not self.is_editing:
            return

        self.temp_drawing.update_drawing(scene_pos)

    def handle_mouse_click(self, scene_pos: QPointF, double_click: bool = False):
        """Обрабатывает клик мыши при редактировании координат"""
        if not self.is_editing:
            return

        new_coord = Coordinate(
            id=None,
            object_id=self.current_object.id,
            x=scene_pos.x(),
            y=scene_pos.y(),
            order_index=len(self.temp_coordinates)
        )
        self.temp_coordinates.append(new_coord)

        # Обновляем временное отображение
        if len(self.temp_coordinates) == 1:
            self.temp_drawing.start_drawing(
                self.current_object.object_type.value,
                scene_pos
            )
        else:
            self.temp_drawing.add_vertex(scene_pos)

        # Для точечного объекта завершаем редактирование после первого клика
        if self.current_object.object_type.value == 'point':
            self._save_changes()
            return

        # Проверяем условия завершения редактирования для других типов объектов
        if double_click:
            if self.current_object.object_type.value == 'stationary':
                if len(self.temp_coordinates) >= 3:
                    first_coord = self.temp_coordinates[0]
                    last_coord = Coordinate(
                        id=None,
                        object_id=self.current_object.id,
                        x=first_coord.x,
                        y=first_coord.y,
                        order_index=len(self.temp_coordinates)
                    )
                    self.temp_coordinates.append(last_coord)
                    self.temp_drawing.close_polygon()
                    self._save_changes()
            else:
                if len(self.temp_coordinates) >= 2:
                    self._save_changes()

    def _save_changes(self):
        """Сохраняет изменения координат в базу данных"""
        try:
            # Проверяем минимальное количество координат
            if (self.current_object.object_type.value == 'point' and len(self.temp_coordinates) != 1) or \
                    (self.current_object.object_type.value == 'linear' and len(self.temp_coordinates) < 2) or \
                    (self.current_object.object_type.value == 'stationary' and len(self.temp_coordinates) < 4):
                raise ValueError("Недостаточно координат для данного типа объекта")

            # Обновляем координаты объекта
            self.current_object.coordinates = self.temp_coordinates

            # Сохраняем изменения в базе данных
            with DatabaseManager(self.main_window.db_handler.current_db_path) as db:
                db.objects.update(self.current_object)

            # Обновляем отображение
            self.main_window.load_objects_from_image(self.current_object.image_id)
            self.main_window.statusBar().showMessage("Координаты успешно обновлены", 3000)

        except Exception as e:
            QMessageBox.critical(
                self.main_window,
                "Ошибка",
                f"Не удалось сохранить изменения координат: {str(e)}"
            )
        finally:
            self.cancel_editing()

    def cancel_editing(self):
        """Отменяет редактирование координат"""
        self.is_editing = False
        self.current_object = None
        self.temp_coordinates = []
        self.temp_drawing.clear_temp_items()
        self.main_window.view.setMouseTracking(False)
        self.main_window.statusBar().clearMessage()