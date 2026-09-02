from PySide6.QtWidgets import QGraphicsPixmapItem
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import QObject, Signal, QRunnable
import numpy as np
from shapely import distance as shapely_distance, points as shapely_points
from shapely.geometry import Point, LineString, Polygon
from iris_db.database import DatabaseManager

# Используем те же константы, что и в example_heatmap.py
PALETTE = np.array([
    [255, 255, 255, 255], [0, 50, 255, 255], [0, 100, 255, 255],
    [0, 120, 255, 255], [0, 140, 255, 255], [0, 160, 255, 255],
    [0, 190, 255, 255], [0, 210, 255, 255], [0, 220, 255, 255],
    [0, 255, 255, 255], [100, 255, 255, 255], [130, 255, 0, 255],
    [150, 255, 0, 255], [180, 255, 0, 255], [200, 255, 0, 255],
    [220, 255, 0, 255], [230, 255, 0, 255], [240, 255, 0, 255],
    [255, 255, 0, 255], [255, 230, 0, 255], [255, 210, 0, 255],
    [255, 200, 0, 255], [255, 190, 0, 255], [255, 170, 0, 255],
    [255, 150, 0, 255], [255, 120, 0, 255], [255, 80, 0, 255],
    [255, 60, 0, 255], [255, 30, 0, 255], [255, 0, 0, 255]
], dtype='uint8')
PALETTE[:, [0, 2]] = PALETTE[:, [2, 0]]  # Swap R and B channels

ROW_CHUNK_SIZE = 256


class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(str)
    result = Signal(object)


class RadiationWorker(QRunnable):
    def __init__(self, width: int, height: int, object_in_table: dict, scale_plan: float,
                 blurring: int):
        super().__init__()
        self.signals = WorkerSignals()
        self.width = width
        self.height = height
        self.object_in_table = object_in_table
        self.scale_plan = scale_plan
        self.blurring = blurring

    def run(self):
        try:
            result = self.calculate()
        except Exception as e:
            self.signals.error.emit(str(e))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()

    def calculate(self) -> tuple[int, int, np.ndarray]:
        """Вычисляет фрагмент зоны риска для одного объекта."""
        radius = int(self.object_in_table['R6'])
        if radius <= 0:
            raise ValueError("Радиус R6 должен быть больше нуля")

        obj = self.create_shapely_object()
        x_min, y_min, x_max, y_max = self._calculation_bounds(obj, radius)

        if x_min > x_max or y_min > y_max:
            return 0, 0, np.zeros((0, 0), dtype=np.float64)

        return (
            x_min,
            y_min,
            self._calculate_fragment(
                obj,
                radius,
                x_min,
                y_min,
                x_max,
                y_max
            )
        )

    def _calculation_bounds(self, obj, radius: int) -> tuple[int, int, int, int]:
        """Возвращает ограниченную планом область возможного воздействия."""
        min_x, min_y, max_x, max_y = obj.bounds
        return (
            max(0, int(np.floor(min_x - radius))),
            max(0, int(np.floor(min_y - radius))),
            min(self.width - 1, int(np.ceil(max_x + radius))),
            min(self.height - 1, int(np.ceil(max_y + radius)))
        )

    @staticmethod
    def _power_from_distances(distances: np.ndarray, radius: int) -> np.ndarray:
        """Повторяет исходное округление расстояния через int()."""
        integer_distances = np.floor(distances).astype(np.int64)
        values = np.zeros(distances.shape, dtype=np.float64)
        affected = integer_distances <= radius
        values[affected] = (
            radius - np.maximum(integer_distances[affected], 1)
        ) / 100.0
        return values

    def _calculate_fragment(self, obj, radius: int, x_min: int, y_min: int,
                            x_max: int, y_max: int) -> np.ndarray:
        """Векторно вычисляет воздействие порциями строк."""
        x_coordinates = np.arange(x_min, x_max + 1, dtype=np.float64)
        fragment = np.zeros(
            (y_max - y_min + 1, x_max - x_min + 1),
            dtype=np.float64
        )

        for start_y in range(y_min, y_max + 1, ROW_CHUNK_SIZE):
            stop_y = min(start_y + ROW_CHUNK_SIZE, y_max + 1)
            y_coordinates = np.arange(start_y, stop_y, dtype=np.float64)
            x_grid, y_grid = np.meshgrid(x_coordinates, y_coordinates)
            grid_points = shapely_points(x_grid, y_grid)
            distances = shapely_distance(grid_points, obj)
            row_offset = start_y - y_min
            fragment[row_offset:row_offset + len(y_coordinates)] = (
                self._power_from_distances(distances, radius)
            )

        return fragment

    def create_shapely_object(self):
        """
        Создает геометрический объект Shapely из данных таблицы
        """
        source_coordinates = self.object_in_table['coordinates']
        if isinstance(source_coordinates, str):
            coord_pairs = source_coordinates.replace('(', '').replace(')', '').split('; ')
            coords = [tuple(map(float, pair.split(','))) for pair in coord_pairs]
        else:
            coords = [(float(x), float(y)) for x, y in source_coordinates]

        obj_type = self.object_in_table['type']

        if obj_type == 'point':
            return Point(coords[0])
        elif obj_type == 'linear':
            return LineString(coords)
        elif obj_type == 'stationary':
            return Polygon(coords)
        else:
            raise ValueError(f"Неизвестный тип объекта: {obj_type}")

