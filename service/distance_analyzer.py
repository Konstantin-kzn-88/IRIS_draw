# distance_analyzer.py
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QVBoxLayout
from PySide6.QtCore import Qt
from iris_db.models import Object, ObjectType
from shapely.geometry import Point, LineString, Polygon


class DistanceAnalyzer:
    """Класс для анализа расстояний между объектами на плане"""

    def __init__(self, parent=None):
        self.parent = parent
        self.distances = {}  # Словарь для хранения расстояний
        self.objects = []  # Список объектов

    def create_shapely_object(self, obj: Object):
        """Создает геометрический объект Shapely из объекта на плане"""
        if not obj.coordinates:
            return None

        coords = [(coord.x, coord.y) for coord in obj.coordinates]

        if obj.object_type == ObjectType.POINT:
            return Point(coords[0])

        elif obj.object_type == ObjectType.LINEAR:
            return LineString(coords)

        elif obj.object_type == ObjectType.STATIONARY:
            # Для полигона первая и последняя точки должны совпадать
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            return Polygon(coords)

        return None

    def calculate_distance(self, obj1: Object, obj2: Object, scale: float) -> float:
        """Вычисляет минимальное расстояние между двумя объектами в метрах"""
        geom1 = self.create_shapely_object(obj1)
        geom2 = self.create_shapely_object(obj2)

        if not geom1 or not geom2:
            return 0.0

        # Shapely вычисляет минимальное расстояние между объектами
        pixels = geom1.distance(geom2)

        # Переводим в метры с учетом масштаба
        return pixels * scale

    def analyze_objects(self, objects: list, scale: float):
        """Анализирует расстояния между всеми объектами"""
        self.objects = objects
        self.distances.clear()

        # Вычисляем расстояния между всеми парами объектов
        for i, obj1 in enumerate(objects):
            self.distances[obj1.id] = {}
            for j, obj2 in enumerate(objects):
                if obj1.id == obj2.id:
                    self.distances[obj1.id][obj2.id] = 0
                else:
                    distance = self.calculate_distance(obj1, obj2, scale)
                    self.distances[obj1.id][obj2.id] = round(distance, 1)

    def create_distance_table(self) -> QTableWidget:
        """Создает таблицу с расстояниями между объектами"""
        table = QTableWidget()
        n = len(self.objects)

        # Настраиваем таблицу
        table.setRowCount(n + 1)  # +1 для заголовка
        table.setColumnCount(n + 1)  # +1 для названий строк

        # Устанавливаем заголовки
        table.setItem(0, 0, QTableWidgetItem("Наименование"))
        for i, obj in enumerate(self.objects, 1):
            header_item = QTableWidgetItem(obj.name)
            table.setItem(0, i, header_item)
            table.setItem(i, 0, QTableWidgetItem(obj.name))

        # Заполняем значения расстояний
        for i, obj1 in enumerate(self.objects, 1):
            for j, obj2 in enumerate(self.objects, 1):
                if obj1.id == obj2.id:
                    item = QTableWidgetItem("-")
                else:
                    distance = self.distances[obj1.id][obj2.id]
                    item = QTableWidgetItem(str(distance))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(i, j, item)

        # Настраиваем внешний вид
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setVisible(False)

        v_header = table.verticalHeader()
        v_header.setVisible(False)

        return table

    def get_distance_widget(self) -> QWidget:
        """Создает виджет с таблицей расстояний"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        table = self.create_distance_table()
        layout.addWidget(table)

        return widget