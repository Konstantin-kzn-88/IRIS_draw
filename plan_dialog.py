# plan_dialog.py
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget,
                               QTableWidgetItem, QPushButton, QHeaderView)
from PySide6.QtCore import Qt
from iris_db.database import DatabaseManager


class SelectPlanDialog(QDialog):
    def __init__(self, db_path, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.selected_plan_id = None
        self.setup_ui()
        self.load_plans()

    def setup_ui(self):
        self.setWindowTitle("Выбор плана")
        self.setModal(True)
        self.resize(600, 400)

        layout = QVBoxLayout(self)

        # Создаем таблицу планов
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "ID", "Название файла", "Дата создания", "Дата обновления"
        ])

        # Настройка размеров колонок
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(0, 50)  # Ширина колонки ID

        # Двойной клик по строке выбирает план
        self.table.cellDoubleClicked.connect(self.accept)

        # Кнопка выбора
        select_button = QPushButton("Выбрать")
        select_button.clicked.connect(self.accept)

        # Кнопка отмены
        cancel_button = QPushButton("Отмена")
        cancel_button.clicked.connect(self.reject)

        # Добавляем виджеты на форму
        layout.addWidget(self.table)
        layout.addWidget(select_button)
        layout.addWidget(cancel_button)

    def load_plans(self):
        """Загружает список планов из базы данных"""
        try:
            with DatabaseManager(self.db_path) as db:
                plans = db.images.get_all()
                self.table.setRowCount(len(plans))

                for row, plan in enumerate(plans):
                    # ID
                    id_item = QTableWidgetItem(str(plan.id))
                    id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row, 0, id_item)

                    # Название файла
                    name_item = QTableWidgetItem(plan.file_name)
                    name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row, 1, name_item)

                    # Дата создания
                    created_item = QTableWidgetItem(plan.created_at.strftime("%Y-%m-%d %H:%M:%S"))
                    created_item.setFlags(created_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row, 2, created_item)

                    # Дата обновления
                    updated_item = QTableWidgetItem(plan.updated_at.strftime("%Y-%m-%d %H:%M:%S"))
                    updated_item.setFlags(updated_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row, 3, updated_item)

        except Exception as e:
            print(f"Ошибка при загрузке планов: {e}")

    def get_selected_plan_id(self):
        """Возвращает ID выбранного плана"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            return int(self.table.item(current_row, 0).text())
        return None