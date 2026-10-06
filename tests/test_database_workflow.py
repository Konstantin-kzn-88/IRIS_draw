"""Regression checks using temporary databases and an offscreen Qt application."""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QMessageBox, QMenu

from iris_db.database import DatabaseManager
from iris_db.models import Image, Object, ObjectType, Coordinate
from iris_db.schema import CREATE_TABLES_SQL
from main import MainWindow
from service.database_handler import DatabaseHandler, get_database_path


def add_plan(db, data=b"image"):
    return db.images.create(Image(None, "plan.jpg", data, 1.0, "image/jpeg", len(data), []))


def add_object(db, image_id):
    return db.objects.create(Object(
        None, image_id, "Object", 0, 0, 0, 0, 0, 0, ObjectType.POINT,
        [Coordinate(None, 0, 10, 20, 0)]
    ))


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_empty_directory_uses_default_and_ignores_sidecars(self):
        (self.directory / "backup.db").mkdir()
        (self.directory / "old.db-wal").touch()
        self.assertEqual(get_database_path(self.directory), self.directory / "iris.db")

    def test_existing_database_connects_without_losing_plans(self):
        path = self.directory / "Existing.DB"
        with DatabaseManager(str(path)) as db:
            image_id = add_plan(db)
        self.assertEqual(get_database_path(self.directory), path)
        handler = DatabaseHandler()
        with patch("service.database_handler.get_database_path", return_value=path):
            self.assertTrue(handler.connect_to_database())
        with DatabaseManager(handler.current_db_path) as db:
            self.assertIsNotNone(db.images.get_by_id(image_id))
        handler.close()
        self.assertFalse(handler.connection)
        self.assertIsNone(handler.current_db_path)

    def test_startup_creates_database_when_missing(self):
        path = self.directory / "iris.db"
        handler = DatabaseHandler()
        with patch("service.database_handler.get_database_path", return_value=path):
            self.assertTrue(handler.connect_to_database())
        self.assertTrue(path.is_file())
        with DatabaseManager(str(path)) as db:
            self.assertEqual(db.images.get_all(), [])

    def test_source_path_does_not_depend_on_working_directory(self):
        import service.database_handler as module
        script = self.directory / "service" / "database_handler.py"
        with patch.object(module, "__file__", str(script)), patch.object(sys, "frozen", False, create=True):
            self.assertEqual(get_database_path(), self.directory / "iris.db")

    def test_packaged_application_uses_executable_directory(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", str(self.directory / "iris.exe")):
            self.assertEqual(get_database_path(), self.directory / "iris.db")

    def test_multiple_databases_are_not_selected_arbitrarily(self):
        (self.directory / "a.db").touch()
        (self.directory / "b.sqlite3").touch()
        with self.assertRaisesRegex(ValueError, "несколько баз"):
            get_database_path(self.directory)
        self.assertFalse((self.directory / "iris.db").exists())

    def test_invalid_database_reports_connection_failure(self):
        path = self.directory / "broken.db"
        path.write_bytes(b"not a SQLite database")
        handler = DatabaseHandler()
        with patch("service.database_handler.get_database_path", return_value=path):
            self.assertFalse(handler.connect_to_database())
        self.assertFalse(handler.connection)
        self.assertIsNone(handler.current_db_path)
        self.assertTrue(handler.last_error)

    def test_clear_cascades_and_vacuum_reclaims_disk_space(self):
        path = self.directory / "test.db"
        with DatabaseManager(str(path)) as db:
            for _ in range(2):
                add_object(db, add_plan(db, b"x" * (1024 * 1024)))
            size_before = path.stat().st_size
            db.clear_plans()
            db.vacuum()
            for table in ("images", "objects", "coordinates"):
                self.assertEqual(db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
            self.assertEqual(db.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(db.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(db.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertLess(path.stat().st_size, size_before)
            add_object(db, add_plan(db))  # Database remains usable after compaction.

    def test_failed_clear_rolls_back_all_plans_and_children(self):
        with DatabaseManager(str(self.directory / "test.db")) as db:
            for _ in range(2):
                add_object(db, add_plan(db))
            db.conn.execute("""
                CREATE TRIGGER prevent_delete BEFORE DELETE ON images
                WHEN OLD.id = 2 BEGIN SELECT RAISE(ABORT, 'blocked'); END
            """)
            db.conn.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                db.clear_plans()
            for table in ("images", "objects", "coordinates"):
                self.assertEqual(db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 2)

    def test_failed_vacuum_keeps_foreign_keys_enabled(self):
        with DatabaseManager(str(self.directory / "test.db")) as db:
            db.conn.execute("BEGIN")
            with self.assertRaises(sqlite3.OperationalError):
                db.vacuum()
            db.conn.rollback()
            self.assertEqual(db.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                add_object(db, 999)

    def test_legacy_placeholder_is_migrated_once_without_losing_data(self):
        path = self.directory / "legacy.db"
        conn = sqlite3.connect(str(path))
        conn.executescript(CREATE_TABLES_SQL)
        conn.executemany(
            "INSERT INTO images (file_name, image_data, scale) VALUES (?, ?, ?)",
            [("old.jpg", b"old image", 1.0), ("known.jpg", b"known image", 0.25)]
        )
        conn.execute("INSERT INTO objects (image_id, name, object_type) VALUES (1, 'Object', 'point')")
        conn.execute("INSERT INTO coordinates (object_id, x, y, order_index) VALUES (1, 10, 20, 0)")
        conn.commit()
        conn.close()
        with DatabaseManager(str(path)) as db:
            self.assertIsNone(db.images.get_scale(1))
            self.assertEqual(db.images.get_scale(2), 0.25)
            self.assertEqual(db.images.get_image_data(1), b"old image")
            self.assertIsNotNone(db.objects.get_by_id(1))
            self.assertEqual(len(db.coordinates.get_by_object_id(1)), 1)
            db.images.set_scale(1, 1.0)
        with DatabaseManager(str(path)) as db:
            self.assertEqual(db.images.get_scale(1), 1.0)

    def test_scale_update_preserves_image_objects_and_coordinate_ids(self):
        path = self.directory / "test.db"
        with DatabaseManager(str(path)) as db:
            image_id = add_plan(db, b"original image")
            object_id = add_object(db, image_id)
            coords_before = db.conn.execute("SELECT * FROM coordinates").fetchall()
            db.images.set_scale(image_id, 0.125)
            self.assertEqual(db.images.get_scale(image_id), 0.125)
            self.assertEqual(db.images.get_image_data(image_id), b"original image")
            self.assertEqual(db.objects.get_by_image_id(image_id)[0].id, object_id)
            self.assertEqual(db.conn.execute("SELECT * FROM coordinates").fetchall(), coords_before)

    def test_invalid_scales_do_not_replace_a_saved_value(self):
        with DatabaseManager(str(self.directory / "test.db")) as db:
            image_id = add_plan(db)
            db.images.set_scale(image_id, 0.25)
            for scale in (0, -1, float("nan"), float("inf")):
                with self.subTest(scale=scale), self.assertRaises(ValueError):
                    db.images.set_scale(image_id, scale)
                self.assertEqual(db.images.get_scale(image_id), 0.25)
            with self.assertRaisesRegex(ValueError, "не найден"):
                db.images.set_scale(999, 0.5)


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / "test.db"
        with patch("service.database_handler.get_database_path", return_value=self.path):
            self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.image_path = self.directory / "plan.jpg"
        image = QImage(80, 60, QImage.Format_RGB32)
        image.fill(QColor("white"))
        self.assertTrue(image.save(str(self.image_path), "JPG"))

    def import_plan(self):
        with patch("main.QFileDialog.getOpenFileName", return_value=(str(self.image_path), "")):
            self.window.add_plan()
        self.assertIsNotNone(self.window.current_image_id)
        return self.window.current_image_id

    def measure_scale(self, real_distance, accepted=True, same_point=False):
        self.window.view.scale_mode = True
        self.window.view.scale_points = [QPointF(10, 10), QPointF(10 if same_point else 110, 10)]
        with patch("main.QInputDialog.getDouble", return_value=(real_distance, accepted)) as dialog:
            self.window.view._finish_scale_measurement()
        return dialog

    def test_startup_connects_and_database_menu_has_no_file_picker(self):
        self.assertEqual(self.window.db_handler.current_db_path, str(self.path))
        menus = self.window.findChildren(QMenu)
        database_menu = next(menu for menu in menus if menu.title() == "База данных")
        self.assertEqual(
            [action.text() for action in database_menu.actions()],
            ["Очистить все ген.планы", "Оптимизировать (VACUUM)"]
        )

    def test_new_plan_is_active_and_objects_are_saved_to_it(self):
        first_id = self.import_plan()
        self.window.object_manager.start_drawing_object(ObjectType.POINT)
        with patch("service.object_manager.QInputDialog.getText", return_value=("New object", True)):
            self.window.object_manager.handle_mouse_click(QPointF(10, 20))
        with DatabaseManager(str(self.path)) as db:
            self.assertEqual(len(db.objects.get_by_image_id(first_id)), 1)
        self.assertEqual(self.window.object_table.rowCount(), 1)
        self.window.scale_for_plan = 0.5
        second_id = self.import_plan()
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(self.window.object_table.rowCount(), 0)
        self.assertEqual(self.window.object_items, {})
        self.assertIsNone(self.window.scale_for_plan)
        with DatabaseManager(str(self.path)) as db:
            self.assertEqual(len(db.objects.get_by_image_id(first_id)), 1)

    def test_clear_cancel_keeps_active_plan_and_database(self):
        image_id = self.import_plan()
        with patch("main.QMessageBox.question", return_value=QMessageBox.No):
            self.assertFalse(self.window._clear_all_plans())
        self.assertEqual(self.window.current_image_id, image_id)
        self.assertTrue(self.window.is_plan_loaded())
        with DatabaseManager(str(self.path)) as db:
            self.assertIsNotNone(db.images.get_by_id(image_id))

    def test_clear_resets_tools_and_automatically_compacts_database(self):
        image_id = self.import_plan()
        with DatabaseManager(str(self.path)) as db:
            add_object(db, image_id)
            add_plan(db, b"x" * (1024 * 1024))
        self.window.load_objects_from_image(image_id)
        self.window.scale_for_plan = 0.5
        self.window.object_manager.start_drawing_object(ObjectType.LINEAR)
        self.window.object_manager.handle_mouse_click(QPointF(10, 20))
        self.window.measurement_tools.start_length_measurement()
        self.window.measurement_tools.handle_mouse_click(QPointF(20, 30))
        self.window.view.scale_mode = True
        self.window.view.scale_points = [QPointF(5, 5)]
        size_before = self.path.stat().st_size
        with patch("main.QMessageBox.question", return_value=QMessageBox.Yes):
            self.assertTrue(self.window._clear_all_plans())
        self.assertIsNone(self.window.current_image_id)
        self.assertIsNone(self.window.scale_for_plan)
        self.assertEqual(self.window.scene.items(), [])
        self.assertEqual(self.window.object_table.rowCount(), 0)
        self.assertFalse(self.window.object_manager.is_drawing)
        self.assertFalse(self.window.measurement_tools.is_measuring)
        self.assertFalse(self.window.view.scale_mode)
        self.assertEqual(self.window.view.scale_points, [])
        self.assertLess(self.path.stat().st_size, size_before)
        with DatabaseManager(str(self.path)) as db:
            for table in ("images", "objects", "coordinates"):
                self.assertEqual(db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.import_plan()

    def test_vacuum_failure_reports_deleted_plans_and_resets_view(self):
        self.import_plan()
        with patch("main.QMessageBox.question", return_value=QMessageBox.Yes), \
                patch.object(DatabaseManager, "vacuum", side_effect=sqlite3.OperationalError("locked")), \
                patch("main.QMessageBox.warning") as warning:
            self.assertFalse(self.window._clear_all_plans())
        self.assertIn("Ген.планы удалены", warning.call_args.args[2])
        self.assertIsNone(self.window.current_image_id)
        self.assertEqual(self.window.scene.items(), [])
        with DatabaseManager(str(self.path)) as db:
            self.assertEqual(db.images.get_all(), [])

    def test_invalid_image_is_not_added_and_keeps_existing_plan(self):
        image_id = self.import_plan()
        self.image_path.write_bytes(b"invalid image")
        with patch("main.QFileDialog.getOpenFileName", return_value=(str(self.image_path), "")):
            self.window.add_plan()
        self.assertEqual(self.window.current_image_id, image_id)
        with DatabaseManager(str(self.path)) as db:
            self.assertEqual(len(db.images.get_all()), 1)

    def test_new_plan_starts_without_a_measured_scale(self):
        image_id = self.import_plan()
        self.assertIsNone(self.window.scale_for_plan)
        with DatabaseManager(str(self.path)) as db:
            self.assertIsNone(db.images.get_scale(image_id))

    def test_measured_scale_is_saved_and_restored_for_each_plan(self):
        first_id = self.import_plan()
        self.measure_scale(25)
        self.assertEqual(self.window.scale_for_plan, 0.25)
        second_id = self.import_plan()
        self.assertIsNone(self.window.scale_for_plan)
        self.measure_scale(10)
        self.assertEqual(self.window.scale_for_plan, 0.1)
        self.assertTrue(self.window.load_plan(first_id))
        self.assertEqual(self.window.scale_for_plan, 0.25)
        self.assertTrue(self.window.load_plan(second_id))
        self.assertEqual(self.window.scale_for_plan, 0.1)
        with DatabaseManager(str(self.path)) as db:
            self.assertEqual(db.images.get_scale(first_id), 0.25)
            self.assertEqual(db.images.get_scale(second_id), 0.1)

    def test_scale_is_restored_after_application_restart(self):
        image_id = self.import_plan()
        self.measure_scale(25)
        self.window.close()
        with patch("service.database_handler.get_database_path", return_value=self.path):
            reopened = MainWindow()
        self.addCleanup(reopened.close)
        self.assertTrue(reopened.load_plan(image_id))
        self.assertEqual(reopened.scale_for_plan, 0.25)

    def test_an_actual_scale_of_one_is_saved_and_restored(self):
        image_id = self.import_plan()
        self.measure_scale(100)
        self.assertEqual(self.window.scale_for_plan, 1.0)
        self.import_plan()
        self.assertTrue(self.window.load_plan(image_id))
        self.assertEqual(self.window.scale_for_plan, 1.0)

    def test_canceled_scale_measurement_keeps_the_previous_value(self):
        image_id = self.import_plan()
        self.measure_scale(25)
        self.measure_scale(50, accepted=False)
        self.assertEqual(self.window.scale_for_plan, 0.25)
        self.assertFalse(self.window.view.scale_mode)
        self.assertEqual(self.window.view.scale_points, [])
        with DatabaseManager(str(self.path)) as db:
            self.assertEqual(db.images.get_scale(image_id), 0.25)

    def test_coincident_measurement_points_do_not_change_scale(self):
        image_id = self.import_plan()
        self.measure_scale(25)
        dialog = self.measure_scale(50, same_point=True)
        dialog.assert_not_called()
        self.assertEqual(self.window.scale_for_plan, 0.25)
        self.assertFalse(self.window.view.scale_mode)
        with DatabaseManager(str(self.path)) as db:
            self.assertEqual(db.images.get_scale(image_id), 0.25)

    def test_failed_scale_write_keeps_previous_scale_in_view_and_database(self):
        image_id = self.import_plan()
        self.measure_scale(25)
        with DatabaseManager(str(self.path)) as db:
            db.conn.execute("""
                CREATE TRIGGER prevent_scale_change BEFORE UPDATE OF scale ON images
                BEGIN SELECT RAISE(ABORT, 'blocked'); END
            """)
            db.conn.commit()
        with patch("main.QMessageBox.warning") as warning:
            self.measure_scale(50)
        warning.assert_called_once()
        self.assertEqual(self.window.scale_for_plan, 0.25)
        with DatabaseManager(str(self.path)) as db:
            self.assertEqual(db.images.get_scale(image_id), 0.25)

    def test_clearing_the_drawing_preserves_saved_scale(self):
        image_id = self.import_plan()
        self.measure_scale(25)
        self.assertTrue(self.window.clear_plan())
        self.assertEqual(self.window.scale_for_plan, 0.25)
        self.assertTrue(self.window.load_plan(image_id))
        self.assertEqual(self.window.scale_for_plan, 0.25)


if __name__ == "__main__":
    unittest.main()
