from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage, QPen, QPainterPath
from PySide6.QtCore import Qt, QPointF
from iris_db.models import Object, ObjectType
from iris_db.database import DatabaseManager


class LinearImpactRenderer:
    """Класс для отрисовки зон поражающих факторов линейных объектов"""

    def __init__(self, scene: QGraphicsScene):
        self.scene = scene
        # Цвета для каждой зоны
        self.zone_colors = {
            'R1': QColor(255, 0, 0, 180),  # Красный
            'R2': QColor(0, 0, 255, 180),  # Синий
            'R3': QColor(255, 165, 0, 180),  # Оранжевый
            'R4': QColor(0, 255, 0, 180),  # Зеленый
            'R5': QColor(128, 0, 128, 180),  # Фиолетовый
            'R6': QColor(255, 255, 0, 180),  # Желтый
        }

    def render_impact_zones(self, obj: Object, scale: float) -> QGraphicsPixmapItem:
        """
        Отрисовывает зоны поражающих факторов для линейного объекта
        """
        if obj.object_type != ObjectType.LINEAR:
            raise ValueError("Этот рендерер поддерживает только линейные объекты")

        # Получаем размеры сцены
        scene_rect = self.scene.sceneRect()
        width = int(scene_rect.width())
        height = int(scene_rect.height())

        # Создаем прозрачное изображение
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.transparent)

        # Создаем художника для рисования
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)

        # Создаем путь из координат объекта
        path = QPainterPath()
        first_coord = obj.coordinates[0]
        path.moveTo(first_coord.x, first_coord.y)

        for coord in obj.coordinates[1:]:
            path.lineTo(coord.x, coord.y)

        # Рисуем линии для каждой зоны (от большей к меньшей)
        zones = ['R6', 'R5', 'R4', 'R3', 'R2', 'R1']
        for zone in zones:
            radius = getattr(obj, zone)  # Получаем радиус из объекта
            # Переводим радиус из метров в пиксели
            width_px = radius / scale

            # Настраиваем перо для рисования
            pen = QPen(self.zone_colors[zone])
            pen.setWidth(int(width_px * 2))  # Ширина линии равна диаметру зоны
            pen.setCapStyle(Qt.RoundCap)  # Закругленные концы
            pen.setJoinStyle(Qt.RoundJoin)  # Закругленные соединения

            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        painter.end()

        # Создаем QPixmap из изображения
        pixmap = QPixmap.fromImage(image)

        # Создаем элемент сцены
        item = QGraphicsPixmapItem(pixmap)
        item.setOpacity(0.6)  # Устанавливаем прозрачность

        return item


def draw_linear_impact_zones(main_window) -> bool:
    """
    Отрисовывает зоны поражающих факторов для выбранного линейного объекта
    """
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

    # Получаем выбранный объект
    selected_id = main_window.object_table.get_selected_object_id()
    if not selected_id:
        main_window.statusBar().showMessage(
            "Выберите объект в таблице",
            3000
        )
        return False

    try:
        # Получаем объект из базы данных
        with DatabaseManager(main_window.db_handler.current_db_path) as db:
            obj = db.objects.get_by_id(selected_id)
            if not obj:
                raise ValueError("Объект не найден в базе данных")

            if obj.object_type != ObjectType.LINEAR:
                raise ValueError("Выбранный объект не является линейным")

            # Создаем рендерер и отрисовываем зоны
            renderer = LinearImpactRenderer(main_window.scene)
            impact_item = renderer.render_impact_zones(obj, main_window.scale_for_plan)

            # Добавляем элемент на сцену
            main_window.scene.addItem(impact_item)

            main_window.statusBar().showMessage(
                "Зоны поражающих факторов отрисованы",
                3000
            )
            return True

    except Exception as e:
        main_window.statusBar().showMessage(
            f"Ошибка при отрисовке зон: {str(e)}",
            3000
        )
        return False