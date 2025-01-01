# main.py
import mimetypes
import sys
import os
from pathlib import Path

from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import QRectF

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QMenuBar, QMenu, QGraphicsView, QGraphicsScene,
    QFileDialog, QGraphicsLineItem, QInputDialog,
    QGraphicsPixmapItem, QDialog, QSplitter,
    QMessageBox, QHeaderView
)
from PySide6.QtGui import QAction, QPixmap, QPainter, QPen, QColor
from PySide6.QtCore import Qt, QPointF, QLineF, QEvent

from database_handler import DatabaseHandler
from edit_coordinates_manager import EditCoordinatesManager
from plan_dialog import SelectPlanDialog
from object_table import ObjectTableWidget
from object_items import create_object_item
from object_manager import ObjectManager
from temp_drawing import TempDrawingManager
from iris_db.models import ObjectType
from iris_db.database import DatabaseManager


class ScaleGraphicsView(QGraphicsView):
    """Класс представления с поддержкой масштабирования и рисования"""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.scale_mode = False
        self.scale_points = []
        self.scale_line = None
        self.temp_line = None
        self.parent = parent

        # Включаем отслеживание мыши
        self.setMouseTracking(True)
        self.drawing_mode = False

        # Параметры масштабирования
        self.zoom_factor = 1.15
        self.min_scale = 0.1
        self.max_scale = 10.0
        self.current_scale = 1.0

        # Параметры перетаскивания
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.last_mouse_pos = None
        self.panning = False

        # Включаем преобразования видового окна
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # Включаем сглаживание
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )

    def wheelEvent(self, event):
        """Обработка прокрутки колеса мыши для масштабирования"""
        if event.angleDelta().y() > 0:
            zoom_in = True
            factor = self.zoom_factor
        else:
            zoom_in = False
            factor = 1.0 / self.zoom_factor

        new_scale = self.current_scale * factor
        if new_scale < self.min_scale or new_scale > self.max_scale:
            return

        self.scale(factor, factor)
        self.current_scale = new_scale

        if self.parent:
            scale_percentage = self.current_scale * 100
            self.parent.statusBar().showMessage(
                f"Масштаб: {scale_percentage:.0f}%",
                self.parent.time_status
            )

    def mousePressEvent(self, event):
        """Обработка нажатия кнопки мыши"""
        if self.parent.edit_coordinates_manager.is_editing:
            scene_pos = self.mapToScene(event.pos())
            if event.type() == QEvent.MouseButtonDblClick:
                self.parent.edit_coordinates_manager.handle_mouse_click(scene_pos, double_click=True)
            else:
                self.parent.edit_coordinates_manager.handle_mouse_click(scene_pos)
            return

        if self.parent.object_manager.is_drawing:
            scene_pos = self.mapToScene(event.pos())
            if event.type() == QEvent.MouseButtonDblClick:
                self.parent.object_manager.handle_mouse_click(scene_pos, double_click=True)
            else:
                self.parent.object_manager.handle_mouse_click(scene_pos)
            return

        if event.button() == Qt.LeftButton:
            if self.scale_mode:
                self._handle_scale_mode_click(event)
            else:
                self._handle_pan_mode_click(event)

        super().mousePressEvent(event)

    def _handle_scale_mode_click(self, event):
        """Обработка клика в режиме масштабирования"""
        pos = self.mapToScene(event.pos())
        if len(self.scale_points) < 2:
            self.scale_points.append(pos)
            if len(self.scale_points) == 2:
                self._finish_scale_measurement()

    def _handle_pan_mode_click(self, event):
        """Обработка клика в режиме перемещения"""
        self.panning = True
        self.last_mouse_pos = event.pos()
        self.setCursor(Qt.ClosedHandCursor)

    def _finish_scale_measurement(self):
        """Завершение измерения масштаба"""
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

    def mouseReleaseEvent(self, event):
        """Обработка отпускания кнопки мыши"""
        if event.button() == Qt.LeftButton and self.panning:
            self.panning = False
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        """Обработка движения мыши"""
        if self.parent.edit_coordinates_manager.is_editing:
            scene_pos = self.mapToScene(event.pos())
            self.parent.edit_coordinates_manager.handle_mouse_move(scene_pos)
        elif self.parent.object_manager.is_drawing:
            scene_pos = self.mapToScene(event.pos())
            self.parent.object_manager.handle_mouse_move(scene_pos)
        elif self.scale_mode and len(self.scale_points) == 1:
            self._handle_scale_mode_move(event)
        elif self.panning and self.last_mouse_pos is not None:
            self._handle_pan_mode_move(event)

        super().mouseMoveEvent(event)

    def _handle_scale_mode_move(self, event):
        """Обработка движения мыши в режиме масштабирования"""
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
        self.parent.statusBar().showMessage(
            f"Длина: {length_pixels:.1f} пикселей"
        )

    def _handle_pan_mode_move(self, event):
        """Обработка движения мыши в режиме перемещения"""
        delta = event.pos() - self.last_mouse_pos
        self.last_mouse_pos = event.pos()

        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - delta.x())
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - delta.y())

    def mouseDoubleClickEvent(self, event):
        """Обработка двойного клика мыши"""
        if self.parent.edit_coordinates_manager.is_editing:
            scene_pos = self.mapToScene(event.pos())
            self.parent.edit_coordinates_manager.handle_mouse_click(scene_pos, double_click=True)
            return

        if self.parent.object_manager.is_drawing:
            scene_pos = self.mapToScene(event.pos())
            self.parent.object_manager.handle_mouse_click(scene_pos, double_click=True)
            return

        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    """Главное окно приложения"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Моё приложение")
        self.setMinimumSize(800, 600)

        # Инициализация базовых атрибутов
        self.current_image_id = None
        self.scale_mode = False
        self.scale_points = []
        self.scale_line = None
        self.scale_for_plan = None
        self.temp_line = None
        self.time_status = 10000
        self.object_items = {}

        # Создание основных компонентов интерфейса
        self._create_central_widget()
        self._setup_graphics_view()
        self._setup_object_table()

        # Теперь, когда view создан, инициализируем менеджеры
        self.edit_coordinates_manager = EditCoordinatesManager(self)
        self.object_manager = ObjectManager(self)
        self.db_handler = DatabaseHandler(self)

        # Создание меню
        self.create_menu()

    def _create_central_widget(self):
        """Создание центрального виджета и компоновка элементов"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Создание разделителя для view и таблицы
        self.splitter = QSplitter(Qt.Vertical)

        # Создание контейнеров для view и таблицы
        self.view_container = QWidget()
        self.view_layout = QVBoxLayout(self.view_container)
        self.view_layout.setContentsMargins(0, 0, 0, 0)

        self.table_container = QWidget()
        self.table_layout = QVBoxLayout(self.table_container)
        self.table_layout.setContentsMargins(0, 0, 0, 0)

        # Добавление контейнеров в разделитель
        self.splitter.addWidget(self.view_container)
        self.splitter.addWidget(self.table_container)

        # Установка начальных размеров (70% для плана, 30% для таблицы)
        self.splitter.setSizes([700, 300])

        # Установка минимальных размеров
        self.view_container.setMinimumHeight(400)
        self.table_container.setMinimumHeight(200)

        # Добавление разделителя в главный layout
        layout.addWidget(self.splitter)

    def _setup_graphics_view(self):
        """Настройка графической сцены и представления"""
        self.scene = QGraphicsScene()
        self.view = ScaleGraphicsView(self.scene, self)

        # Настройка параметров отображения
        self.view.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        # Добавление view в контейнер
        self.view_layout.addWidget(self.view)

    def _setup_object_table(self):
        """Настройка таблицы объектов"""
        self.object_table = ObjectTableWidget(self)  # self передается как parent
        self.object_table.itemSelectionChanged.connect(self.highlight_selected_object)
        self.table_layout.addWidget(self.object_table)

    def resizeEvent(self, event):
        """Обработчик изменения размера окна"""
        super().resizeEvent(event)
        if not self.scene.items():
            return
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def create_menu(self):
        """Создание главного меню приложения"""
        menubar = self.menuBar()

        # Меню "Файл"
        file_menu = menubar.addMenu("Файл")
        self._create_database_menu(file_menu)

        # Меню "План"
        plan_menu = menubar.addMenu("План")
        self._create_plan_menu(plan_menu)

        # Меню "Рисовать"
        draw_menu = menubar.addMenu("Рисовать")
        self._create_draw_menu(draw_menu)

    def _create_database_menu(self, file_menu):
        """Создание подменю для работы с базой данных"""
        database_menu = QMenu("База данных", self)
        file_menu.addMenu(database_menu)

        # Создание действий для работы с базой данных
        create_action = QAction("Создать", self)
        connect_action = QAction("Подключиться", self)
        vacuum_action = QAction("Оптимизировать (VACUUM)", self)

        # Установка идентификаторов
        create_action.setObjectName("create_action")
        connect_action.setObjectName("connect_action")
        vacuum_action.setObjectName("vacuum_action")

        # Добавление действий в меню
        database_menu.addAction(create_action)
        database_menu.addAction(connect_action)
        database_menu.addAction(vacuum_action)

        # Привязка обработчиков
        create_action.triggered.connect(self._create_database)
        connect_action.triggered.connect(self._connect_database)
        vacuum_action.triggered.connect(self._vacuum_database)

    def _create_plan_menu(self, plan_menu):
        """Создание подменю для работы с планом"""
        gen_plan_menu = QMenu("Ген.план", self)
        plan_menu.addMenu(gen_plan_menu)

        # Добавление действия для измерения масштаба
        scale_action = QAction("Измерить масштаб", self)
        scale_action.triggered.connect(self.toggle_scale_mode)
        plan_menu.addAction(scale_action)

        # Создание действий для работы с планом
        actions = {
            "add": ("Добавить", self.add_plan),
            "select": ("Выбрать", self.select_plan),
            "replace": ("Заменить", self.replace_plan),
            "clear": ("Очистить", self.clear_plan),  # Добавляем новое действие
            "save": ("Сохранить", self.save_plan),
            "delete": ("Удалить план с объектами", self.delete_plan)
        }

        # Добавление действий в меню
        for action_id, (title, handler) in actions.items():
            action = QAction(title, self)
            if handler:
                action.triggered.connect(handler)
            gen_plan_menu.addAction(action)

    def _create_draw_menu(self, draw_menu):
        """Создание подменю для рисования"""
        draw_submenu = QMenu("Рисовать", self)
        draw_menu.addMenu(draw_submenu)

        # Создание действий для рисования
        draw_actions = {
            "all": "Все объекты",
            "one": "Один объект",
            "risk": "Риск"
        }

        # Добавляем обработчик для "Один объект"
        one_object_action = QAction(draw_actions["one"], self)
        one_object_action.triggered.connect(self.draw_single_object_zones)
        draw_submenu.addAction(one_object_action)

        # Добавляем обработчик для "Все объекты"
        all_objects_action = QAction(draw_actions["all"], self)
        all_objects_action.triggered.connect(self.draw_all_objects_zones)
        draw_submenu.addAction(all_objects_action)

        # Добавляем остальные пункты меню
        for action_id, title in draw_actions.items():
            if action_id not in ["one", "all"]:  # Пропускаем уже добавленные действия
                action = QAction(title, self)
                draw_submenu.addAction(action)

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

    def save_plan(self):
        """
        Сохраняет текущее содержимое сцены в файл JPG
        """
        if self.is_scene_empty():
            self.statusBar().showMessage(
                "Нет плана для сохранения",
                3000
            )
            return False

        try:
            # Открываем диалог выбора файла для сохранения
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Сохранить план",
                "",
                "Изображения (*.jpg)"
            )

            if not file_path:
                return False

            # Добавляем расширение .jpg если его нет
            if not file_path.lower().endswith('.jpg'):
                file_path += '.jpg'

            # Создаем изображение из содержимого сцены
            scene_rect = self.scene.sceneRect()
            image = QImage(
                int(scene_rect.width()),
                int(scene_rect.height()),
                QImage.Format_RGB32
            )
            image.fill(Qt.white)  # Заполняем белым фоном

            # Создаем painter для рисования на изображении
            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing)

            # Рендерим содержимое сцены
            self.scene.render(
                painter,
                QRectF(image.rect()),
                self.scene.sceneRect()
            )
            painter.end()

            # Сохраняем изображение
            if image.save(file_path, 'JPG', 100):  # Качество 100%
                self.statusBar().showMessage(
                    f"План успешно сохранен в {file_path}",
                    3000
                )
                return True
            else:
                raise Exception("Не удалось сохранить файл")

        except Exception as e:
            self.statusBar().showMessage(
                f"Ошибка при сохранении плана: {str(e)}",
                3000
            )
            print(f"Подробности ошибки сохранения: {e}")
            return False

    def clear_plan(self):
        """
        Очищает сцену и перезагружает план из базы данных.
        Сохраняет объекты и масштаб.
        """
        if not self.db_handler.current_db_path:
            self.statusBar().showMessage("Сначала подключитесь к базе данных", 3000)
            return False

        if not self.current_image_id:
            self.statusBar().showMessage("План не выбран", 3000)
            return False

        try:
            # Получаем данные изображения из базы
            with DatabaseManager(self.db_handler.current_db_path) as db:
                image_data = db.images.get_image_data(self.current_image_id)
                if not image_data:
                    raise ValueError("План не найден в базе данных")

                # Очищаем сцену
                self.scene.clear()

                # Загружаем изображение
                pixmap = QPixmap()
                if not pixmap.loadFromData(image_data):
                    raise ValueError("Не удалось загрузить изображение")

                # Добавляем изображение на сцену
                self.scene.addPixmap(pixmap)

                # Восстанавливаем масштаб отображения
                self.view.fitInView(
                    self.scene.sceneRect(),
                    Qt.AspectRatioMode.KeepAspectRatio
                )

                # Перезагружаем объекты
                self.load_objects_from_image(self.current_image_id)

                self.statusBar().showMessage("План успешно очищен", 3000)
                return True

        except Exception as e:
            self.statusBar().showMessage(
                f"Ошибка при очистке плана: {str(e)}",
                3000
            )
            print(f"Подробности ошибки: {e}")
            return False

    def replace_plan(self):
        """
        Заменяет изображение текущего плана, сохраняя существующие объекты.

        Returns:
            bool: True если замена прошла успешно, False в случае ошибки
        """
        if not self.db_handler.current_db_path:
            self.statusBar().showMessage("Сначала подключитесь к базе данных", 3000)
            return False

        if not self.current_image_id:
            self.statusBar().showMessage("Сначала выберите план для замены", 3000)
            return False

        try:
            # Проверяем существование текущего плана в базе
            with DatabaseManager(self.db_handler.current_db_path) as db:
                current_image = db.images.get_by_id(self.current_image_id)
                if not current_image:
                    self.statusBar().showMessage("Текущий план не найден в базе данных", 3000)
                    return False

            # Открываем диалог выбора файла
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Выбрать новый план",
                "",
                "Изображения (*.jpg *.jpeg *.png)"
            )

            if not file_path:
                return False

            # Загружаем новое изображение
            with open(file_path, 'rb') as file:
                new_image_data = file.read()

            # Проверяем, что это действительно изображение
            pixmap = QPixmap()
            if not pixmap.loadFromData(new_image_data):
                self.statusBar().showMessage("Выбранный файл не является изображением", 3000)
                return False

            # Обновляем данные в базе
            with DatabaseManager(self.db_handler.current_db_path) as db:
                # Обновляем данные изображения
                current_image.image_data = new_image_data
                current_image.file_name = Path(file_path).name
                current_image.file_size = len(new_image_data)
                current_image.mime_type, _ = mimetypes.guess_type(file_path)

                # Сохраняем изменения
                db.images.update(current_image)

            # Обновляем отображение на сцене
            self.scene.clear()
            pixmap_item = self.scene.addPixmap(pixmap)
            self.view.fitInView(
                self.scene.sceneRect(),
                Qt.AspectRatioMode.KeepAspectRatio
            )

            # Перезагружаем объекты
            self.load_objects_from_image(self.current_image_id)

            self.statusBar().showMessage(
                f"План успешно заменен на {Path(file_path).name}",
                3000
            )
            return True

        except Exception as e:
            error_msg = f"Ошибка при замене плана: {str(e)}"
            self.statusBar().showMessage(error_msg, 3000)
            print(f"Подробности ошибки: {e}")
            return False

    def delete_plan(self):
        """
        Удаляет текущий план и все связанные с ним объекты из базы данных.
        Очищает графическую сцену и сбрасывает текущее состояние.
        """
        if not self.db_handler.current_db_path:
            self.statusBar().showMessage("Сначала подключитесь к базе данных", 3000)
            return False

        if not self.current_image_id:
            self.statusBar().showMessage("План для удаления не выбран", 3000)
            return False

        # Запрашиваем подтверждение удаления
        confirmation = QMessageBox.question(
            self,
            "Подтверждение удаления",
            "Вы действительно хотите удалить текущий план?\n"
            "Все объекты на плане также будут удалены.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if confirmation == QMessageBox.No:
            return False

        try:
            with DatabaseManager(self.db_handler.current_db_path) as db:
                # Удаляем план из базы данных
                # (связанные объекты удалятся автоматически благодаря ON DELETE CASCADE)
                db.images.delete(self.current_image_id)

            # Очищаем графическую сцену
            self.scene.clear()

            # Очищаем таблицу объектов
            self.object_table.clear_table()

            # Очищаем словарь графических элементов
            for item in self.object_items.values():
                if item:
                    item.cleanup()
            self.object_items.clear()

            # Сбрасываем текущий ID плана
            self.current_image_id = None

            # Сбрасываем масштаб
            self.scale_for_plan = None

            self.statusBar().showMessage("План и связанные объекты успешно удалены", 3000)
            return True

        except Exception as e:
            error_msg = f"Ошибка при удалении плана: {str(e)}"
            self.statusBar().showMessage(error_msg, 3000)
            print(f"Подробности ошибки: {e}")
            return False

    def draw_all_objects_zones(self):
        """Обработчик для пункта меню 'Рисовать' -> 'Все объекты'"""
        from all_impact_zones import draw_all_impact_zones
        draw_all_impact_zones(self)

    def draw_single_object_zones(self):
        """Обработчик для пункта меню 'Рисовать' -> 'Один объект'"""
        # Получаем тип выбранного объекта
        selected_id = self.object_table.get_selected_object_id()
        if not selected_id:
            self.statusBar().showMessage("Выберите объект в таблице", 3000)
            return

        try:
            with DatabaseManager(self.db_handler.current_db_path) as db:
                obj = db.objects.get_by_id(selected_id)
                if not obj:
                    raise ValueError("Объект не найден в базе данных")

                if obj.object_type == ObjectType.POINT:
                    from impact_zones import draw_impact_zones
                    draw_impact_zones(self)
                elif obj.object_type == ObjectType.LINEAR:
                    from linear_impact_zones import draw_linear_impact_zones
                    draw_linear_impact_zones(self)
                elif obj.object_type == ObjectType.STATIONARY:
                    from stationary_impact_zones import draw_stationary_impact_zones
                    draw_stationary_impact_zones(self)
                else:
                    self.statusBar().showMessage(
                        "Отрисовка зон не поддерживается для данного типа объекта",
                        3000
                    )

        except Exception as e:
            self.statusBar().showMessage(
                f"Ошибка при отрисовке зон: {str(e)}",
                3000
            )

    def toggle_scale_mode(self):
        """Включает/выключает режим измерения масштаба"""
        if self.is_scene_empty():
            self.statusBar().showMessage(
                "План не определен. Подключитесь к базе данных. Выберете план."
            )
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

    def start_edit_coordinates(self, object_id: int):
        """Начинает процесс редактирования координат объекта"""
        if not self.is_plan_loaded():
            QMessageBox.warning(self, "Предупреждение",
                                "Сначала выберите план")
            return
        self.edit_coordinates_manager.start_editing_coordinates(object_id)

    def is_scene_empty(self):
        """Проверяет наличие плана на сцене"""
        if not self.scene.items():
            return True
        pixmap_items = [item for item in self.scene.items() if isinstance(item, QGraphicsPixmapItem)]
        return len(pixmap_items) == 0

    def add_plan(self):
        """Добавление нового плана в базу данных"""
        plan_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбрать план",
            "",
            "Изображения (*.jpg *.jpeg)"
        )

        if plan_path:
            try:
                with open(plan_path, 'rb') as file:
                    image_data = file.read()

                plan_name = os.path.basename(plan_path)
                image_id = self.db_handler.save_plan(plan_name, image_data, plan_path)

                if image_id:
                    pixmap = QPixmap()
                    pixmap.loadFromData(image_data)

                    self.scene.clear()
                    self.scene.addPixmap(pixmap)
                    self.view.fitInView(
                        self.scene.sceneRect(),
                        Qt.AspectRatioMode.KeepAspectRatio
                    )

                    self.statusBar().showMessage(
                        f"План '{plan_name}' успешно добавлен",
                        3000
                    )

                    if image_id:
                        self.load_objects_from_image(image_id)

            except Exception as e:
                self.statusBar().showMessage(
                    f"Ошибка при добавлении плана: {str(e)}",
                    3000
                )

    def select_plan(self):
        """Выбор существующего плана из базы данных"""
        if not self.db_handler.current_db_path:
            self.statusBar().showMessage("Сначала подключитесь к базе данных", 3000)
            return

        dialog = SelectPlanDialog(self.db_handler.current_db_path, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            plan_id = dialog.get_selected_plan_id()
            if plan_id:
                self.load_plan(plan_id)

    def load_plan(self, plan_id):
        """Загрузка плана из базы данных"""
        try:
            with DatabaseManager(self.db_handler.current_db_path) as db:
                image_data = db.images.get_image_data(plan_id)
                if image_data:
                    self.current_image_id = plan_id

                    pixmap = QPixmap()
                    pixmap.loadFromData(image_data)

                    self.scene.clear()
                    self.scene.addPixmap(pixmap)
                    self.view.fitInView(
                        self.scene.sceneRect(),
                        Qt.AspectRatioMode.KeepAspectRatio
                    )

                    self.load_objects_from_image(plan_id)
                    self.statusBar().showMessage("План успешно загружен", 3000)
                else:
                    self.statusBar().showMessage("План не найден", 3000)
        except Exception as e:
            self.statusBar().showMessage(f"Ошибка при загрузке плана: {str(e)}", 3000)
            print(f"Подробности ошибки: {e}")

    def load_objects_from_image(self, image_id):
        """Загрузка объектов изображения в таблицу и создание их графических представлений"""
        try:
            self.object_table.clear_table()

            # Очищаем старые графические элементы
            for item in self.object_items.values():
                if item:
                    item.cleanup()
            self.object_items.clear()

            # Загружаем объекты из базы данных
            with DatabaseManager(self.db_handler.current_db_path) as db:
                objects = db.objects.get_by_image_id(image_id)

                # Добавляем объекты в таблицу и создаем их графические представления
                for obj in objects:
                    self.object_table.add_object(obj)

                    object_item = create_object_item(obj, self.scene)
                    if object_item:
                        self.object_items[obj.id] = object_item

        except Exception as e:
            self.statusBar().showMessage(f"Ошибка при загрузке объектов: {str(e)}", 3000)
            print(f"Подробности ошибки загрузки объектов: {e}")


    def highlight_selected_object(self):
        """Подсветка выбранного объекта на плане"""
        try:
            for item in self.object_items.values():
                if item and hasattr(item, 'set_visible'):
                    item.set_visible(False)
                    item.highlight(False)

            selected_id = self.object_table.get_selected_object_id()
            if selected_id is not None and selected_id in self.object_items:
                selected_item = self.object_items[selected_id]
                if selected_item:
                    selected_item.set_visible(True)
                    selected_item.highlight(True)
        except Exception as e:
            self.statusBar().showMessage(f"Ошибка при подсветке объекта: {str(e)}", 3000)
            print(f"Подробности ошибки подсветки: {e}")

    def is_plan_loaded(self) -> bool:
        """Проверка загрузки плана"""
        if not self.current_image_id:
            return False
        return any(isinstance(item, QGraphicsPixmapItem) for item in self.scene.items())

    def start_drawing_object(self, object_type: ObjectType):
        """Начало процесса рисования нового объекта"""
        if not self.is_plan_loaded():
            QMessageBox.warning(self, "Предупреждение",
                                "Сначала выберите план")
            return
        self.object_manager.start_drawing_object(object_type)

    def load_image(self, image_path):
        """
        Загрузка изображения из файла

        Args:
            image_path (str): Путь к файлу изображения
        """
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.scene.clear()
            self.scene.addPixmap(pixmap)
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _get_selected_object(self):
        """
        Получение текущего выбранного объекта

        Returns:
            tuple: (id объекта, объект в таблице) или (None, None) если ничего не выбрано
        """
        current_row = self.object_table.currentRow()
        if current_row >= 0:
            id_item = self.object_table.item(current_row, 0)
            if id_item and id_item.text():
                return int(id_item.text()), self.object_table.item(current_row, 1)
        return None, None

    def update_status(self, message: str, timeout: int = 3000):
        """
        Обновление статусной строки

        Args:
            message (str): Текст сообщения
            timeout (int): Время отображения в миллисекундах
        """
        self.statusBar().showMessage(message, timeout)

    def closeEvent(self, event):
        """
        Обработчик закрытия приложения

        Args:
            event: Событие закрытия
        """
        try:
            if self.db_handler:
                self.db_handler.close()
            event.accept()
        except Exception as e:
            print(f"Ошибка при закрытии приложения: {e}")
            event.accept()


def main():
    """Точка входа в приложение"""
    try:
        app = QApplication(sys.argv)

        # Установка стиля приложения
        app.setStyle('Fusion')

        # Создание и отображение главного окна
        window = MainWindow()
        window.show()

        # Запуск главного цикла обработки событий
        sys.exit(app.exec())

    except Exception as e:
        print(f"Критическая ошибка при запуске приложения: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()