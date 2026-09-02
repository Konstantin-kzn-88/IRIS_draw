from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene

from iris_db.models import Object, ObjectType


DEFAULT_ISOLINE_WIDTH = 2.0
MIN_ISOLINE_WIDTH = 0.5
MAX_ISOLINE_WIDTH = 20.0

ZONE_ORDER = ('R6', 'R5', 'R4', 'R3', 'R2', 'R1')
ZONE_COLORS = {
    'R6': QColor(255, 255, 0),
    'R5': QColor(128, 0, 128),
    'R4': QColor(0, 255, 0),
    'R3': QColor(255, 165, 0),
    'R2': QColor(0, 0, 255),
    'R1': QColor(255, 0, 0),
}


class IsolineRenderer:
    """Общий рендерер контурных зон поражающих факторов."""

    def __init__(
        self,
        scene: QGraphicsScene,
        line_width: float = DEFAULT_ISOLINE_WIDTH,
    ):
        self.scene = scene
        self.line_width = max(
            MIN_ISOLINE_WIDTH,
            min(float(line_width), MAX_ISOLINE_WIDTH),
        )
        self.zone_colors = ZONE_COLORS.copy()

    @staticmethod
    def _object_path(obj: Object) -> QPainterPath:
        path = QPainterPath()
        first_coord = obj.coordinates[0]
        path.moveTo(first_coord.x, first_coord.y)

        for coord in obj.coordinates[1:]:
            path.lineTo(coord.x, coord.y)

        if obj.object_type == ObjectType.STATIONARY:
            path.closeSubpath()

        return path

    def _zone_path(self, obj: Object, radius_px: float) -> QPainterPath:
        if obj.object_type == ObjectType.POINT:
            center = obj.coordinates[0]
            path = QPainterPath()
            path.addEllipse(
                QRectF(
                    center.x - radius_px,
                    center.y - radius_px,
                    radius_px * 2,
                    radius_px * 2,
                )
            )
            return path

        object_path = self._object_path(obj)
        stroker = QPainterPathStroker()
        stroker.setWidth(radius_px * 2)
        stroker.setCapStyle(Qt.RoundCap)
        stroker.setJoinStyle(Qt.RoundJoin)
        zone_path = stroker.createStroke(object_path)

        if obj.object_type == ObjectType.STATIONARY:
            # Оставляем только внешнюю границу зоны на расстоянии R от объекта.
            zone_path = zone_path.united(object_path)

        return zone_path

    def draw_object_zone(
        self,
        obj: Object,
        painter: QPainter,
        zone: str,
        scale: float,
    ) -> None:
        radius = float(getattr(obj, zone))
        if radius <= 0:
            return

        path = self._zone_path(obj, radius / scale)
        pen = QPen(self.zone_colors[zone])
        pen.setWidthF(self.line_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)

        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
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

        image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)

        for zone in ZONE_ORDER:
            for obj in objects:
                self.draw_object_zone(obj, painter, zone, scale)

        painter.end()

        item = QGraphicsPixmapItem(QPixmap.fromImage(image))
        item.setOpacity(1.0)
        return item
