# main.py
import sys
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QMenuBar, QMenu, QGraphicsView, QGraphicsScene,
                               QFileDialog, QGraphicsLineItem)
from PySide6.QtGui import QAction, QPixmap, QPainter

from database_handler import DatabaseHandler
from PySide6.QtWidgets import QInputDialog
from PySide6.QtWidgets import QGraphicsPixmapItem


from PySide6.QtCore import Qt, QPointF, QLineF
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QDialog

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from iris_db.models import Object, ObjectType

from PySide6.QtWidgets import QSplitter, QTableWidget, QTableWidgetItem
from iris_db.database import DatabaseManager

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget,
                              QTableWidgetItem, QPushButton, QHeaderView)
from iris_db.database import DatabaseManager

from plan_dialog import SelectPlanDialog
from object_table import ObjectTableWidget
from object_items import create_object_item


class ScaleGraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.scale_mode = False
        self.scale_points = []
        self.scale_line = None
        self.temp_line = None
        self.parent = parent

        # Включаем отслеживание мыши
        self.setMouseTracking(True)

        # Параметры масштабирования
        self.zoom_factor = 1.15  # Коэффициент масштабирования
        self.min_scale = 0.1  # Минимальный масштаб
        self.max_scale = 10.0  # Максимальный масштаб
        self.current_scale = 1.0  # Текущий масштаб

        # Параметры перетаскивания
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.last_mouse_pos = None
        self.panning = False

        # Включаем преобразования видового окна
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # Включаем сглаживание
        self.setRenderHints(QPainter.RenderHint.Antialiasing |
                            QPainter.RenderHint.SmoothPixmapTransform)

    def wheelEvent(self, event):
        """Обработка события прокрутки колесика мыши"""
        if event.angleDelta().y() > 0:
            # Увеличение масштаба
            zoom_in = True
            factor = self.zoom_factor
        else:
            # Уменьшение масштаба
            zoom_in = False
            factor = 1.0 / self.zoom_factor

        # Проверяем, не выходит ли новый масштаб за пределы
        new_scale = self.current_scale * factor
        if new_scale < self.min_scale or new_scale > self.max_scale:
            return

        # Применяем масштабирование
        self.scale(factor, factor)
        self.current_scale = new_scale

        # Обновляем статусбар с текущим масштабом
        if self.parent:
            scale_percentage = self.current_scale * 100
            self.parent.statusBar().showMessage(
                f"Масштаб: {scale_percentage:.0f}%",
                self.parent.time_status
            )

    def mousePressEvent(self, event):
        """Обработка нажатия кнопки мыши"""
        if event.button() == Qt.LeftButton:
            if self.scale_mode:
                pos = self.mapToScene(event.pos())
                if len(self.scale_points) < 2:
                    self.scale_points.append(pos)
                    if len(self.scale_points) == 2:
                        if self.temp_line:
                            self.scene().removeItem(self.temp_line)
                            self.temp_line = None
                        if self.scale_line:
                            self.scene().removeItem(self.scale_line)
                        line = QLineF(self.scale_points[0], self.scale_points[1])
                        self.scale_line = QGraphicsLineItem(line)
                        pixels_length = line.length()
                        real_distance, ok = QInputDialog.getDouble(
                            self,
                            "Введите расстояние",
                            "Укажите реальное расстояние в метрах:",
                            1.0, 0.1, 10000.0, 2
                        )
                        if ok:
                            scale = real_distance / pixels_length
                            self.parent.statusBar().showMessage(
                                f"Масштаб: 1 пиксель = {scale:.3f} метров"
                            )
                            self.parent.scale_for_plan = scale
                        self.scale_mode = False
                        self.setCursor(Qt.ArrowCursor)
                        self.scale_points.clear()
            else:
                # Включаем режим перетаскивания
                self.panning = True
                self.last_mouse_pos = event.pos()
                self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Обработка отпускания кнопки мыши"""
        if event.button() == Qt.LeftButton and self.panning:
            self.panning = False
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        """Обработка движения мыши"""
        if self.scale_mode and len(self.scale_points) == 1:
            current_pos = self.mapToScene(event.pos())
            if self.temp_line:
                self.scene().removeItem(self.temp_line)
            line = QLineF(self.scale_points[0], current_pos)
            self.temp_line = QGraphicsLineItem(line)
            pen = QPen(QColor('blue'))
            pen.setStyle(Qt.DashLine)
            pen.setWidth(5)
            self.temp_line.setPen(pen)
            self.scene().addItem(self.temp_line)
            length_pixels = line.length()
            self.parent.statusBar().showMessage(f"Длина: {length_pixels:.1f} пикселей")
        elif self.panning and self.last_mouse_pos is not None:
            # Вычисляем разницу в координатах
            delta = event.pos() - self.last_mouse_pos
            self.last_mouse_pos = event.pos()

            # Прокручиваем область просмотра
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())

        super().mouseMoveEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Моё приложение")
        self.setMinimumSize(800, 600)

        # Dictionary to store object items
        self.object_items = {}  # {object_id: ObjectItem}

        # Мастаб
        self.scale_mode = False
        self.scale_points = []
        self.scale_line = None
        self.scale_for_plan = None
        self.temp_line = None
        # Обязательно включаем отслеживание мыши для главного окна
        self.setMouseTracking(True)

        # Создаем статус бар
        self.statusBar()
        self.time_status = 10000

        # Создаем меню
        self.create_menu()

        # Создаем центральный виджет и слой
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Создаем разделитель для view и таблицы
        splitter = QSplitter(Qt.Vertical)

        # Задаем минимальные размеры для компонентов
        view_container = QWidget()
        view_layout = QVBoxLayout(view_container)
        view_layout.setContentsMargins(0, 0, 0, 0)

        # Создаем QGraphicsView и QGraphicsScene
        self.scene = QGraphicsScene()
        self.view = ScaleGraphicsView(self.scene, self)
        view_layout.addWidget(self.view)

        # Создаем контейнер для таблицы
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)

        # Создаем таблицу объектов
        self.object_table = ObjectTableWidget()
        self.object_table.itemSelectionChanged.connect(self.highlight_selected_object)
        table_layout.addWidget(self.object_table)

        # Добавляем виджеты в сплиттер
        splitter.addWidget(view_container)
        splitter.addWidget(table_container)

        # Устанавливаем начальные размеры сплиттера (70% для плана, 30% для таблицы)
        splitter.setSizes([700, 300])

        # Устанавливаем минимальные размеры для компонентов
        view_container.setMinimumHeight(400)  # Минимальная высота для плана
        table_container.setMinimumHeight(200)  # Минимальная высота для таблицы

        # Добавляем разделитель на слой
        layout.addWidget(splitter)

        # Настраиваем QGraphicsView
        self.view.setRenderHints(QPainter.RenderHint.Antialiasing |
                                 QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        # Инициализируем обработчик базы данных
        self.db_handler = DatabaseHandler(self)

    def _create_database(self):
        """Обработчик создания новой базы данных"""
        if self.db_handler.create_database():
            self.statusBar().showMessage("База данных успешно создана", self.time_status)
        else:
            self.statusBar().showMessage("Ошибка при создании базы данных", self.time_status)

    def _connect_database(self):
        """Обработчик подключения к существующей базе данных"""
        if self.db_handler.connect_to_database():
            self.statusBar().showMessage("Подключение к базе данных выполнено успешно", self.time_status)
        else:
            self.statusBar().showMessage("Ошибка при подключении к базе данных", self.time_status)

    def create_menu(self):
        # Создаем строку меню
        menubar = self.menuBar()

        # Меню "Файл"
        file_menu = menubar.addMenu("Файл")
        database_menu = QMenu("База данных", self)
        file_menu.addMenu(database_menu)

        # Подменю "База данных"
        create_action = QAction("Создать", self)
        create_action.setObjectName("create_action")
        connect_action = QAction("Подключиться", self)
        connect_action.setObjectName("connect_action")
        database_menu.addAction(create_action)
        database_menu.addAction(connect_action)

        # Привязываем действия для работы с базой данных
        create_action.triggered.connect(self._create_database)
        connect_action.triggered.connect(self._connect_database)

        # Меню "План"
        plan_menu = menubar.addMenu("План")
        gen_plan_menu = QMenu("Ген.план", self)
        plan_menu.addMenu(gen_plan_menu)
        # Добавляем действие для измерения масштаба в меню
        scale_action = QAction("Измерить масштаб", self)
        scale_action.triggered.connect(self.toggle_scale_mode)
        plan_menu.addAction(scale_action)

        # Подменю "Ген.план"
        add_action = QAction("Добавить", self)
        select_action = QAction("Выбрать", self)  # Добавляем новое действие
        replace_action = QAction("Заменить", self)
        save_action = QAction("Сохранить", self)
        clear_action = QAction("Очистить", self)
        delete_action = QAction("Удалить план с объектами", self)

        gen_plan_menu.addAction(add_action)
        gen_plan_menu.addAction(select_action)  # Добавляем в меню
        gen_plan_menu.addAction(replace_action)
        gen_plan_menu.addAction(save_action)
        gen_plan_menu.addAction(clear_action)
        gen_plan_menu.addAction(delete_action)

        # Привязываем действие к кнопке "Добавить"
        add_action.triggered.connect(self.add_plan)
        # Привязываем действия к кнопке "Выбрать"
        add_action.triggered.connect(self.add_plan)
        select_action.triggered.connect(self.select_plan)  # Привязываем обработчик


        # Меню "Рисовать"
        draw_menu = menubar.addMenu("Рисовать")
        draw_submenu = QMenu("Рисовать", self)
        draw_menu.addMenu(draw_submenu)

        # Подменю "Рисовать"
        all_objects_action = QAction("Все объекты", self)
        one_object_action = QAction("Один объект", self)
        risk_action = QAction("Риск", self)

        draw_submenu.addAction(all_objects_action)
        draw_submenu.addAction(one_object_action)
        draw_submenu.addAction(risk_action)

        # В подменю "База данных" добавляем действие для VACUUM
        vacuum_action = QAction("Оптимизировать (VACUUM)", self)
        vacuum_action.setObjectName("vacuum_action")
        database_menu.addAction(vacuum_action)
        vacuum_action.triggered.connect(self._vacuum_database)


    def select_plan(self):
        """Открывает диалог выбора плана из базы данных"""
        if not self.db_handler.current_db_path:
            self.statusBar().showMessage("Сначала подключитесь к базе данных", 3000)
            return

        dialog = SelectPlanDialog(self.db_handler.current_db_path, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            plan_id = dialog.get_selected_plan_id()
            if plan_id:
                self.load_plan(plan_id)

    def load_plan(self, plan_id):
        """Загружает выбранный план из базы данных"""
        try:
            with DatabaseManager(self.db_handler.current_db_path) as db:
                # Получаем данные изображения
                image_data = db.images.get_image_data(plan_id)
                if image_data:
                    # Загружаем изображение на сцену
                    pixmap = QPixmap()
                    pixmap.loadFromData(image_data)

                    # Очищаем сцену и добавляем новое изображение
                    self.scene.clear()
                    self.scene.addPixmap(pixmap)

                    # Масштабируем вид
                    self.view.fitInView(
                        self.scene.sceneRect(),
                        Qt.AspectRatioMode.KeepAspectRatio
                    )

                    # Загружаем объекты в таблицу
                    self.load_objects_from_image(plan_id)

                    self.statusBar().showMessage("План успешно загружен", 3000)
                else:
                    self.statusBar().showMessage("План не найден", 3000)

        except Exception as e:
            self.statusBar().showMessage(f"Ошибка при загрузке плана: {str(e)}", 3000)


    def _vacuum_database(self):
        """Обработчик оптимизации базы данных"""
        if self.db_handler.vacuum_database():
            self.statusBar().showMessage(
                "База данных успешно оптимизирована",
                self.time_status
            )
        else:
            self.statusBar().showMessage(
                "Ошибка при оптимизации базы данных",
                self.time_status
            )

    def toggle_scale_mode(self):
        """Включает/выключает режим измерения масштаба"""
        if self.is_scene_empty():
            self.statusBar().showMessage("План не определен. Подключитесь к базе данных. Выберете план.")
            return
        self.view.scale_mode = not self.view.scale_mode
        if self.view.scale_mode:
            self.view.setCursor(Qt.CrossCursor)
            self.statusBar().showMessage("Выберите две точки для измерения масштаба")
        else:
            self.view.setCursor(Qt.ArrowCursor)
            if self.view.scale_line:
                self.scene.removeItem(self.view.scale_line)
                self.view.scale_line = None
            if self.view.temp_line:
                self.scene.removeItem(self.view.temp_line)
                self.view.temp_line = None
            self.view.scale_points.clear()

    def is_scene_empty(self):
        # Проверяем наличие элементов на сцене
        if not self.scene.items():
            return True
        # Проверяем наличие изображений среди элементов
        pixmap_items = [item for item in self.scene.items() if isinstance(item, QGraphicsPixmapItem)]
        return len(pixmap_items) == 0

    def add_plan(self):
        """Функция добавления плана в базу данных и отображения на сцене"""
        # Открываем диалог выбора файла
        plan_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбрать план",
            "",
            "Изображения (*.jpg *.jpeg)"
        )

        if plan_path:
            try:
                # Читаем файл в бинарном режиме
                with open(plan_path, 'rb') as file:
                    image_data = file.read()

                # Получаем имя файла без пути
                plan_name = os.path.basename(plan_path)

                # Сохраняем в базу данных
                image_id = self.db_handler.save_plan(plan_name, image_data, plan_path)

                if image_id:
                    print('image_id',image_id)
                    # Загружаем изображение на сцену
                    pixmap = QPixmap()
                    pixmap.loadFromData(image_data)

                    # Очищаем сцену и добавляем новое изображение
                    self.scene.clear()
                    self.scene.addPixmap(pixmap)

                    # Масштабируем вид, чтобы изображение поместилось
                    self.view.fitInView(
                        self.scene.sceneRect(),
                        Qt.AspectRatioMode.KeepAspectRatio
                    )

                    self.statusBar().showMessage(
                        f"План '{plan_name}' успешно добавлен",
                        3000
                    )
                    if image_id:
                        # После успешной загрузки изображения
                        self.load_objects_from_image(image_id)  # Загружаем объекты в таблицу
            except Exception as e:
                self.statusBar().showMessage(
                    f"Ошибка при добавлении плана: {str(e)}",
                    3000
                )


    def load_image(self, image_path):
        """Метод для загрузки изображения"""
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.scene.clear()
            self.scene.addPixmap(pixmap)
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        """Обработчик изменения размера окна"""
        super().resizeEvent(event)
        if not self.scene.items():
            return
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def load_objects_from_image(self, image_id):
        """Загружает объекты изображения в таблицу и создает их графические представления"""
        try:
            with DatabaseManager(self.db_handler.current_db_path) as db:
                objects = db.objects.get_by_image_id(image_id)

                # Очищаем существующие объекты
                self.object_table.clear_table()

                # Удаляем старые графические элементы со сцены
                for item in self.object_items.values():
                    for graphics_item in item.items:
                        self.scene.removeItem(graphics_item)
                self.object_items.clear()

                # Создаем и сохраняем объекты
                for obj in objects:
                    # Добавляем в таблицу
                    self.object_table.add_object(obj)

                    # Создаем графический элемент (скрытый по умолчанию)
                    object_item = create_object_item(obj, self.scene)
                    self.object_items[obj.id] = object_item

        except Exception as e:
            self.statusBar().showMessage(f"Ошибка при загрузке объектов: {str(e)}", 3000)

    def highlight_selected_object(self):
        """Подсвечивает выбранный объект на плане"""
        # Скрываем все объекты
        for item in self.object_items.values():
            item.set_visible(False)
            item.highlight(False)

        # Получаем ID выбранного объекта
        selected_id = self.object_table.get_selected_object_id()
        if selected_id is not None and selected_id in self.object_items:
            # Показываем и подсвечиваем только выбранный объект
            self.object_items[selected_id].set_visible(True)
            self.object_items[selected_id].highlight(True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
