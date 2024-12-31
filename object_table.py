# object_table.py
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt
from iris_db.models import Object, ObjectType


class ObjectTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_table()

        # Enable single row selection
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

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

    def remove_selected_object(self):
        """Удаляет выбранный объект из таблицы"""
        current_row = self.currentRow()
        if current_row >= 0:
            self.removeRow(current_row)

    def get_selected_object_id(self):
        """Возвращает ID выбранного объекта"""
        current_row = self.currentRow()
        if current_row >= 0:
            id_item = self.item(current_row, 0)
            if id_item and id_item.text():
                return int(id_item.text())
        return None