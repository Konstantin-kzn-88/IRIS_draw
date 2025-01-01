from PySide6.QtWidgets import QGraphicsItem, QGraphicsEllipseItem, QGraphicsPathItem
from PySide6.QtGui import QPen, QColor, QPainterPath
from PySide6.QtCore import Qt
from iris_db.models import Object, ObjectType


class BaseObjectItem:
    """Базовый класс для всех объектов на плане"""

    def __init__(self, obj: Object):
        self.object = obj
        self._is_highlighted = False
        self.items = []
        self.is_valid = True  # Флаг валидности объекта
        self.set_visible(False)

    def set_visible(self, visible: bool):
        """Устанавливает видимость объекта"""
        if not self.is_valid:
            return
        try:
            for item in self.items:
                if item and item.scene():  # Проверяем, что элемент существует и привязан к сцене
                    item.setVisible(visible)
        except RuntimeError:
            self.is_valid = False  # Помечаем объект как недействительный
            self.items = []  # Очищаем список элементов

    def highlight(self, enabled=True):
        """Подсвечивает или снимает подсветку с объекта"""
        if not self.is_valid:
            return
        try:
            self._is_highlighted = enabled
            color = QColor('red') if enabled else QColor('blue')
            width = 3 if enabled else 1
            for item in self.items:
                if item and item.scene() and isinstance(item, (QGraphicsEllipseItem, QGraphicsPathItem)):
                    pen = QPen(color, width)
                    if enabled:
                        pen.setStyle(Qt.SolidLine)
                    item.setPen(pen)
        except RuntimeError:
            self.is_valid = False
            self.items = []

    def cleanup(self):
        """Очищает графические элементы объекта"""
        if not self.is_valid:
            return
        try:
            for item in self.items:
                if item and item.scene():
                    item.scene().removeItem(item)
            self.items = []
            self.is_valid = False
        except RuntimeError:
            self.is_valid = False
            self.items = []

class PointObjectItem(BaseObjectItem):
    """Класс для отображения точечных объектов"""

    def __init__(self, obj: Object, scene):
        super().__init__(obj)

        # Создаем круг в точке расположения объекта
        coord = obj.coordinates[0]
        radius = 5  # Радиус точки в пикселях
        ellipse = QGraphicsEllipseItem(
            coord.x - radius,
            coord.y - radius,
            radius * 2,
            radius * 2
        )

        # Настраиваем отображение
        pen = QPen(QColor('blue'), 1)
        ellipse.setPen(pen)

        self.items.append(ellipse)
        scene.addItem(ellipse)


class LinearObjectItem(BaseObjectItem):
    """Класс для отображения линейных объектов"""

    def __init__(self, obj: Object, scene):
        super().__init__(obj)

        # Создаем путь из точек объекта
        path = QPainterPath()
        first_coord = obj.coordinates[0]
        path.moveTo(first_coord.x, first_coord.y)

        for coord in obj.coordinates[1:]:
            path.lineTo(coord.x, coord.y)

        # Создаем элемент пути
        path_item = QGraphicsPathItem(path)
        pen = QPen(QColor('blue'), 1)
        path_item.setPen(pen)

        self.items.append(path_item)
        scene.addItem(path_item)


class StationaryObjectItem(BaseObjectItem):
    """Класс для отображения стационарных объектов"""

    def __init__(self, obj: Object, scene):
        super().__init__(obj)

        # Создаем замкнутый полигон
        path = QPainterPath()
        first_coord = obj.coordinates[0]
        path.moveTo(first_coord.x, first_coord.y)

        for coord in obj.coordinates[1:]:
            path.lineTo(coord.x, coord.y)

        path.closeSubpath()  # Замыкаем путь

        # Создаем элемент пути
        path_item = QGraphicsPathItem(path)
        pen = QPen(QColor('blue'), 1)
        path_item.setPen(pen)

        self.items.append(path_item)
        scene.addItem(path_item)


def create_object_item(obj: Object, scene) -> BaseObjectItem:
    """Фабричный метод для создания графических объектов"""
    if obj.object_type == ObjectType.POINT:
        return PointObjectItem(obj, scene)
    elif obj.object_type == ObjectType.LINEAR:
        return LinearObjectItem(obj, scene)
    elif obj.object_type == ObjectType.STATIONARY:
        return StationaryObjectItem(obj, scene)
    else:
        raise ValueError(f"Неподдерживаемый тип объекта: {obj.object_type}")