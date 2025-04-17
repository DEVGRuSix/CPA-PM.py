from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QHBoxLayout, QListWidget,
    QLineEdit, QPushButton, QMessageBox, QAbstractItemView
)


class MergeActivityDialog(QDialog):
    def __init__(self, all_activities, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置活动合并策略")
        self.setMinimumWidth(400)

        self.selected_activities = []
        self.new_activity_name = None

        layout = QVBoxLayout()

        layout.addWidget(QLabel("选择要合并的活动（可多选）:"))
        self.list_widget = QListWidget()
        self.list_widget.addItems(sorted(all_activities))
        self.list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        layout.addWidget(self.list_widget)

        layout.addWidget(QLabel("合并后的活动名称："))
        self.name_input = QLineEdit()
        layout.addWidget(self.name_input)

        btn_layout = QHBoxLayout()
        self.btn_ok = QPushButton("确认合并")
        self.btn_cancel = QPushButton("取消")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def get_result(self):
        selected = [item.text() for item in self.list_widget.selectedItems()]
        name = self.name_input.text().strip()
        return selected, name

    def accept(self):
        selected, name = self.get_result()
        if len(selected) < 2:
            QMessageBox.warning(self, "警告", "至少选择两个活动进行合并。")
            return
        if not name:
            QMessageBox.warning(self, "警告", "请输入合并后的活动名称。")
            return
        self.selected_activities = selected
        self.new_activity_name = name
        super().accept()
