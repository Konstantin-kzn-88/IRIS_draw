"""Check actual pixels to keep overlapping zone boundaries out of the drawing."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsScene

from draw_zone.all_impact_zones import AllImpactRenderer
from draw_zone.isoline_renderer import ZONE_ORDER, ZONE_COLORS
from iris_db.models import Coordinate, Object, ObjectType


def make_object(object_type, points, **radii):
    values = {f"R{i}": 0.0 for i in range(1, 7)}
    values.update(radii)
    return Object(
        id=None, image_id=1, name="Object", object_type=object_type,
        coordinates=[Coordinate(None, 0, x, y, i) for i, (x, y) in enumerate(points)],
        **values,
    )


class IsolineRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.scene = QGraphicsScene()
        self.scene.setSceneRect(0, 0, 360, 260)
        self.renderer = AllImpactRenderer(self.scene)

    def render(self, objects, scale=1.0):
        return self.renderer.render_impact_zones(objects, scale).pixmap().toImage()

    def test_intersecting_circles_keep_outer_contour_without_internal_arcs(self):
        objects = [
            make_object(ObjectType.POINT, [(100, 110)], R6=60),
            make_object(ObjectType.POINT, [(160, 110)], R6=60),
        ]
        image = self.render(objects)
        # These are each circle's boundary, inside the other circle.
        for x, y in [(160, 110), (100, 110)]:
            self.assertEqual(image.pixelColor(x, y).alpha(), 0)
        for x, y in [(40, 110), (220, 110), (130, 58), (130, 162)]:
            self.assertGreater(image.pixelColor(x, y).alpha(), 0)

    def test_contained_zone_does_not_add_an_inner_outline(self):
        image = self.render([
            make_object(ObjectType.POINT, [(120, 120)], R6=80),
            make_object(ObjectType.POINT, [(140, 120)], R6=20),
        ])
        self.assertEqual(image.pixelColor(160, 120).alpha(), 0)
        self.assertGreater(image.pixelColor(200, 120).alpha(), 0)

    def test_different_levels_remain_visible_inside_larger_zones(self):
        image = self.render([
            make_object(ObjectType.POINT, [(100, 110)], R6=70, R5=25),
            make_object(ObjectType.POINT, [(160, 110)], R6=70, R5=25),
        ])
        for x, zone in [(125, "R5"), (135, "R5"), (30, "R6")]:
            color = image.pixelColor(x, 110)
            self.assertGreater(color.alpha(), 200)
            for actual, expected in zip(color.getRgb()[:3], ZONE_COLORS[zone].getRgb()[:3]):
                self.assertAlmostEqual(actual, expected, delta=1)

    def test_disjoint_objects_keep_both_closed_contours(self):
        image = self.render([
            make_object(ObjectType.POINT, [(60, 110)], R6=30),
            make_object(ObjectType.POINT, [(220, 110)], R6=30),
        ])
        for x in (30, 90, 190, 250):
            self.assertGreater(image.pixelColor(x, 110).alpha(), 0)
        self.assertEqual(image.pixelColor(140, 110).alpha(), 0)

    def test_point_linear_and_stationary_zones_merge_together(self):
        image = self.render([
            make_object(ObjectType.STATIONARY, [(80, 80), (160, 80), (160, 160), (80, 160), (80, 80)], R6=20),
            make_object(ObjectType.POINT, [(180, 120)], R6=40),
            make_object(ObjectType.LINEAR, [(160, 120), (240, 120)], R6=20),
        ])
        for x, y in [(140, 120), (180, 120), (220, 120), (200, 100)]:
            self.assertEqual(image.pixelColor(x, y).alpha(), 0)
        for x, y in [(60, 120), (120, 60), (260, 120)]:
            self.assertGreater(image.pixelColor(x, y).alpha(), 0)

    def test_a_real_gap_inside_a_ring_preserves_its_boundary(self):
        corners = [(60, 60), (180, 60), (180, 180), (60, 180)]
        objects = [
            make_object(ObjectType.LINEAR, [start, end], R6=10)
            for start, end in zip(corners, corners[1:] + corners[:1])
        ]
        image = self.render(objects)
        self.assertEqual(image.pixelColor(120, 120).alpha(), 0)
        self.assertGreater(image.pixelColor(120, 70).alpha(), 0)
        self.assertGreater(image.pixelColor(120, 50).alpha(), 0)

    def test_scale_is_used_before_merging(self):
        image = self.render([
            make_object(ObjectType.POINT, [(100, 110)], R6=30),
            make_object(ObjectType.POINT, [(160, 110)], R6=30),
        ], scale=0.5)
        self.assertEqual(image.pixelColor(160, 110).alpha(), 0)
        self.assertGreater(image.pixelColor(40, 110).alpha(), 0)

    def test_zero_and_negative_radii_are_not_drawn(self):
        image = self.render([
            make_object(ObjectType.POINT, [(100, 110)], R6=0, R5=-10),
            make_object(ObjectType.POINT, [(160, 110)], R6=30),
        ])
        self.assertEqual(image.pixelColor(100, 110).alpha(), 0)
        self.assertGreater(image.pixelColor(190, 110).alpha(), 0)

    def test_single_object_rendering_matches_the_original_contours(self):
        objects = [
            make_object(ObjectType.POINT, [(120, 120)], R6=70, R5=30),
            make_object(ObjectType.LINEAR, [(80, 80), (180, 120), (120, 180)], R6=30, R5=10),
            make_object(ObjectType.STATIONARY, [(80, 80), (160, 80), (120, 160), (80, 80)], R6=30, R5=10),
        ]
        for obj in objects:
            with self.subTest(object_type=obj.object_type):
                expected = QImage(360, 260, QImage.Format_ARGB32_Premultiplied)
                expected.fill(Qt.transparent)
                painter = QPainter(expected)
                painter.setRenderHint(QPainter.Antialiasing)
                for zone in ZONE_ORDER:
                    self.renderer.draw_object_zone(obj, painter, zone, 1.0)
                painter.end()
                self.assertEqual(self.render([obj]), expected)


if __name__ == "__main__":
    unittest.main()
