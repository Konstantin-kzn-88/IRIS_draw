from PySide6.QtWidgets import QMainWindow, QGraphicsScene, QMessageBox
from PySide6.QtGui import QPen, QColor, QPainterPath
from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsEllipseItem


class MeasurementTools:
    """Класс для измерения длины и площади на плане"""

    def __init__(self, main_window: QMainWindow):
        self.main_window = main_window
        self.scene = main_window.scene
        self.is_measuring = False
        self.measure_type = None  # 'length' или 'area'
        self.points = []
        self.temp_items = []
        self.current_path = None
        self.path_item = None

    def start_length_measurement(self):
        """Начинает измерение длины"""
        if not self._check_prerequisites():
            return

        self.measure_type = 'length'
        self.is_measuring = True
        self.points = []
        self._clear_temp_items()
        self.main_window.view.setCursor(Qt.CrossCursor)
        self.main_window.statusBar().showMessage(
            "Кликайте для добавления точек линии. Двойной клик для завершения измерения"
        )

    def start_area_measurement(self):
        """Начинает измерение площади"""
        if not self._check_prerequisites():
            return

        self.measure_type = 'area'
        self.is_measuring = True
        self.points = []
        self._clear_temp_items()
        self.main_window.view.setCursor(Qt.CrossCursor)
        self.main_window.statusBar().showMessage(
            "Кликайте для добавления точек области. Двойной клик для замыкания и измерения"
        )

    def handle_mouse_click(self, scene_pos: QPointF, double_click: bool = False):
        """Обрабатывает клик мыши при измерении"""
        if not self.is_measuring:
            return

        self.points.append(scene_pos)

        # Добавляем маркер точки
        self._add_point_marker(scene_pos)

        # Обновляем путь
        if len(self.points) > 1:
            self._update_path()

        # Обрабатываем завершение измерения
        if double_click:
            if self.measure_type == 'length' and len(self.points) >= 2:
                self._finish_length_measurement()
            elif self.measure_type == 'area' and len(self.points) >= 3:
                self._finish_area_measurement()

    def handle_mouse_move(self, scene_pos: QPointF):
        """Обрабатывает движение мыши при измерении"""
        if not self.is_measuring or not self.points:
            return

        # Создаем временный путь для отображения текущей линии
        if not self.current_path:
            self.current_path = QPainterPath()

        self.current_path.clear()
        self.current_path.moveTo(self.points[0])

        for point in self.points[1:]:
            self.current_path.lineTo(point)

        self.current_path.lineTo(scene_pos)

        if self.measure_type == 'area' and len(self.points) >= 2:
            self.current_path.lineTo(self.points[0])

        if not self.path_item:
            self.path_item = QGraphicsPathItem()
            pen = QPen(QColor('blue'), 2, Qt.DashLine)
            self.path_item.setPen(pen)
            self.scene.addItem(self.path_item)
            self.temp_items.append(self.path_item)

        self.path_item.setPath(self.current_path)

    def _check_prerequisites(self) -> bool:
        """Проверяет необходимые условия для начала измерения"""
        if not self.main_window.is_plan_loaded():
            QMessageBox.warning(
                self.main_window,
                "Предупреждение",
                "Сначала загрузите план"
            )
            return False

        if not self.main_window.scale_for_plan:
            QMessageBox.warning(
                self.main_window,
                "Предупреждение",
                "Сначала задайте масштаб"
            )
            return False

        return True

    def _add_point_marker(self, point: QPointF):
        """Добавляет маркер точки на сцену"""
        radius = 3
        marker = QGraphicsEllipseItem(
            point.x() - radius,
            point.y() - radius,
            radius * 2,
            radius * 2
        )
        marker.setBrush(QColor('blue'))
        marker.setPen(QPen(Qt.NoPen))
        self.scene.addItem(marker)
        self.temp_items.append(marker)

    def _update_path(self):
        """Обновляет путь на сцене"""
        if not self.current_path:
            self.current_path = QPainterPath()
            self.path_item = QGraphicsPathItem()
            pen = QPen(QColor('blue'), 2, Qt.DashLine)
            self.path_item.setPen(pen)
            self.scene.addItem(self.path_item)
            self.temp_items.append(self.path_item)

        self.current_path.clear()
        self.current_path.moveTo(self.points[0])

        for point in self.points[1:]:
            self.current_path.lineTo(point)

        if self.measure_type == 'area':
            self.current_path.lineTo(self.points[0])

        self.path_item.setPath(self.current_path)

    def _calculate_length(self) -> float:
        """Вычисляет общую длину линии в метрах"""
        total_length = 0
        for i in range(len(self.points) - 1):
            p1 = self.points[i]
            p2 = self.points[i + 1]
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            length_pixels = (dx * dx + dy * dy) ** 0.5
            total_length += length_pixels * self.main_window.scale_for_plan
        return total_length

    def _calculate_area(self) -> float:
        """Вычисляет площадь многоугольника в квадратных метрах"""
        # Используем формулу площади Гаусса
        area = 0
        n = len(self.points)
        for i in range(n):
            j = (i + 1) % n
            area += self.points[i].x() * self.points[j].y()
            area -= self.points[j].x() * self.points[i].y()
        area = abs(area) / 2
        # Переводим площадь из квадратных пикселей в квадратные метры
        return area * (self.main_window.scale_for_plan ** 2)

    def _finish_length_measurement(self):
        """Завершает измерение длины"""
        length = self._calculate_length()
        QMessageBox.information(
            self.main_window,
            "Результат измерения",
            f"Общая длина: {length:.2f} метров"
        )
        self._finish_measurement()

    def _finish_area_measurement(self):
        """Завершает измерение площади"""
        area = self._calculate_area()
        QMessageBox.information(
            self.main_window,
            "Результат измерения",
            f"Площадь: {area:.2f} кв. метров"
        )
        self._finish_measurement()

    def _finish_measurement(self):
        """Завершает процесс измерения"""
        self.is_measuring = False
        self._clear_temp_items()
        self.points = []
        self.current_path = None
        self.path_item = None
        self.main_window.view.setCursor(Qt.ArrowCursor)
        self.main_window.statusBar().clearMessage()

    def _clear_temp_items(self):
        """Удаляет все временные элементы со сцены"""
        for item in self.temp_items:
            self.scene.removeItem(item)
        self.temp_items.clear()