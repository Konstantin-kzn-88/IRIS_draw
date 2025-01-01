# object_table.py
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QMenu, QMainWindow
from PySide6.QtCore import Qt

from iris_db.database import DatabaseManager
from iris_db.models import Object, ObjectType
from PySide6.QtWidgets import QMessageBox


class ObjectTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.setup_table()
        # Подключаем обработчик изменения ячеек
        self.itemChanged.connect(self.handle_item_changed)
        # Флаг для предотвращения рекурсивных вызовов при обновлении
        self.is_updating = False

    def handle_item_changed(self, item):
        """Обработка изменения значения в ячейке"""
        if self.is_updating:
            return

        try:
            row = item.row()
            col = item.column()
            new_value = item.text()
            object_id = int(self.item(row, 0).text())

            # Игнорируем изменения в нередактируемых столбцах
            if col in [0, 2, 9]:  # ID, Тип, Координаты
                return

            with DatabaseManager(self.main_window.db_handler.current_db_path) as db:
                obj = db.objects.get_by_id(object_id)
                if not obj:
                    raise ValueError("Объект не найден в базе данных")

                if col == 1:  # Название
                    obj.name = new_value
                elif 3 <= col <= 8:  # R1-R6
                    try:
                        value = float(new_value)
                        if value < 0:
                            raise ValueError("Значение не может быть отрицательным")
                        setattr(obj, f'R{col-2}', value)
                    except ValueError as e:
                        QMessageBox.warning(
                            self,
                            "Ошибка",
                            "Введите корректное числовое значение"
                        )
                        self.is_updating = True
                        item.setText(str(getattr(obj, f'R{col-2}')))
                        self.is_updating = False
                        return

                # Сохраняем изменения в базе данных
                db.objects.update(obj)
                self.main_window.statusBar().showMessage(
                    "Изменения сохранены",
                    3000
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось сохранить изменения: {str(e)}"
            )
            # Отменяем изменение
            self.is_updating = True
            item.setText(str(getattr(obj, f'R{col-2}')))
            self.is_updating = False

    def delete_selected_object(self):
        """Удаляет выбранный объект из таблицы и базы данных"""
        object_id = self.get_selected_object_id()
        if object_id is None:
            self.main_window.statusBar().showMessage(
                "Объект для удаления не выбран",
                3000
            )
            return

        confirmation = QMessageBox.question(
            self,
            "Подтверждение удаления",
            "Вы действительно хотите удалить выбранный объект?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if confirmation == QMessageBox.No:
            return

        try:
            with DatabaseManager(self.main_window.db_handler.current_db_path) as db:
                db.objects.delete(object_id)

            if object_id in self.main_window.object_items:
                self.main_window.object_items[object_id].cleanup()
                del self.main_window.object_items[object_id]

            current_row = self.currentRow()
            self.removeRow(current_row)

            self.main_window.statusBar().showMessage(
                "Объект успешно удален",
                3000
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось удалить объект: {str(e)}"
            )

    def setup_table(self):
        # Установка колонок таблицы
        columns = ['ID', 'Название', 'Тип', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Координаты']
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)

        # Настройка растягивания колонок
        header = self.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Название растягивается
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Тип подстраивается под содержимое

        # Установка минимальной ширины для числовых колонок
        for i in range(3, 9):  # R1-R6
            header.setSectionResizeMode(i, QHeaderView.Fixed)
            self.setColumnWidth(i, 60)

        # Координаты могут быть шире
        header.setSectionResizeMode(9, QHeaderView.ResizeToContents)

    def add_object(self, obj: Object):
        """Добавляет объект в таблицу"""
        row = self.rowCount()
        self.insertRow(row)

        # ID - нередактируемый
        id_item = QTableWidgetItem(str(obj.id or ''))
        id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 0, id_item)

        # Название - редактируемое
        self.setItem(row, 1, QTableWidgetItem(obj.name))

        # Тип - нередактируемый
        type_item = QTableWidgetItem(obj.object_type.value)
        type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 2, type_item)

        # R1-R6 - редактируемые
        self.setItem(row, 3, QTableWidgetItem(str(obj.R1)))
        self.setItem(row, 4, QTableWidgetItem(str(obj.R2)))
        self.setItem(row, 5, QTableWidgetItem(str(obj.R3)))
        self.setItem(row, 6, QTableWidgetItem(str(obj.R4)))
        self.setItem(row, 7, QTableWidgetItem(str(obj.R5)))
        self.setItem(row, 8, QTableWidgetItem(str(obj.R6)))

        # Координаты - нередактируемые
        coords_str = '; '.join([f"({c.x:.1f}, {c.y:.1f})" for c in obj.coordinates])
        coords_item = QTableWidgetItem(coords_str)
        coords_item.setFlags(coords_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 9, coords_item)

    def clear_table(self):
        """Очищает таблицу"""
        self.setRowCount(0)

    def show_context_menu(self, position):
        menu = QMenu()
        edit_coordinates_action = menu.addAction("Редактировать координаты")
        delete_action = menu.addAction("Удалить")

        action = menu.exec_(self.mapToGlobal(position))

        if action == edit_coordinates_action:
            object_id = self.get_selected_object_id()
            if object_id is not None and isinstance(self.main_window, QMainWindow):
                self.main_window.start_edit_coordinates(object_id)
        elif action == delete_action:
            self.delete_selected_object()

    def get_selected_object_id(self):
        """Возвращает ID выбранного объекта"""
        current_row = self.currentRow()
        if current_row >= 0:
            id_item = self.item(current_row, 0)
            if id_item and id_item.text():
                return int(id_item.text())
        return None