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

    def delete_selected_object(self):
        """Удаляет выбранный объект из таблицы и базы данных"""

        # Получаем ID выбранного объекта
        object_id = self.get_selected_object_id()
        if object_id is None:
            self.main_window.statusBar().showMessage(
                "Объект для удаления не выбран",
                3000
            )
            return

        # Запрашиваем подтверждение удаления
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
            # Удаляем объект из базы данных
            with DatabaseManager(self.main_window.db_handler.current_db_path) as db:
                db.objects.delete(object_id)

            # Удаляем объект из графической сцены
            if object_id in self.main_window.object_items:
                self.main_window.object_items[object_id].cleanup()
                del self.main_window.object_items[object_id]

            # Удаляем строку из таблицы
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

        # Заполняем ячейки данными объекта
        self.setItem(row, 0, QTableWidgetItem(str(obj.id or '')))
        self.setItem(row, 1, QTableWidgetItem(obj.name))
        self.setItem(row, 2, QTableWidgetItem(obj.object_type.value))
        self.setItem(row, 3, QTableWidgetItem(str(obj.R1)))
        self.setItem(row, 4, QTableWidgetItem(str(obj.R2)))
        self.setItem(row, 5, QTableWidgetItem(str(obj.R3)))
        self.setItem(row, 6, QTableWidgetItem(str(obj.R4)))
        self.setItem(row, 7, QTableWidgetItem(str(obj.R5)))
        self.setItem(row, 8, QTableWidgetItem(str(obj.R6)))

        # Формируем строку координат
        coords_str = '; '.join([f"({c.x:.1f}, {c.y:.1f})" for c in obj.coordinates])
        self.setItem(row, 9, QTableWidgetItem(coords_str))

    def clear_table(self):
        """Очищает таблицу"""
        self.setRowCount(0)

    def show_context_menu(self, position):
        menu = QMenu()
        edit_coordinates_action = menu.addAction("Редактировать координаты")
        delete_action = menu.addAction("Удалить")  # Добавляем новый пункт меню

        action = menu.exec_(self.mapToGlobal(position))

        if action == edit_coordinates_action:
            object_id = self.get_selected_object_id()
            if object_id is not None and isinstance(self.main_window, QMainWindow):
                self.main_window.start_edit_coordinates(object_id)
        elif action == delete_action:  # Обработка нового действия
            self.delete_selected_object()

    def get_selected_object_id(self):
        """Возвращает ID выбранного объекта"""
        current_row = self.currentRow()
        if current_row >= 0:
            id_item = self.item(current_row, 0)
            if id_item and id_item.text():
                return int(id_item.text())
        return None