class RiskCalculator:
    def __init__(self, main_window):
        self.main_window = main_window
        self.heatmap = np.zeros((1, 1))

    def calculate_risk(self, objects):
        """Вычисляет зоны риска для списка объектов"""
        scene_rect = self.main_window.scene.sceneRect()
        width = int(scene_rect.width())
        height = int(scene_rect.height())

        self.heatmap = np.zeros((height, width))

        for obj in objects:
            # Преобразуем Object в словарь
            obj_dict = {
                'name': obj.name,
                'type': obj.object_type.value,
                'R1': obj.R1,
                'R2': obj.R2,
                'R3': obj.R3,
                'R4': obj.R4,
                'R5': obj.R5,
                'R6': obj.R6,
                'coordinates': [(c.x, c.y) for c in obj.coordinates]
            }

            worker = RadiationWorker(
                width,
                height,
                obj_dict,
                self.main_window.scale_for_plan,
                blurring=1
            )
            self.worker_output(worker.calculate())

        return self.create_risk_pixmap(self.heatmap)

    def worker_output(self, result):
        """Обработка результата от worker'а"""
        x_min, y_min, result_array = result
        height, width = result_array.shape
        if height and width:
            self.heatmap[y_min:y_min + height, x_min:x_min + width] += result_array

    def create_risk_pixmap(self, heatmap):
        bins = np.array([i * np.max(heatmap) / 30 for i in range(1, 31)])
        digitize = np.digitize(heatmap, bins, right=True)
        digitize = np.expand_dims(digitize, axis=2)
        # Поворачиваем против часовой стрелки и отражаем
        digitize = np.fliplr(digitize)
        digitize = np.rot90(digitize, k=-3)
        digitize = np.fliplr(digitize)
        digitize = np.rot90(digitize, k=1)

        im = np.choose(digitize, PALETTE, mode='clip')
        h, w, _ = im.shape
        # Находим белые пиксели (RGB = 255,255,255) и делаем их прозрачными
        white_pixels = (im[..., 0] == 255) & (im[..., 1] == 255) & (im[..., 2] == 255)
        im[white_pixels, 3] = 0  # Устанавливаем альфа-канал в 0 для белых пикселей
        image = QImage(im.data, w, h, 4 * w, QImage.Format_ARGB32)

        return QPixmap.fromImage(image)


def draw_risk_zones(main_window) -> bool:
    """Отрисовывает зоны риска для всех объектов на плане"""
    # Проверяем, что план загружен
    if not main_window.is_plan_loaded():
        main_window.statusBar().showMessage(
            "Сначала необходимо загрузить план",
            3000
        )
        return False

    # Проверяем, что масштаб задан
    if not main_window.scale_for_plan:
        main_window.statusBar().showMessage(
            "Сначала необходимо измерить масштаб",
            3000
        )
        return False

    try:
        # Получаем все объекты текущего плана
        with DatabaseManager(main_window.db_handler.current_db_path) as db:
            objects = db.objects.get_by_image_id(main_window.current_image_id)

            if not objects:
                main_window.statusBar().showMessage(
                    "На плане нет объектов для отрисовки",
                    3000
                )
                return False

            # Создаем калькулятор и выполняем расчет
            calculator = RiskCalculator(main_window)
            risk_pixmap = calculator.calculate_risk(objects)

            # Создаем и добавляем элемент на сцену
            risk_item = QGraphicsPixmapItem(risk_pixmap)
            risk_item.setOpacity(0.6)
            main_window.scene.addItem(risk_item)

            main_window.statusBar().showMessage(
                "Зоны риска отрисованы",
                3000
            )
            return True

    except Exception as e:
        main_window.statusBar().showMessage(
            f"Ошибка при отрисовке зон риска: {str(e)}",
            3000
        )
        return False
