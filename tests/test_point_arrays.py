"""Point arrays: actual Qt events, database round trips and geometry equivalence."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsScene

from draw_zone.filled_zone_renderer import FilledZoneRenderer
from draw_zone.impact_zones import ImpactZoneRenderer
from draw_zone.risk_zones import RadiationWorker
from iris_db.database import DatabaseManager
from iris_db.models import Coordinate, Image, Object, ObjectType
from main import MainWindow
from service.distance_analyzer import DistanceAnalyzer


def point_object(points, image_id=1, name="Array", **radii):
    values = {f"R{i}": 0.0 for i in range(1, 7)}
    values.update(radii)
    return Object(None, image_id, name, object_type=ObjectType.POINT,
                  coordinates=[Coordinate(None, 0, x, y, i)
                               for i, (x, y) in enumerate(points)], **values)


class PointArrayDatabaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = str(Path(temp.name) / "test.db")
        with DatabaseManager(self.path) as db:
            self.image_id = db.images.create(Image(None, "plan.jpg", b"image", None,
                                                  "image/jpeg", 5, []))

    def test_round_trip_and_delete_all_coordinates(self):
        points = [(1.25, 2.5), (11.5, 22.75), (100, 110)]
        with DatabaseManager(self.path) as db:
            obj = point_object(points, self.image_id, R6=30)
            object_id = db.objects.create(obj)
        with DatabaseManager(self.path) as db:
            saved = db.objects.get_by_id(object_id)
            self.assertEqual([(c.x, c.y) for c in saved.coordinates], points)
            self.assertEqual([c.order_index for c in saved.coordinates], [0, 1, 2])
            self.assertEqual(saved.R6, 30)
            self.assertEqual(len(db.objects.get_by_image_id(self.image_id)), 1)
            db.objects.delete(object_id)
            self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM coordinates").fetchone()[0], 0)

    def test_empty_point_object_is_rejected(self):
        with DatabaseManager(self.path) as db:
            with self.assertRaises(ValueError):
                db.objects.create(point_object([], self.image_id))

    def reject_second_coordinate(self, db):
        db.conn.execute("""CREATE TRIGGER reject_coordinate BEFORE INSERT ON coordinates
                           WHEN NEW.order_index = 1
                           BEGIN SELECT RAISE(ABORT, 'blocked'); END""")
        db.conn.commit()

    def test_failed_array_insert_rolls_back_object_and_every_coordinate(self):
        with DatabaseManager(self.path) as db:
            self.reject_second_coordinate(db)
            with self.assertRaises(sqlite3.IntegrityError):
                db.objects.create(point_object([(1, 2), (3, 4)], self.image_id))
            for table in ("objects", "coordinates"):
                self.assertEqual(db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_failed_update_retains_name_radii_and_original_coordinates(self):
        with DatabaseManager(self.path) as db:
            object_id = db.objects.create(point_object([(1, 2), (3, 4)], self.image_id, R6=50))
            saved = db.objects.get_by_id(object_id)
            before = db.conn.execute("SELECT * FROM coordinates").fetchall()
            self.reject_second_coordinate(db)
            saved.name = "Changed"
            saved.R6 = 100
            saved.coordinates = point_object([(10, 20), (30, 40)]).coordinates
            with self.assertRaises(sqlite3.IntegrityError):
                db.objects.update(saved)
            unchanged = db.objects.get_by_id(object_id)
            self.assertEqual(unchanged.name, "Array")
            self.assertEqual(unchanged.R6, 50)
            self.assertEqual(db.conn.execute("SELECT * FROM coordinates").fetchall(), before)


class PointArrayWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "test.db"
        with patch("service.database_handler.get_database_path", return_value=self.path):
            self.window = MainWindow()
        self.addCleanup(self.window.close)
        image_path = Path(temp.name) / "plan.jpg"
        image = QImage(360, 260, QImage.Format_RGB32)
        image.fill(QColor("white"))
        image.save(str(image_path), "JPG")
        with patch("main.QFileDialog.getOpenFileName", return_value=(str(image_path), "")):
            self.window.add_plan()
        self.image_id = self.window.current_image_id

    def objects(self):
        with DatabaseManager(str(self.path)) as db:
            return db.objects.get_by_image_id(self.window.current_image_id)

    def enter_array(self, points):
        self.window.start_point_array()
        for x, y in points:
            self.window.object_manager.handle_mouse_click(QPointF(x, y))
        QTest.keyClick(self.window.view, Qt.Key_Return)

    def test_menu_clicks_enter_save_one_row_and_show_every_point(self):
        action = next(a for a in self.window.findChildren(QAction)
                      if a.text() == "Ввести массив точек")
        self.window.show()
        self.app.processEvents()
        self.window.view.reset_scale()
        action.trigger()
        viewport = self.window.view.viewport()
        points = [(50, 60), (150, 160), (250, 60)]
        with patch("service.object_manager.QInputDialog.getText") as name_dialog:
            for x, y in points:
                QTest.mouseClick(viewport, Qt.LeftButton,
                                 pos=self.window.view.mapFromScene(QPointF(x, y)))
            self.assertEqual(self.objects(), [])
            self.assertEqual(len(self.window.object_manager.temp_drawing.temp_items), 3)
            self.assertTrue(all(isinstance(i, QGraphicsEllipseItem)
                                for i in self.window.object_manager.temp_drawing.temp_items))
            QTest.keyClick(self.window.view, Qt.Key_Return)
            name_dialog.assert_not_called()
        saved, = self.objects()
        self.assertEqual(saved.name, "массив_1")
        self.assertEqual([(c.x, c.y) for c in saved.coordinates], points)
        self.assertEqual(self.window.object_table.rowCount(), 1)
        items = self.window.object_items[saved.id].items
        self.assertEqual(len(items), 3)
        self.assertTrue(all(i.isVisible() for i in items))
        self.assertFalse(self.window.object_manager.is_drawing)

    def test_double_click_with_mouse_movement_keeps_last_point_once(self):
        self.window.start_point_array()
        manager = self.window.object_manager
        manager.handle_mouse_click(QPointF(40, 50))
        manager.handle_mouse_click(QPointF(140, 150))
        manager.handle_mouse_click(QPointF(141, 150), double_click=True)
        self.assertEqual([(c.x, c.y) for c in self.objects()[0].coordinates],
                         [(40, 50), (140, 150)])

    def test_actual_double_click_event_finishes_input(self):
        self.window.show()
        self.app.processEvents()
        self.window.start_point_array()
        view = self.window.view
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.mapFromScene(QPointF(50, 60)))
        last = view.mapFromScene(QPointF(150, 160))
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=last)
        QTest.mouseDClick(view.viewport(), Qt.LeftButton, pos=last)
        self.assertEqual(len(self.objects()[0].coordinates), 2)
        self.assertFalse(self.window.object_manager.is_drawing)

    def test_escape_and_empty_enter_do_not_save_and_next_input_is_clean(self):
        self.window.start_point_array()
        QTest.keyClick(self.window.view, Qt.Key_Return)
        self.assertTrue(self.window.object_manager.is_drawing)
        self.window.object_manager.handle_mouse_click(QPointF(10, 20))
        QTest.keyClick(self.window.view, Qt.Key_Escape)
        self.assertEqual(self.objects(), [])
        self.assertEqual(self.window.object_manager.temp_drawing.temp_items, [])
        self.enter_array([(30, 40)])
        self.assertEqual([(c.x, c.y) for c in self.objects()[0].coordinates], [(30, 40)])

    def test_right_click_does_not_place_point(self):
        self.window.start_point_array()
        QTest.mouseClick(self.window.view.viewport(), Qt.RightButton)
        self.assertEqual(self.window.object_manager.temp_coordinates, [])

    def test_numbering_continues_after_reopening_and_saved_arrays_are_restored(self):
        self.enter_array([(10, 20), (30, 40)])
        first, = self.objects()
        with DatabaseManager(str(self.path)) as db:
            first.R5, first.R6 = 20, 40
            db.objects.update(first)
            coord_ids = [c.id for c in db.objects.get_by_id(first.id).coordinates]
        self.window.close()
        with patch("service.database_handler.get_database_path", return_value=self.path):
            self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.assertTrue(self.window.load_plan(self.image_id))
        first, = self.objects()
        self.assertEqual(len(self.window.object_items[first.id].items), 2)
        self.assertEqual([c.id for c in first.coordinates], coord_ids)
        self.assertEqual((first.R5, first.R6), (20, 40))
        self.enter_array([(50, 60), (70, 80)])
        self.assertEqual([o.name for o in self.objects()], ["массив_1", "массив_2"])

    def test_edit_array_changes_all_points_and_escape_preserves_them(self):
        self.enter_array([(10, 20), (30, 40)])
        saved, = self.objects()
        self.window.start_edit_coordinates(saved.id)
        editor = self.window.edit_coordinates_manager
        self.assertTrue(editor.is_point_array)
        for x, y in [(50, 60), (70, 80), (90, 100)]:
            editor.handle_mouse_click(QPointF(x, y))
        editor.handle_mouse_move(QPointF(150, 150))
        self.assertTrue(editor.is_editing)
        QTest.keyClick(self.window.view, Qt.Key_Enter)
        expected = [(50, 60), (70, 80), (90, 100)]
        self.assertEqual([(c.x, c.y) for c in self.objects()[0].coordinates], expected)
        self.window.start_edit_coordinates(saved.id)
        editor.handle_mouse_click(QPointF(200, 210))
        QTest.keyClick(self.window.view, Qt.Key_Escape)
        self.assertEqual([(c.x, c.y) for c in self.objects()[0].coordinates], expected)
        self.assertTrue(all(i.isVisible() for i in self.window.object_items[saved.id].items))

    def test_switching_or_clearing_plan_cancels_unsaved_array(self):
        self.window.start_point_array()
        self.window.object_manager.handle_mouse_click(QPointF(10, 20))
        self.assertTrue(self.window.clear_plan())
        self.assertFalse(self.window.object_manager.is_drawing)
        self.assertEqual(self.objects(), [])
        self.window.start_point_array()
        self.window.object_manager.handle_mouse_click(QPointF(30, 40))
        self.assertTrue(self.window.load_plan(self.image_id))
        self.assertFalse(self.window.object_manager.is_point_array)
        self.assertEqual(self.objects(), [])

    def test_failed_save_keeps_preview_and_can_be_retried(self):
        self.window.start_point_array()
        for x, y in [(10, 20), (30, 40)]:
            self.window.object_manager.handle_mouse_click(QPointF(x, y))
        with DatabaseManager(str(self.path)) as db:
            db.conn.execute("""CREATE TRIGGER reject_coordinate BEFORE INSERT ON coordinates
                               WHEN NEW.order_index = 1
                               BEGIN SELECT RAISE(ABORT, 'blocked'); END""")
            db.conn.commit()
        with patch("service.object_manager.QMessageBox.critical") as message:
            QTest.keyClick(self.window.view, Qt.Key_Return)
            message.assert_called_once()
        self.assertEqual(self.objects(), [])
        self.assertTrue(self.window.object_manager.is_drawing)
        self.assertEqual(len(self.window.object_manager.temp_drawing.temp_items), 2)
        with DatabaseManager(str(self.path)) as db:
            db.conn.execute("DROP TRIGGER reject_coordinate")
            db.conn.commit()
        QTest.keyClick(self.window.view, Qt.Key_Return)
        self.assertEqual(len(self.objects()[0].coordinates), 2)


class PointArrayGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.scene = QGraphicsScene()
        self.scene.setSceneRect(0, 0, 360, 260)

    def test_array_isolines_equal_individually_entered_points_and_merge_overlaps(self):
        points = [(100, 110), (160, 110)]
        array = point_object(points, R6=60, R5=25)
        renderer = ImpactZoneRenderer(self.scene)
        image = renderer.render_impact_zones(array, 1.0).pixmap().toImage()
        separate = renderer.render_objects([point_object([p], R6=60, R5=25)
                                            for p in points], 1.0).pixmap().toImage()
        self.assertEqual(image, separate)
        self.assertEqual(image.pixelColor(100, 110).alpha(), 0)
        self.assertGreater(image.pixelColor(220, 110).alpha(), 0)
        self.assertGreater(image.pixelColor(125, 110).alpha(), 0)

    def test_filled_zones_cover_every_point_without_connecting_them(self):
        array = point_object([(60, 100), (260, 100)], R6=20)
        renderer = FilledZoneRenderer(self.scene)
        image = renderer.render_objects([array], 0.5).pixmap().toImage()
        for x in (60, 260):
            self.assertGreater(image.pixelColor(x, 100).alpha(), 0)
        self.assertEqual(image.pixelColor(160, 100).alpha(), 0)

    def test_distance_uses_nearest_point_in_each_array(self):
        analyzer = DistanceAnalyzer()
        first = point_object([(0, 0), (100, 0)])
        second = point_object([(200, 0), (103, 4)])
        self.assertEqual(analyzer.calculate_distance(first, second, 0.5), 2.5)
        self.assertEqual(analyzer.calculate_distance(first, point_object([(100, 0)]), 1), 0)

    def test_array_risk_equals_sum_of_individual_point_contributions(self):
        def raster(points):
            worker = RadiationWorker(100, 80, {"type": "point", "R6": 20,
                                              "coordinates": points}, 1, 1)
            x, y, fragment = worker.calculate()
            image = np.zeros((80, 100))
            image[y:y + fragment.shape[0], x:x + fragment.shape[1]] = fragment
            return image

        points = [(30, 40), (45, 40), (-100, -100)]
        combined = raster(points)
        expected = sum((raster([p]) for p in points), np.zeros((80, 100)))
        np.testing.assert_allclose(combined, expected)
        self.assertGreater(combined[40, 35], raster([points[0]])[40, 35])


if __name__ == "__main__":
    unittest.main()
