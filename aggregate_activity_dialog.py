from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QComboBox, QListWidget,
    QListWidgetItem, QLineEdit, QDialogButtonBox
)
from PyQt5.QtCore import Qt

class AggregateActivityDialog(QDialog):
    def __init__(self, activities, fields, parent=None):
        super().__init__(parent)
        self.setWindowTitle("活动聚合设置")
        self.setMinimumWidth(400)

        self.selected_activity = None
        self.strategy = "first"
        self.selected_fields = []
        self.new_col_name = ""

        layout = QVBoxLayout()
        form = QFormLayout()

        # 活动选择（单选）
        self.combo_activity = QComboBox()
        self.combo_activity.addItems(activities)
        form.addRow("目标活动：", self.combo_activity)

        # 策略选择
        self.combo_strategy = QComboBox()
        self.combo_strategy.addItems(["保留首次", "保留最后"])
        form.addRow("保留策略：", self.combo_strategy)

        # 聚合字段（多选）
        self.field_list = QListWidget()
        self.field_list.setSelectionMode(QListWidget.MultiSelection)
        for f in fields:
            item = QListWidgetItem(f)
            self.field_list.addItem(item)
        form.addRow("聚合字段（多选）：", self.field_list)

        # 新列名（可选）
        self.new_col_edit = QLineEdit()
        self.new_col_edit.setPlaceholderText("可选：新增列名")
        form.addRow("新增列名：", self.new_col_edit)

        layout.addLayout(form)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def get_values(self):
        self.selected_activity = self.combo_activity.currentText()
        self.strategy = "first" if self.combo_strategy.currentText() == "保留首次" else "last"
        self.selected_fields = [item.text() for item in self.field_list.selectedItems()]
        self.new_col_name = self.new_col_edit.text().strip()
        return self.selected_activity, self.strategy, self.selected_fields, self.new_col_name
