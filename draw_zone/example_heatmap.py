import sys
import numpy as np
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QGraphicsScene, QGraphicsView
from PySide6.QtGui import QImage, QPixmap, QColor, QPainter
from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QRectF
from shapely.geometry import Point, LineString, Polygon
from shapely.geometry.base import BaseGeometry

import time


# Предопределенная палитра цветов
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

# Константы для многоуровневого поиска
SEARCH_STEPS = [100, 20, 5, 1]

OBJECTS = [
    {
        'id': 1,
        'name': 'Точечный объект 1',
        'type': 'point',  # Возможные значения: 'point', 'linear', 'stationary'
        'R1': 10.0,
        'R2': 20.0,
        'R3': 30.0,
        'R4': 40.0,
        'R5': 50.0,
        'R6': 60.0,
        'coordinates': '(1051.1, 673.7)'  # Для точечного объекта
    },
    {
        'id': 2,
        'name': 'Линейный объект 1',
        'type': 'linear',
        'R1': 10.0,
        'R2': 20.0,
        'R3': 30.0,
        'R4': 40.0,
        'R5': 50.0,
        'R6': 60.0,
        'coordinates': '(877.4, 613.6); (1092.4, 610.7); (1195.7, 467.4); (1453.7, 490.3); (1568.4, 576.3); (1459.4, 685.3); (1422.2, 831.5); (1528.3, 868.8); (1528.3, 868.8)'
        # Для линейного объекта
    },
    {
        'id': 3,
        'name': 'Стационарный объект 1',
        'type': 'stationary',
        'R1': 10.0,
        'R2': 20.0,
        'R3': 30.0,
        'R4': 40.0,
        'R5': 50.0,
        'R6': 60.0,
        'coordinates': '(1585.6, 639.4); (1688.8, 599.3); (1749.0, 490.3); (1677.4, 415.8); (1594.2, 381.3); (1511.1, 381.3); (1436.5, 450.2); (1436.5, 527.6); (1482.4, 567.7); (1493.8, 582.1); (1493.8, 582.1); (1585.6, 639.4)'
        # Для стационарного объекта (замкнутый контур)
    }
]


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



class RadiationMapWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Radiation Map Visualization")

        # Создаем сцену
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.setCentralWidget(self.view)
        self.heatmap = 0
        # е. Пул потоков
        self.threadpool = QThreadPool()
        self.resize(800, 800)
        # Добавляем переменные для отслеживания времени
        self.start_time = 0
        self.object_times = {}
        self.draw_risk()

    def draw_risk(self):
        print("Starting draw_risk calculations...")  # Отладочный вывод
        # Засекаем общее время начала
        self.start_time = time.time()
        # очистим сцену перед новой отрисовкой
        self.scene.clear()

        # 2. Получить данные
        # 2.1. О масштабе
        scale_plan = 0.143  # в одном пикселе 0,143 метра

        # 2.2. Получить координаты и типы объектов
        # очистим матрицу результатов
        scene_width = 2300
        scene_height = 2300
        print(f"Scene dimensions: {scene_width}x{scene_height}")  # Отладочный вывод

        self.heatmap = np.zeros((scene_width, scene_height))

        for obj in OBJECTS:
            print(f"Processing object: {obj['name']}")  # Отладочный вывод
            # Засекаем время для объекта
            self.object_times[obj['name']] = time.time()
            worker = RadiationWorker(scene_width, scene_height, obj, scale_plan, blurring=1)
            worker.signals.result.connect(self.worker_output)
            worker.signals.finished.connect(lambda name=obj['name']: self.worker_complete(name))
            self.threadpool.start(worker)

    def worker_output(self, s):
        print("Worker output received")  # Отладочный вывод
        self.heatmap = self.heatmap + s
        if self.threadpool.activeThreadCount() == 0:
            total_time = time.time() - self.start_time
            print("\nProcessing complete!")
            print(f"Total execution time: {total_time:.2f} seconds")
            print("\nExecution times for each object:")
            for name, start_time in self.object_times.items():
                object_time = time.time() - start_time
                print(f"{name}: {object_time:.2f} seconds")

            print("\nAll workers completed, generating heatmap")  # Отладочный вывод
            # Нарисуем тепловую карту
            qimg = self.show_heat_map(self.heatmap)
            # Преобразуем QImage в QPixmap и добавим на сцену
            pixmap = QPixmap.fromImage(qimg)
            self.scene.addPixmap(pixmap)
            # Установим размеры сцены по размеру изображения
            self.scene.setSceneRect(QRectF(pixmap.rect()))
            # Масштабируем view чтобы было видно всё изображение
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def worker_complete(self, obj_name):
        object_time = time.time() - self.object_times[obj_name]
        print(f"Thread complete for {obj_name}. Time taken: {object_time:.2f} seconds")

    def show_heat_map(self, zeros_array):
        print("Generating heatmap visualization")  # Отладочный вывод
        print(f"Array max value: {np.max(zeros_array)}, min value: {np.min(zeros_array)}")

        bins = np.array([i * np.max(zeros_array) / 30 for i in range(1, 31)])
        digitize = np.digitize(zeros_array, bins, right=True)
        digitize = np.expand_dims(digitize, axis=2)
        # Поворачиваем против часовой стрелки и отражаем
        digitize = np.fliplr(digitize)
        digitize = np.rot90(digitize, k=-3)
        digitize = np.fliplr(digitize)
        digitize = np.rot90(digitize, k=1)

        im = np.choose(digitize, PALETTE, mode='clip')
        h, w, _ = im.shape
        print(f"Generated image dimensions: {w}x{h}")  # Отладочный вывод
        qimg_zone = QImage(im.data, w, h, 4 * w, QImage.Format_ARGB32)
        return qimg_zone

def main():
    print("Starting Radiation Map Generator")

    # Создаем приложение и окно визуализации
    print("\nInitializing Qt application...")
    app = QApplication(sys.argv)

    print("\nCreating visualization window...")
    window = RadiationMapWindow()
    window.show()

    print("\nApplication started")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
