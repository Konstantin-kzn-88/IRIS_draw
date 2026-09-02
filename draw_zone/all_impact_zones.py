from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene

from draw_zone.isoline_renderer import DEFAULT_ISOLINE_WIDTH, IsolineRenderer
from iris_db.database import DatabaseManager
from iris_db.models import Object


class AllImpactRenderer(IsolineRenderer):
    """Отрисовка изолиний для всех объектов на плане."""

    def __init__(
        self,
        scene: QGraphicsScene,
        line_width: float = DEFAULT_ISOLINE_WIDTH,
    ):
        super().__init__(scene, line_width)

    def render_impact_zones(
        self,
        objects: list[Object],
        scale: float,
    ) -> QGraphicsPixmapItem:
        return self.render_objects(objects, scale)


def draw_all_impact_zones(main_window) -> bool:
    """Отрисовывает изолинии поражающих факторов для всех объектов."""
    if not main_window.is_plan_loaded():
        main_window.statusBar().showMessage("Сначала необходимо загрузить план", 3000)
        return False

    if not main_window.scale_for_plan:
        main_window.statusBar().showMessage("Сначала необходимо измерить масштаб", 3000)
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

            renderer = AllImpactRenderer(
                main_window.scene,
                main_window.isoline_width,
            )
            main_window.scene.addItem(
                renderer.render_impact_zones(objects, main_window.scale_for_plan)
            )
            main_window.statusBar().showMessage(
                "Изолинии отрисованы для всех объектов",
                3000,
            )
            return True

    except Exception as error:
        main_window.statusBar().showMessage(
            f"Ошибка при отрисовке зон: {error}",
            3000,
        )
        return False
