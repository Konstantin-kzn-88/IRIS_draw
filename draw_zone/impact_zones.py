from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage
from PySide6.QtCore import Qt

from iris_db.database import DatabaseManager
from iris_db.models import Object, ObjectType


class ImpactZoneRenderer:
    """Класс для отрисовки зон поражающих факторов"""

    def __init__(self, scene: QGraphicsScene):
        self.scene = scene
        # Цвета для каждой зоны без прозрачности
        self.zone_colors = {
            'R6': QColor(255, 255, 0),  # Желтый
            'R5': QColor(128, 0, 128),  # Фиолетовый
            'R4': QColor(0, 255, 0),  # Зеленый
            'R3': QColor(255, 165, 0),  # Оранжевый
            'R2': QColor(0, 0, 255),  # Синий
            'R1': QColor(255, 0, 0)  # Красный
        }

    def render_impact_zones(self, obj: Object, scale: float) -> QGraphicsPixmapItem:
        """
        Отрисовывает зоны поражающих факторов для объекта

        Args:
            obj: Объект для которого рисуются зоны
            scale: Масштаб (метров в пикселе)

        Returns:
            QGraphicsPixmapItem: Элемент сцены с отрисованными зонами
        """
        if obj.object_type != ObjectType.POINT:
            raise ValueError("Зоны поражения поддерживаются только для точечных объектов")

        # Получаем размеры сцены
        scene_rect = self.scene.sceneRect()
        width = int(scene_rect.width())
        height = int(scene_rect.height())

        # Создаем белое изображение
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.white)

        # Создаем художника для рисования
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)

        # Получаем координаты центра объекта
        center_x = obj.coordinates[0].x
        center_y = obj.coordinates[0].y

        # Рисуем круги для каждой зоны (от большей к меньшей)
        zones = ['R6', 'R5', 'R4', 'R3', 'R2', 'R1']
        for zone in zones:
            radius = getattr(obj, zone)  # Получаем радиус из объекта
            radius_px = radius / scale

            # Устанавливаем цвет для зоны
            painter.setBrush(self.zone_colors[zone])
            painter.setPen(Qt.NoPen)

            # Рисуем круг
            painter.drawEllipse(
                center_x - radius_px,
                center_y - radius_px,
                radius_px * 2,
                radius_px * 2
            )

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


def draw_impact_zones(main_window) -> bool:
    """
    Отрисовывает зоны поражающих факторов для выбранного объекта

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

            if obj.object_type != ObjectType.POINT:
                raise ValueError("Зоны поражения поддерживаются только для точечных объектов")

            # Создаем рендерер и отрисовываем зоны
            renderer = ImpactZoneRenderer(main_window.scene)
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