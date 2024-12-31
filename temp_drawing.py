from PySide6.QtWidgets import QGraphicsItem, QGraphicsEllipseItem, QGraphicsPathItem
from PySide6.QtGui import QPen, QColor, QPainterPath
from PySide6.QtCore import Qt, QPointF


class TempDrawingManager:
    """Класс для управления временными объектами при рисовании"""

    def __init__(self, scene):
        self.scene = scene
        self.temp_items = []
        self.current_path = None
        self.start_point = None

    def start_drawing(self, object_type, point: QPointF):
        """Начинает рисование объекта"""
        self.clear_temp_items()

        if object_type == "point":
            # Создаем временную точку
            radius = 5
            ellipse = QGraphicsEllipseItem(
                point.x() - radius,
                point.y() - radius,
                radius * 2,
                radius * 2
            )
            pen = QPen(QColor('red'), 2, Qt.DashLine)
            ellipse.setPen(pen)
            self.scene.addItem(ellipse)
            self.temp_items.append(ellipse)

        elif object_type in ["linear", "stationary"]:
            # Начинаем рисовать путь
            self.start_point = point
            self.current_path = QPainterPath()
            self.current_path.moveTo(point)

            path_item = QGraphicsPathItem(self.current_path)
            pen = QPen(QColor('red'), 2, Qt.DashLine)
            path_item.setPen(pen)
            self.scene.addItem(path_item)
            self.temp_items.append(path_item)

            # Добавляем точку начала
            self.add_vertex_marker(point)

    def update_drawing(self, point: QPointF):
        """Обновляет текущий рисуемый объект"""
        if not self.temp_items:
            return

        if self.current_path is not None:
            # Обновляем линейный или стационарный объект
            new_path = QPainterPath(self.current_path)
            new_path.lineTo(point)

            path_item = self.temp_items[0]
            path_item.setPath(new_path)

    def add_vertex(self, point: QPointF):
        """Добавляет новую вершину к текущему объекту"""
        if self.current_path is not None:
            self.current_path.lineTo(point)
            path_item = self.temp_items[0]
            path_item.setPath(self.current_path)

            # Добавляем маркер вершины
            self.add_vertex_marker(point)

    def add_vertex_marker(self, point: QPointF):
        """Добавляет маркер вершины"""
        radius = 3
        marker = QGraphicsEllipseItem(
            point.x() - radius,
            point.y() - radius,
            radius * 2,
            radius * 2
        )
        marker.setBrush(QColor('red'))
        marker.setPen(QPen(Qt.NoPen))
        self.scene.addItem(marker)
        self.temp_items.append(marker)

    def close_polygon(self):
        """Замыкает полигон для стационарного объекта"""
        if self.current_path is not None and self.start_point is not None:
            self.current_path.lineTo(self.start_point)
            path_item = self.temp_items[0]
            path_item.setPath(self.current_path)

    def clear_temp_items(self):
        """Удаляет все временные элементы"""
        for item in self.temp_items:
            self.scene.removeItem(item)
        self.temp_items.clear()
        self.current_path = None
        self.start_point = None