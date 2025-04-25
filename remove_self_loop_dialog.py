# remove_self_loop_dialog.py
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout,
    QLabel, QComboBox, QDialogButtonBox
)


class RemoveSelfLoopDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("清除自循环片段")
        self.setMinimumWidth(300)

        layout = QVBoxLayout()
        form = QFormLayout()

        self.cbo_strategy = QComboBox()
        self.cbo_strategy.addItems(["保留首次", "保留最后"])
        form.addRow("保留策略：", self.cbo_strategy)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def get_strategy(self):
        return "first" if self.cbo_strategy.currentText() == "保留首次" else "last"
