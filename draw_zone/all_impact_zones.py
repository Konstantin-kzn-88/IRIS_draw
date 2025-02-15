from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage, QPen, QPainterPath
from PySide6.QtCore import Qt, QPointF

from iris_db.models import Object, ObjectType
from iris_db.database import DatabaseManager


class AllImpactRenderer:
    """Класс для отрисовки зон поражающих факторов всех объектов на плане"""

    def __init__(self, scene: QGraphicsScene):
        self.scene = scene
        # Цвета для каждой зоны
        self.zone_colors = {
            'R1': QColor(255, 0, 0, 100),  # Красный
            'R2': QColor(0, 0, 255, 100),  # Синий
            'R3': QColor(255, 165, 0, 100),  # Оранжевый
            'R4': QColor(0, 255, 0, 100),  # Зеленый
            'R5': QColor(128, 0, 128, 100),  # Фиолетовый
            'R6': QColor(255, 255, 0, 100),  # Желтый
        }

    def blend_images(self, images: list[QImage]) -> QImage:
        """
        Объединяет несколько изображений с учетом прозрачности
        """
        if not images:
            return None

        result = QImage(images[0].size(), QImage.Format_ARGB32)
        result.fill(Qt.transparent)

        painter = QPainter(result)
        for img in images:
            painter.drawImage(0, 0, img)
        painter.end()

        return result

    def render_point_zone(self, obj: Object, painter: QPainter, zone: str, scale: float):
        """Отрисовка конкретной зоны для точечного объекта"""
        center_x = obj.coordinates[0].x
        center_y = obj.coordinates[0].y
        radius = getattr(obj, zone)
        radius_px = radius / scale

        painter.setBrush(self.zone_colors[zone])
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(
            center_x - radius_px,
            center_y - radius_px,
            radius_px * 2,
            radius_px * 2
        )

    def render_linear_zone(self, obj: Object, painter: QPainter, zone: str, scale: float):
        """Отрисовка конкретной зоны для линейного объекта"""
        path = QPainterPath()
        first_coord = obj.coordinates[0]
        path.moveTo(first_coord.x, first_coord.y)

        for coord in obj.coordinates[1:]:
            path.lineTo(coord.x, coord.y)

        radius = getattr(obj, zone)
        width_px = radius / scale

        pen = QPen(self.zone_colors[zone])
        pen.setWidth(int(width_px * 2))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)

        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    def render_stationary_zone(self, obj: Object, painter: QPainter, zone: str, scale: float):
        """Отрисовка конкретной зоны для стационарного объекта"""
        path = QPainterPath()
        first_coord = obj.coordinates[0]
        path.moveTo(first_coord.x, first_coord.y)

        for coord in obj.coordinates[1:]:
            path.lineTo(coord.x, coord.y)
        path.closeSubpath()

        radius = getattr(obj, zone)
        width_px = radius / scale

        pen = QPen(self.zone_colors[zone])
        pen.setWidth(int(width_px * 2))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)

        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # Для зоны R1 дополнительно заливаем внутреннюю область
        if zone == 'R1':
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 0, 0, 100))
            painter.drawPath(path)

    def render_zone_for_all_objects(self, objects: list[Object], painter: QPainter, zone: str, scale: float):
        """Отрисовка конкретной зоны для всех объектов"""
        # Сначала отрисовываем стационарные объекты
        for obj in objects:
            if obj.object_type == ObjectType.STATIONARY:
                self.render_stationary_zone(obj, painter, zone, scale)

        # Затем линейные объекты
        for obj in objects:
            if obj.object_type == ObjectType.LINEAR:
                self.render_linear_zone(obj, painter, zone, scale)

        # В последнюю очередь точечные объекты
        for obj in objects:
            if obj.object_type == ObjectType.POINT:
                self.render_point_zone(obj, painter, zone, scale)

    def render_impact_zones(self, objects: list[Object], scale: float) -> QGraphicsPixmapItem:
        """
        Отрисовывает зоны поражающих факторов для всех объектов
        """
        scene_rect = self.scene.sceneRect()
        width = int(scene_rect.width())
        height = int(scene_rect.height())

        # Создаем белое изображение
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.white)

        # Создаем художника для рисования
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)

        # Цвета зон без прозрачности
        zone_colors_solid = {
            'R6': QColor(255, 255, 0),  # Желтый
            'R5': QColor(128, 0, 128),  # Фиолетовый
            'R4': QColor(0, 255, 0),  # Зеленый
            'R3': QColor(255, 165, 0),  # Оранжевый
            'R2': QColor(0, 0, 255),  # Синий
            'R1': QColor(255, 0, 0)  # Красный
        }
        self.zone_colors = zone_colors_solid

        # Отрисовываем зоны от большей к меньшей
        for zone in ['R6', 'R5', 'R4', 'R3', 'R2', 'R1']:
            self.render_zone_for_all_objects(objects, painter, zone, scale)

        painter.end()

        # Создаем QPixmap из изображения
        pixmap = QPixmap.fromImage(image)

        # Удаляем белые пиксели одной маской
        mask = pixmap.createMaskFromColor(QColor(255, 255, 255))
        pixmap.setMask(mask)

        # Создаем элемент сцены с прозрачностью
        item = QGraphicsPixmapItem(pixmap)
        item.setOpacity(0.4)

        return item


def draw_all_impact_zones(main_window) -> bool:
    """
    Отрисовывает зоны поражающих факторов для всех объектов на плане

    Args:
        main_window: Главное окно приложения

    Returns:
        bool: True если отрисовка выполнена успешно
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

            # Создаем рендерер и отрисовываем зоны
            renderer = AllImpactRenderer(main_window.scene)
            impact_item = renderer.render_impact_zones(objects, main_window.scale_for_plan)

            # Добавляем элемент на сцену
            main_window.scene.addItem(impact_item)

            main_window.statusBar().showMessage(
                "Зоны поражающих факторов отрисованы для всех объектов",
                3000
            )
            return True

    except Exception as e:
        main_window.statusBar().showMessage(
            f"Ошибка при отрисовке зон: {str(e)}",
            3000
        )
        return False