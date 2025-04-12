from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QComboBox,
    QDialogButtonBox, QLineEdit, QCheckBox, QHBoxLayout, QMessageBox
)
from PyQt5.QtCore import Qt


class MergeActivityDialog(QDialog):
    def __init__(self, parent, activity_list, field_list):
        super().__init__(parent)
        self.setWindowTitle("合并活动设置")

        self.selected_activities = []
        self.keep_strategy = "first"
        self.selected_fields = []
        self.new_activity_name = ""

        layout = QVBoxLayout()

        # 选择要合并的活动（多选）
        layout.addWidget(QLabel("选择要合并的活动："))
        self.activity_list_widget = QListWidget()
        self.activity_list_widget.setSelectionMode(QListWidget.MultiSelection)
        for act in activity_list:
            item = QListWidgetItem(act)
            self.activity_list_widget.addItem(item)
        layout.addWidget(self.activity_list_widget)

        # 合并后活动名称
        layout.addWidget(QLabel("合并后活动名称："))
        self.new_name_input = QLineEdit()
        layout.addWidget(self.new_name_input)

        # 设置保留策略
        layout.addWidget(QLabel("时间戳保留策略："))
        self.strategy_box = QComboBox()
        self.strategy_box.addItems(["first", "last", "min", "max"])
        layout.addWidget(self.strategy_box)

        # 选择聚合字段
        layout.addWidget(QLabel("选择要聚合的字段（多选）："))
        self.field_checks = []
        self.fields_layout = QVBoxLayout()
        for field in field_list:
            cb = QCheckBox(field)
            self.field_checks.append(cb)
            self.fields_layout.addWidget(cb)
        layout.addLayout(self.fields_layout)

        # 确认/取消按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def get_values(self):
        self.selected_activities = [
            item.text() for item in self.activity_list_widget.selectedItems()
        ]
        self.new_activity_name = self.new_name_input.text().strip()
        self.keep_strategy = self.strategy_box.currentText()
        self.selected_fields = [
            cb.text() for cb in self.field_checks if cb.isChecked()
        ]
        return self.selected_activities, self.new_activity_name, self.keep_strategy, self.selected_fields
