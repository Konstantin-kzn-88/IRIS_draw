import time

from PySide6.QtWidgets import QGraphicsPixmapItem, QApplication
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool
import numpy as np
from shapely.geometry import Point, LineString, Polygon
from iris_db.models import ObjectType
from iris_db.database import DatabaseManager

# Используем те же константы, что и в heatmap.py
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

SEARCH_STEPS = [100, 20, 5, 1]


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
        print(f"RadiationWorker initialized with dimensions: {width}x{height}")  # Debug print

    def run(self):
        try:
            print(f"Starting calculations for object {self.object_in_table['name']}")  # Debug print

            # создадим силу воздействия
            R6 = int(self.object_in_table['R6'])
            dist_power = [i for i in range(R6)]
            power = list(reversed([i / 100 for i in dist_power]))

            print(f"Power array created with length: {len(power)}")  # Debug print

            # нулевая матрица
            zeros_array = np.zeros((self.height, self.width))  # Изменен порядок размерностей

            # Создадим объект до которого идет измерение
            obj = self.create_shapely_object()
            print(f"Created shapely object: {obj}")  # Debug print

            # ШАГ 1.
            print("Starting step 1: 50px squares")
            find_square_50 = self.search_nearby_squares(
                x_min=0,
                x_max=self.width - 1,  # Уменьшаем на 1 чтобы не выйти за границы
                y_min=0,
                y_max=self.height - 1,
                size_search=SEARCH_STEPS[0],
                object_under_study=obj
            )
            print(f"Found {len(find_square_50) // 8} squares in step 1")  # Debug print

            # ШАГ 2.
            print("Starting step 2: 10px squares")
            find_square_10 = []
            for i in range(0, len(find_square_50), 8):
                sq = find_square_50[i:i + 8]
                result_square = self.search_nearby_squares(
                    x_min=sq[0],
                    x_max=min(sq[2], self.width - 1),
                    y_min=sq[1],
                    y_max=min(sq[5], self.height - 1),
                    size_search=SEARCH_STEPS[1],
                    object_under_study=obj
                )
                find_square_10.extend(result_square)
            print(f"Found {len(find_square_10) // 8} squares in step 2")  # Debug print

            # ШАГ 3.
            print("Starting step 3: 2px squares")
            find_square_2 = []
            for i in range(0, len(find_square_10), 8):
                sq = find_square_10[i:i + 8]
                result_square = self.search_nearby_squares(
                    x_min=sq[0],
                    x_max=min(sq[2], self.width - 1),
                    y_min=sq[1],
                    y_max=min(sq[5], self.height - 1),
                    size_search=SEARCH_STEPS[2],
                    object_under_study=obj
                )
                find_square_2.extend(result_square)
            print(f"Found {len(find_square_2) // 8} squares in step 3")  # Debug print

            # ШАГ 4.
            print("Starting step 4: individual points")
            find_coordinate_step_4 = []
            for i in range(0, len(find_square_2), 8):
                sq = find_square_2[i:i + 8]
                x_line = [i for i in range(sq[0], min(sq[2] + 1, self.width), SEARCH_STEPS[3])]
                y_line = [i for i in range(sq[1], min(sq[5] + 1, self.height), SEARCH_STEPS[3])]
                for x in x_line:
                    for y in y_line:
                        search_point = Point(x, y)
                        find_coordinate_step_4.append(search_point)

            print(f"Processing {len(find_coordinate_step_4)} points")  # Debug print

            # Удалим повторы точек и посчитаем в какой точке какое воздействие
            unique_points = list(set(find_coordinate_step_4))
            print(f"Processing {len(unique_points)} unique points")  # Debug print

            for item in unique_points:
                distance = int(item.distance(obj))
                x, y = int(item.x), int(item.y)

                # Проверка границ массива
                if 0 <= y < self.height and 0 <= x < self.width:
                    if distance == 0:
                        zeros_array[y, x] = max(power)
                    else:
                        if distance <= R6:
                            dist_index = min(distance - 1, len(dist_power) - 1)
                            zeros_array[y, x] = power[dist_index]

            print("Calculations completed successfully")  # Debug print

        except Exception as e:
            print(f"Error in calculations: {str(e)}")  # Debug print
            self.signals.error.emit(str(e))
            return

        self.signals.result.emit(zeros_array)
        self.signals.finished.emit()

    def create_shapely_object(self):
        """
        Создает геометрический объект Shapely из данных таблицы
        """
        # Преобразуем строку координат в список пар координат
        coords_str = self.object_in_table['coordinates']
        # Убираем скобки и разделяем по точке с запятой
        coord_pairs = coords_str.replace('(', '').replace(')', '').split('; ')
        # Преобразуем строки координат в числа
        coords = []
        for pair in coord_pairs:
            x, y = map(float, pair.split(','))
            coords.append((x, y))

        obj_type = self.object_in_table['type']

        if obj_type == 'point':
            return Point(coords[0])
        elif obj_type == 'linear':
            return LineString(coords)
        elif obj_type == 'stationary':
            return Polygon(coords)
        else:
            raise ValueError(f"Неизвестный тип объекта: {obj_type}")

    def search_nearby_squares(self, x_min: int, x_max: int, y_min: int, y_max: int,
                              size_search: int, object_under_study) -> list:
        """
        Функция поиска близлежащих координат
        """
        R6 = float(self.object_in_table['R6'])  # Преобразуем в float
        x_line = range(x_min, x_max + 1, size_search)
        y_line = range(y_min, y_max + 1, size_search)
        result_square = []

        for x in x_line:
            for y in y_line:
                # Создаем квадрат для проверки
                square_coords = [
                    (x, y),
                    (min(x + size_search, self.width), y),
                    (min(x + size_search, self.width), min(y + size_search, self.height)),
                    (x, min(y + size_search, self.height))
                ]
                search_polygon = Polygon(square_coords)

                try:
                    distance = search_polygon.distance(object_under_study)
                    if distance < R6:
                        result_square.extend([
                            x, y,
                            min(x + size_search, self.width), y,
                            min(x + size_search, self.width), min(y + size_search, self.height),
                            x, min(y + size_search, self.height)
                        ])
                except Exception as e:
                    print(f"Error calculating distance for square at ({x},{y}): {e}")
                    continue

        return result_square


