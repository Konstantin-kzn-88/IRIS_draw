from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene

from iris_db.database import DatabaseManager
from iris_db.models import Object, ObjectType


ZONE_ORDER = ('R6', 'R5', 'R4', 'R3', 'R2', 'R1')
OBJECT_ORDER = (
    ObjectType.STATIONARY,
    ObjectType.LINEAR,
    ObjectType.POINT,
)
ZONE_COLORS = {
    'R6': QColor(255, 255, 0),
    'R5': QColor(128, 0, 128),
    'R4': QColor(0, 255, 0),
    'R3': QColor(255, 165, 0),
    'R2': QColor(0, 0, 255),
    'R1': QColor(255, 0, 0),
}


class FilledZoneRenderer:
    """Отрисовка зон сплошной цветной заливкой."""

    def __init__(self, scene: QGraphicsScene):
        self.scene = scene

    @staticmethod
    def _object_path(obj: Object) -> QPainterPath:
        path = QPainterPath()
        first_coord = obj.coordinates[0]
        path.moveTo(first_coord.x, first_coord.y)
        for coordinate in obj.coordinates[1:]:
            path.lineTo(coordinate.x, coordinate.y)
        if obj.object_type == ObjectType.STATIONARY:
            path.closeSubpath()
        return path

    def _draw_zone(
        self,
        obj: Object,
        painter: QPainter,
        zone: str,
        scale: float,
    ) -> None:
        radius_px = float(getattr(obj, zone)) / scale
        if radius_px <= 0:
            return

        color = ZONE_COLORS[zone]
        if obj.object_type == ObjectType.POINT:
            center = obj.coordinates[0]
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(
                center.x - radius_px,
                center.y - radius_px,
                radius_px * 2,
                radius_px * 2,
            )
            return

        path = self._object_path(obj)
        pen = QPen(color)
        pen.setWidth(max(1, int(radius_px * 2)))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        if obj.object_type == ObjectType.STATIONARY and zone == 'R1':
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawPath(path)

    def render_objects(
        self,
        objects: list[Object],
        scale: float,
    ) -> QGraphicsPixmapItem:
        if scale <= 0:
            raise ValueError("Масштаб должен быть больше нуля")

        scene_rect = self.scene.sceneRect()
        width = max(1, int(scene_rect.width()))
        height = max(1, int(scene_rect.height()))
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.white)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        for zone in ZONE_ORDER:
            for object_type in OBJECT_ORDER:
                for obj in objects:
                    if obj.object_type == object_type:
                        self._draw_zone(obj, painter, zone, scale)
        painter.end()

        pixmap = QPixmap.fromImage(image)
        pixmap.setMask(pixmap.createMaskFromColor(QColor(255, 255, 255)))
        item = QGraphicsPixmapItem(pixmap)
        item.setOpacity(0.4)
        return item


def _drawing_is_available(main_window) -> bool:
    if not main_window.is_plan_loaded():
        main_window.statusBar().showMessage("Сначала необходимо загрузить план", 3000)
        return False
    if not main_window.scale_for_plan:
        main_window.statusBar().showMessage("Сначала необходимо измерить масштаб", 3000)
        return False
    return True


def draw_filled_single_object_zones(main_window) -> bool:
    """Отрисовывает заливкой зоны выбранного объекта любого типа."""
    if not _drawing_is_available(main_window):
        return False

    selected_id = main_window.object_table.get_selected_object_id()
    if not selected_id:
        main_window.statusBar().showMessage("Выберите объект в таблице", 3000)
        return False

    try:
        with DatabaseManager(main_window.db_handler.current_db_path) as db:
            obj = db.objects.get_by_id(selected_id)
            if not obj:
                raise ValueError("Объект не найден в базе данных")

            renderer = FilledZoneRenderer(main_window.scene)
            main_window.scene.addItem(
                renderer.render_objects([obj], main_window.scale_for_plan)
            )

        main_window.statusBar().showMessage(
            "Зоны выбранного объекта отрисованы заливкой",
            3000,
        )
        return True
    except Exception as error:
        main_window.statusBar().showMessage(
            f"Ошибка при отрисовке зон: {error}",
            3000,
        )
        return False


def draw_filled_all_object_zones(main_window) -> bool:
    """Отрисовывает заливкой зоны всех объектов плана."""
    if not _drawing_is_available(main_window):
        return False

    try:
        with DatabaseManager(main_window.db_handler.current_db_path) as db:
            objects = db.objects.get_by_image_id(main_window.current_image_id)
            if not objects:
                main_window.statusBar().showMessage(
                    "На плане нет объектов для отрисовки",
                    3000,
                )
                return False

            renderer = FilledZoneRenderer(main_window.scene)
            main_window.scene.addItem(
                renderer.render_objects(objects, main_window.scale_for_plan)
            )

        main_window.statusBar().showMessage(
            "Зоны всех объектов отрисованы заливкой",
            3000,
        )
        return True
    except Exception as error:
        main_window.statusBar().showMessage(
            f"Ошибка при отрисовке зон: {error}",
            3000,
        )
        return False
