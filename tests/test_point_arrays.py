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
from PySide6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsScene, QMessageBox

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
            objects = [point_object([point], self.image_id, name=f"массив_{i+1}", R6=30+i)
                       for i, point in enumerate(points)]
            ids = db.objects.create_many(objects)
        with DatabaseManager(self.path) as db:
            saved = db.objects.get_by_image_id(self.image_id)
            self.assertEqual([(o.coordinates[0].x, o.coordinates[0].y) for o in saved], points)
            self.assertEqual([o.R6 for o in saved], [30, 31, 32])
            self.assertTrue(all(len(o.coordinates) == 1 and o.coordinates[0].order_index == 0
                                for o in saved))
            db.objects.delete(ids[1])
            self.assertEqual([o.id for o in db.objects.get_by_image_id(self.image_id)],
                             [ids[0], ids[2]])
            self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM coordinates").fetchone()[0], 2)

    def test_empty_point_object_is_rejected(self):
        with DatabaseManager(self.path) as db:
            with self.assertRaises(ValueError):
                db.objects.create(point_object([], self.image_id))

    def reject_coordinate(self, db):
        db.conn.execute("""CREATE TRIGGER reject_coordinate BEFORE INSERT ON coordinates
                           WHEN NEW.x = 30
                           BEGIN SELECT RAISE(ABORT, 'blocked'); END""")
        db.conn.commit()

    def test_failed_array_insert_rolls_back_object_and_every_coordinate(self):
        with DatabaseManager(self.path) as db:
            self.reject_coordinate(db)
            with self.assertRaises(sqlite3.IntegrityError):
                db.objects.create_many([point_object([(1, 2)], self.image_id),
                                        point_object([(30, 40)], self.image_id)])
            for table in ("objects", "coordinates"):
                self.assertEqual(db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_failed_update_retains_name_radii_and_original_coordinates(self):
        with DatabaseManager(self.path) as db:
            object_id = db.objects.create(point_object([(1, 2)], self.image_id, R6=50))
            saved = db.objects.get_by_id(object_id)
            before = db.conn.execute("SELECT * FROM coordinates").fetchall()
            self.reject_coordinate(db)
            saved.name = "Changed"
            saved.R6 = 100
            saved.coordinates = point_object([(30, 40)]).coordinates
            with self.assertRaises(sqlite3.IntegrityError):
                db.objects.update(saved)
            unchanged = db.objects.get_by_id(object_id)
            self.assertEqual(unchanged.name, "Array")
            self.assertEqual(unchanged.R6, 50)
            self.assertEqual(db.conn.execute("SELECT * FROM coordinates").fetchall(), before)

    def test_invalid_point_in_batch_saves_nothing(self):
        with DatabaseManager(self.path) as db:
            with self.assertRaises(ValueError):
                db.objects.create_many([point_object([(1, 2)], self.image_id),
                                        point_object([(3, 4), (5, 6)], self.image_id)])
            self.assertEqual(db.objects.get_by_image_id(self.image_id), [])

    def seed_legacy_group(self, name="массив_1", existing_name="массив_9"):
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute("""
                INSERT INTO objects (image_id, name, R1, R2, R3, R4, R5, R6, object_type)
                VALUES (?, ?, 1, 2, 3, 4, 5, 6, 'point')
            """, (self.image_id, name))
            group_id = cursor.lastrowid
            conn.executemany(
                "INSERT INTO coordinates (object_id, x, y, order_index) VALUES (?, ?, ?, ?)",
                [(group_id, 10, 20, 0), (group_id, 30, 40, 1), (group_id, 50, 60, 2)]
            )
            other = conn.execute(
                "INSERT INTO objects (image_id, name, object_type) VALUES (?, ?, 'point')",
                (self.image_id, existing_name)
            ).lastrowid
            conn.execute("INSERT INTO coordinates (object_id, x, y, order_index) VALUES (?, 90, 100, 0)",
                         (other,))
            conn.execute("UPDATE images SET scale = 0.25 WHERE id = ?", (self.image_id,))
            conn.execute("PRAGMA user_version = 1")
            coordinates = conn.execute("SELECT id, x, y FROM coordinates ORDER BY id").fetchall()
        return group_id, coordinates

    def test_legacy_groups_split_once_preserving_ids_radii_image_and_scale(self):
        group_id, old_coordinates = self.seed_legacy_group()
        with DatabaseManager(self.path) as db:
            points = db.objects.get_by_image_id(self.image_id)
            self.assertEqual([o.name for o in points],
                             ["массив_1", "массив_9", "массив_10", "массив_11"])
            self.assertEqual(points[0].id, group_id)
            self.assertTrue(all(len(o.coordinates) == 1 for o in points))
            for point in (points[0], points[2], points[3]):
                self.assertEqual(tuple(getattr(point, f"R{i}") for i in range(1, 7)),
                                 (1, 2, 3, 4, 5, 6))
            self.assertEqual(db.conn.execute("SELECT id, x, y FROM coordinates ORDER BY id").fetchall(),
                             old_coordinates)
            self.assertEqual(db.images.get_scale(self.image_id), 0.25)
            self.assertEqual(db.images.get_image_data(self.image_id), b"image")
            self.assertEqual(db.conn.execute("PRAGMA user_version").fetchone()[0], 2)
        with DatabaseManager(self.path) as db:
            self.assertEqual(len(db.objects.get_by_image_id(self.image_id)), 4)

    def test_legacy_custom_names_do_not_collide_with_existing_points(self):
        self.seed_legacy_group(name="Скважина", existing_name="Скважина_2")
        with DatabaseManager(self.path) as db:
            self.assertEqual([o.name for o in db.objects.get_by_image_id(self.image_id)],
                             ["Скважина", "Скважина_2", "Скважина_3", "Скважина_4"])

    def test_failed_legacy_split_rolls_back_entire_migration(self):
        self.seed_legacy_group()
        with sqlite3.connect(self.path) as conn:
            before_objects = conn.execute("SELECT * FROM objects").fetchall()
            before_coordinates = conn.execute("SELECT * FROM coordinates").fetchall()
            conn.execute("""
                CREATE TRIGGER reject_move BEFORE UPDATE OF object_id ON coordinates
                WHEN OLD.order_index = 1 BEGIN SELECT RAISE(ABORT, 'blocked'); END
            """)
        with self.assertRaises(sqlite3.IntegrityError):
            DatabaseManager(self.path)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute("SELECT * FROM objects").fetchall(), before_objects)
            self.assertEqual(conn.execute("SELECT * FROM coordinates").fetchall(), before_coordinates)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)


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

    def test_menu_clicks_enter_save_separate_rows_and_show_every_point(self):
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
        saved = self.objects()
        self.assertEqual([o.name for o in saved], ["массив_1", "массив_2", "массив_3"])
        self.assertEqual([(o.coordinates[0].x, o.coordinates[0].y) for o in saved], points)
        self.assertEqual(self.window.object_table.rowCount(), 3)
        for obj in saved:
            items = self.window.object_items[obj.id].items
            self.assertEqual(len(items), 1)
            self.assertTrue(items[0].isVisible())
        self.assertFalse(self.window.object_manager.is_drawing)

    def test_double_click_with_mouse_movement_keeps_last_point_once(self):
        self.window.start_point_array()
        manager = self.window.object_manager
        manager.handle_mouse_click(QPointF(40, 50))
        manager.handle_mouse_click(QPointF(140, 150))
        manager.handle_mouse_click(QPointF(141, 150), double_click=True)
        self.assertEqual([(o.coordinates[0].x, o.coordinates[0].y) for o in self.objects()],
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
        self.assertEqual(len(self.objects()), 2)
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
        first, second = self.objects()
        with DatabaseManager(str(self.path)) as db:
            first.R5, first.R6 = 20, 40
            db.objects.update(first)
            coord_ids = [c.id for c in db.objects.get_by_id(first.id).coordinates]
        self.window.close()
        with patch("service.database_handler.get_database_path", return_value=self.path):
            self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.assertTrue(self.window.load_plan(self.image_id))
        first, second = self.objects()
        self.assertEqual(len(self.window.object_items[first.id].items), 1)
        self.assertEqual([c.id for c in first.coordinates], coord_ids)
        self.assertEqual((first.R5, first.R6), (20, 40))
        self.assertEqual((second.R5, second.R6), (0, 0))
        self.enter_array([(50, 60), (70, 80)])
        self.assertEqual([o.name for o in self.objects()],
                         ["массив_1", "массив_2", "массив_3", "массив_4"])

    def test_move_and_cancel_affect_only_selected_point(self):
        self.enter_array([(10, 20), (30, 40)])
        saved, other = self.objects()
        self.window.object_table.selectRow(0)
        self.window.start_edit_coordinates(saved.id)
        editor = self.window.edit_coordinates_manager
        editor.handle_mouse_click(QPointF(50, 60))
        self.assertFalse(editor.is_editing)
        expected = [(50, 60), (30, 40)]
        self.assertEqual([(o.coordinates[0].x, o.coordinates[0].y) for o in self.objects()], expected)
        self.window.start_edit_coordinates(saved.id)
        editor.handle_mouse_move(QPointF(200, 210))
        QTest.keyClick(self.window.view, Qt.Key_Escape)
        self.assertEqual([(o.coordinates[0].x, o.coordinates[0].y) for o in self.objects()], expected)
        self.assertTrue(all(i.isVisible() for i in self.window.object_items[saved.id].items))

    def test_each_point_has_independent_radii_after_table_edits_and_reopening(self):
        self.enter_array([(60, 100), (260, 100)])
        expected = [(5, 10, 15, 20, 25, 30), (10, 20, 30, 40, 50, 60)]
        for row, radii in enumerate(expected):
            for column, radius in enumerate(radii, start=3):
                self.window.object_table.item(row, column).setText(str(radius))
        self.assertTrue(self.window.load_plan(self.image_id))
        saved = self.objects()
        self.assertEqual([tuple(getattr(o, f"R{i}") for i in range(1, 7)) for o in saved], expected)
        self.window.set_plan_scale(1.0)
        renderer = ImpactZoneRenderer(self.window.scene)
        image = renderer.render_objects(saved, 1.0).pixmap().toImage()
        self.assertGreater(image.pixelColor(90, 100).alpha(), 0)
        self.assertEqual(image.pixelColor(120, 100).alpha(), 0)
        self.assertGreater(image.pixelColor(320, 100).alpha(), 0)

    def test_delete_one_batch_point_keeps_the_other(self):
        self.enter_array([(10, 20), (30, 40)])
        first, second = self.objects()
        self.window.object_table.selectRow(0)
        with patch("service.object_table.QMessageBox.question", return_value=QMessageBox.Yes):
            self.window.object_table.delete_selected_object()
        self.assertEqual([o.id for o in self.objects()], [second.id])

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
                               WHEN NEW.x = 30
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
        self.assertEqual(len(self.objects()), 2)


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