class RiskCalculator:
    def __init__(self, main_window):
        self.main_window = main_window
        self.thread_pool = QThreadPool()
        self.heatmap = np.zeros((1, 1))
        self.start_time = time.time()
        self.object_times = {}

    def calculate_risk(self, objects):
        """Вычисляет зоны риска для списка объектов"""
        print("Starting calculate_risk")
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
                'coordinates': '; '.join([f"({c.x}, {c.y})" for c in obj.coordinates])
            }

            print(f"Processing object: {obj_dict['name']}")
            self.object_times[obj_dict['name']] = time.time()

            worker = RadiationWorker(
                width,
                height,
                obj_dict,
                self.main_window.scale_for_plan,
                blurring=1
            )
            worker.signals.result.connect(self.worker_output)
            worker.signals.finished.connect(
                lambda name=obj_dict['name']: self.worker_complete(name)
            )
            self.thread_pool.start(worker)

        # Ждем завершения всех расчетов
        while self.thread_pool.activeThreadCount() > 0:
            QApplication.processEvents()

        print("All workers completed")
        print(f"Final heatmap values - max: {np.max(self.heatmap)}, min: {np.min(self.heatmap)}")
        return self.create_risk_pixmap(self.heatmap)

    def worker_output(self, result_array):
        """Обработка результата от worker'а"""
        print("Received worker output")
        print(f"Result array max: {np.max(result_array)}, min: {np.min(result_array)}")
        self.heatmap = self.heatmap + result_array

    def worker_complete(self, obj_name):
        """Обработка завершения worker'а"""
        object_time = time.time() - self.object_times[obj_name]
        print(f"Worker complete for {obj_name}. Time taken: {object_time:.2f} seconds")

    def create_risk_pixmap(self,heatmap):
        print("Generating heatmap visualization")  # Отладочный вывод
        print(f"Array max value: {np.max(heatmap)}, min value: {np.min(heatmap)}")

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
        print(f"Generated image dimensions: {w}x{h}")  # Отладочный вывод
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