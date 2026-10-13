# object_manager.py
import re

from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtCore import QPointF
from iris_db.models import Object, Coordinate, ObjectType
from iris_db.database import DatabaseManager
from .temp_drawing import TempDrawingManager


class ObjectManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.current_object = None
        self.temp_coordinates = []
        self.is_drawing = False
        self.is_point_array = False
        self.current_object_type = None
        self.temp_drawing = TempDrawingManager(main_window.view.scene())

    def start_drawing_object(self, object_type: ObjectType, point_array: bool = False):
        """Начинает процесс рисования нового объекта"""
        if not self.main_window.db_handler.current_db_path:
            QMessageBox.warning(self.main_window, "Предупреждение",
                              "Сначала подключитесь к базе данных")
            return

        self.cancel_drawing()
        self.main_window.edit_coordinates_manager.cancel_editing()
        self.main_window.measurement_tools._finish_measurement()
        if self.main_window.view.scale_mode:
            self.main_window.toggle_scale_mode()
        self.current_object_type = object_type
        self.is_point_array = point_array and object_type == ObjectType.POINT
        self.is_drawing = True
        self.temp_coordinates = []

        # Включаем отслеживание мыши для view
        self.main_window.view.setMouseTracking(True)
        self.main_window.view.setCursor(Qt.CrossCursor)
        self.main_window.view.setFocus()

        # Показываем сообщение в статусбаре
        msg = {
            ObjectType.POINT: "Кликните для размещения точечного объекта",
            ObjectType.LINEAR: "Кликайте для добавления точек линейного объекта. Двойной клик для завершения",
            ObjectType.STATIONARY: "Кликайте для добавления точек стационарного объекта. Двойной клик для замыкания"
        }
        if self.is_point_array:
            self._show_array_status()
        else:
            self.main_window.statusBar().showMessage(msg[object_type])

    def start_point_array(self):
        """Начинает размещение массива независимых точек."""
        self.start_drawing_object(ObjectType.POINT, point_array=True)

    def _show_array_status(self):
        self.main_window.statusBar().showMessage(
            f"Введено точек: {len(self.temp_coordinates)}. "
            "Кликайте по плану; Enter или двойной клик — сохранить, Esc — отменить"
        )

    def handle_mouse_move(self, scene_pos: QPointF):
        """Обрабатывает движение мыши при рисовании"""
        if not self.is_drawing:
            return

        self.temp_drawing.update_drawing(scene_pos)

    def handle_mouse_click(self, scene_pos: QPointF, double_click: bool = False):
        """Обрабатывает клик мыши при рисовании объекта"""
        if not self.is_drawing:
            return

        if self.current_object_type == ObjectType.POINT:
            self._handle_point_click(scene_pos, double_click)
        elif self.current_object_type == ObjectType.LINEAR:
            self._handle_linear_click(scene_pos, double_click)
        elif self.current_object_type == ObjectType.STATIONARY:
            self._handle_stationary_click(scene_pos, double_click)

    def _handle_point_click(self, scene_pos: QPointF, double_click: bool = False):
        """Обработка клика для точечного объекта"""
        if self.is_point_array:
            # Первый клик двойного щелчка уже добавил последнюю точку.
            # Допускаем небольшое смещение мыши между двумя нажатиями.
            repeats_last = False
            if double_click and self.temp_coordinates:
                last = self.temp_coordinates[-1]
                screen_delta = self.main_window.view.mapFromScene(scene_pos) - \
                    self.main_window.view.mapFromScene(QPointF(last.x, last.y))
                repeats_last = screen_delta.manhattanLength() <= QApplication.startDragDistance()
            duplicate = any(
                c.x == scene_pos.x() and c.y == scene_pos.y()
                for c in self.temp_coordinates
            )
            if not repeats_last and not duplicate:
                self.temp_coordinates.append(Coordinate(
                    None, 0, scene_pos.x(), scene_pos.y(), len(self.temp_coordinates)
                ))
                self.temp_drawing.add_point(scene_pos)
            self._show_array_status()
            if double_click:
                self.finish_point_array()
            return

        coord = Coordinate(None, 0, scene_pos.x(), scene_pos.y(), 0)
        self.temp_coordinates = [coord]

        # Отображаем временную точку
        self.temp_drawing.start_drawing("point", scene_pos)
        self._finish_drawing()

    def _handle_linear_click(self, scene_pos: QPointF, double_click: bool):
        """Обработка клика для линейного объекта"""
        coord = Coordinate(None, 0, scene_pos.x(), scene_pos.y(), len(self.temp_coordinates))
        self.temp_coordinates.append(coord)

        # Обновляем временное отображение
        if len(self.temp_coordinates) == 1:
            self.temp_drawing.start_drawing("linear", scene_pos)
        else:
            self.temp_drawing.add_vertex(scene_pos)

        if double_click and len(self.temp_coordinates) >= 2:
            self._finish_drawing()

    def _handle_stationary_click(self, scene_pos: QPointF, double_click: bool):
        """Обработка клика для стационарного объекта"""
        if double_click and len(self.temp_coordinates) >= 3:
            # Замыкаем контур
            first_coord = self.temp_coordinates[0]
            last_coord = Coordinate(None, 0, first_coord.x, first_coord.y, len(self.temp_coordinates))
            self.temp_coordinates.append(last_coord)

            # Замыкаем временное отображение
            self.temp_drawing.close_polygon()
            self._finish_drawing()
        else:
            coord = Coordinate(None, 0, scene_pos.x(), scene_pos.y(), len(self.temp_coordinates))
            self.temp_coordinates.append(coord)

            # Обновляем временное отображение
            if len(self.temp_coordinates) == 1:
                self.temp_drawing.start_drawing("stationary", scene_pos)
            else:
                self.temp_drawing.add_vertex(scene_pos)

    def _finish_drawing(self):
        """Завершает процесс рисования объекта"""
        if self.is_point_array:
            self.finish_point_array()
            return
        name, ok = QInputDialog.getText(self.main_window, "Название объекта",
                                        "Введите название объекта:", QLineEdit.Normal)
        if ok and name:
            new_object = Object(
                id=None,
                image_id=self._get_current_image_id(),
                name=name,
                R1=0.0, R2=0.0, R3=0.0, R4=0.0, R5=0.0, R6=0.0,
                object_type=self.current_object_type,
                coordinates=self.temp_coordinates
            )

            if not self._save_object(new_object):
                return  # Оставляем точки для повторной попытки или отмены.
            self._update_display()

        self.cancel_drawing()

    def finish_point_array(self):
        """Сохраняет каждую введенную точку отдельным объектом одной транзакцией."""
        if not (self.is_drawing and self.is_point_array and self.temp_coordinates):
            return
        try:
            with DatabaseManager(self.main_window.db_handler.current_db_path) as db:
                names = db.conn.execute(
                    "SELECT name FROM objects WHERE image_id = ?", (self._get_current_image_id(),)
                ).fetchall()
                numbers = [
                    int(match.group(1)) for (name,) in names
                    if (match := re.fullmatch(r"массив_(\d+)", name))
                ]
                first_number = max(numbers, default=0) + 1
                objects = [
                    Object(
                        id=None, image_id=self._get_current_image_id(),
                        name=f"массив_{first_number + i}",
                        R1=0.0, R2=0.0, R3=0.0, R4=0.0, R5=0.0, R6=0.0,
                        object_type=ObjectType.POINT,
                        coordinates=[Coordinate(None, 0, coord.x, coord.y, 0)]
                    )
                    for i, coord in enumerate(self.temp_coordinates)
                ]
                db.objects.create_many(objects)
        except Exception as e:
            QMessageBox.critical(self.main_window, "Ошибка",
                                 f"Не удалось сохранить точки: {str(e)}")
            return  # Ни одна точка не записана; можно повторить Enter или отменить.
        self._update_display()
        self.cancel_drawing()
        self.main_window.statusBar().showMessage(
            f"Сохранено отдельных точечных объектов: {len(objects)}",
            self.main_window.time_status
        )

    def cancel_drawing(self):
        """Отменяет ввод, не записывая временные координаты в базу."""
        self.temp_drawing.clear_temp_items()

        # Сбрасываем состояние рисования
        self.is_drawing = False
        self.is_point_array = False
        self.current_object_type = None
        self.current_object = None
        self.temp_coordinates = []
        self.main_window.view.setCursor(Qt.ArrowCursor)
        self.main_window.statusBar().clearMessage()

    def _save_object(self, obj: Object):
        """Сохраняет объект в базу данных"""
        try:
            with DatabaseManager(self.main_window.db_handler.current_db_path) as db:
                obj.id = db.objects.create(obj)
            return True
        except Exception as e:
            QMessageBox.critical(self.main_window, "Ошибка",
                                 f"Не удалось сохранить объект: {str(e)}")
            return False

    def _update_display(self):
        """Обновляет отображение объектов на плане и в таблице"""
        # Обновляем таблицу объектов
        self.main_window.load_objects_from_image(self._get_current_image_id())

    def _get_current_image_id(self) -> int:
        """Получает ID текущего изображения"""
        return self.main_window.current_image_id
