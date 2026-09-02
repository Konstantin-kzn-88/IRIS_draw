from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene

from draw_zone.isoline_renderer import DEFAULT_ISOLINE_WIDTH, IsolineRenderer
from iris_db.database import DatabaseManager
from iris_db.models import Object, ObjectType


class StationaryImpactRenderer(IsolineRenderer):
    """Отрисовка изолиний для стационарного объекта."""

    def __init__(
        self,
        scene: QGraphicsScene,
        line_width: float = DEFAULT_ISOLINE_WIDTH,
    ):
        super().__init__(scene, line_width)

    def render_impact_zones(
        self,
        obj: Object,
        scale: float,
    ) -> QGraphicsPixmapItem:
        if obj.object_type != ObjectType.STATIONARY:
            raise ValueError("Этот рендерер поддерживает только стационарные объекты")
        return self.render_objects([obj], scale)


def draw_stationary_impact_zones(main_window) -> bool:
    """Отрисовывает изолинии для выбранного стационарного объекта."""
    if not main_window.is_plan_loaded():
        main_window.statusBar().showMessage("Сначала необходимо загрузить план", 3000)
        return False

    if not main_window.scale_for_plan:
        main_window.statusBar().showMessage("Сначала необходимо измерить масштаб", 3000)
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
            if obj.object_type != ObjectType.STATIONARY:
                raise ValueError("Выбранный объект не является стационарным")

            renderer = StationaryImpactRenderer(
                main_window.scene,
                main_window.isoline_width,
            )
            main_window.scene.addItem(
                renderer.render_impact_zones(obj, main_window.scale_for_plan)
            )
            main_window.statusBar().showMessage(
                "Изолинии поражающих факторов отрисованы",
                3000,
            )
            return True

    except Exception as error:
        main_window.statusBar().showMessage(
            f"Ошибка при отрисовке зон: {error}",
            3000,
        )
        return False
