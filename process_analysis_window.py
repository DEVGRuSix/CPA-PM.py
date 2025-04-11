# process_analysis_window.py
import sys
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QSplitter, QLabel, QSpinBox, QMessageBox, QSlider,
    QGroupBox, QTableWidget, QTableWidgetItem, QListWidget
)
from PyQt5.QtCore import Qt
from process_graph_view import ProcessGraphView
from pm4py.objects.conversion.log import converter as log_converter


class ProcessAnalysisWindow(QMainWindow):
    def __init__(self, event_log, parent=None):
        super().__init__(parent)
        self.setWindowTitle("流程图分析与交互控制")
        self.setGeometry(200, 100, 1200, 700)

        # 原始日志
        self.original_log = event_log
        # 当前日志 - 必须初始化
        self.current_log = event_log

        # 日志历史栈（用于撤销上一操作）
        self.log_history = []

        # 活动合并操作列表
        self.merge_operations = []

        # 顶部数据集展示区（可折叠）
        self.dataset_group = QGroupBox("▼ 数据集")
        self.dataset_group.setCheckable(True)
        self.dataset_group.setChecked(True)
        self.dataset_group.clicked.connect(self.toggle_dataset_visibility)

        self.dataset_table = QTableWidget()
        self.dataset_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.dataset_table.setColumnCount(0)
        self.dataset_table.setRowCount(0)
        self.dataset_table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.dataset_table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.dataset_table.verticalScrollBar().valueChanged.connect(self.load_more_rows)

        dataset_layout = QVBoxLayout()
        dataset_layout.addWidget(self.dataset_table)
        self.dataset_group.setLayout(dataset_layout)

        self.visible_rows = 20  # 当前展示的行数

        # 用垂直splitter分割“数据集面板”与“流程图+右侧控制面板”
        splitter_main = QSplitter(Qt.Vertical)
        self.setCentralWidget(splitter_main)

        # 将顶部的“数据集”面板放入 splitter_main
        splitter_main.addWidget(self.dataset_group)

        # 再创建一个水平splitter，用来分割左侧流程图与右侧控制区
        splitter_h = QSplitter(Qt.Horizontal)
        splitter_main.addWidget(splitter_h)

        splitter_main.setSizes([200, 500])  # 初始高度可自行调节

        # 左侧流程图
        self.graph_view = ProcessGraphView()
        self.graph_view.draw_from_event_log(self.current_log)
        splitter_h.addWidget(self.graph_view)

        # 右侧控制面板
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)

        # 按钮：保留首次活动
        btn_cpa_first_only = QPushButton("CPA：保留首次活动")
        btn_cpa_first_only.clicked.connect(self.cpa_keep_first)
        control_layout.addWidget(btn_cpa_first_only)

        # 标签+SpinBox：过滤低频活动
        lbl_freq = QLabel("过滤低频活动（最小出现次数）：")
        self.freq_spin = QSpinBox()
        self.freq_spin.setMinimum(1)
        self.freq_spin.setMaximum(999)
        self.freq_spin.setValue(2)
        btn_filter_freq = QPushButton("应用频次过滤")
        btn_filter_freq.clicked.connect(self.filter_by_frequency)

        control_layout.addWidget(lbl_freq)
        control_layout.addWidget(self.freq_spin)
        control_layout.addWidget(btn_filter_freq)

        # 重置日志
        btn_reset = QPushButton("重置为原始日志")
        btn_reset.clicked.connect(self.reset_log)
        control_layout.addWidget(btn_reset)

        # 撤销上一操作
        btn_undo_last = QPushButton("撤销上一步修改")
        btn_undo_last.clicked.connect(self.undo_last_change)
        control_layout.addWidget(btn_undo_last)

        # 配置活动合并/保留策略
        btn_merge_keep_config = QPushButton("设置活动合并/保留策略")
        btn_merge_keep_config.clicked.connect(self.open_merge_keep_dialog)
        control_layout.addWidget(btn_merge_keep_config)

        # 操作记录区域标题
        self.label_merge_ops = QLabel("已设置的合并/保留策略：")
        self.label_merge_ops.setStyleSheet("font-weight: bold; margin-top: 10px;")
        control_layout.addWidget(self.label_merge_ops)

        # merge_ops_list容器
        self.merge_ops_list = QWidget()
        self.merge_ops_layout = QVBoxLayout()
        self.merge_ops_layout.setContentsMargins(0, 0, 0, 0)
        self.merge_ops_list.setLayout(self.merge_ops_layout)
        control_layout.addWidget(self.merge_ops_list)

        # 下方：可排序列表 + 删除按钮
        self.activity_ops = []
        self.activity_ops_list = QListWidget()
        self.activity_ops_list.setDragDropMode(QListWidget.InternalMove)
        # 注意：.itemChanged.connect(...) 如果不是 "信号 -> 槽" 就需要用 lambda
        # 但这里你写成了 .itemChanged.connect(self.refresh_log_after_merge_ops()) => 这会立即调用而不是监听
        # 如果要在列表项目变化后动态更新，需要写成:
        # self.activity_ops_list.itemChanged.connect(self.refresh_log_after_merge_ops)
        # 这里先注释掉，以免造成死循环
        # self.activity_ops_list.itemChanged.connect(self.refresh_log_after_merge_ops)

        btn_remove_selected_op = QPushButton("删除选中操作")
        btn_remove_selected_op.clicked.connect(self.remove_selected_activity_op)

        control_layout.addWidget(QLabel("已定义的活动处理操作（可排序）:"))
        control_layout.addWidget(self.activity_ops_list)
        control_layout.addWidget(btn_remove_selected_op)

        # 活动节点显示比例
        self.label_act_slider = QLabel("活动节点显示比例：")
        self.slider_act = QSlider(Qt.Horizontal)
        self.slider_act.setMinimum(1)
        self.slider_act.setMaximum(100)
        self.slider_act.setValue(100)
        self.slider_act.valueChanged.connect(self.update_graph_with_filter)

        # 路径边显示比例
        self.label_edge_slider = QLabel("路径边显示比例：")
        self.slider_edge = QSlider(Qt.Horizontal)
        self.slider_edge.setMinimum(1)
        self.slider_edge.setMaximum(100)
        self.slider_edge.setValue(100)
        self.slider_edge.valueChanged.connect(self.update_graph_with_filter)

        control_layout.addWidget(self.label_act_slider)
        control_layout.addWidget(self.slider_act)
        control_layout.addWidget(self.label_edge_slider)
        control_layout.addWidget(self.slider_edge)

        control_layout.addStretch()
        splitter_h.addWidget(control_panel)
        splitter_h.setSizes([800, 300])

        # 让窗口初始化时直接展示数据
        self.update_dataset_preview()


    def filter_by_frequency(self):
        """
        根据活动出现的总频次进行过滤。
        若有活动 < 阈值，则丢弃包含该活动的整条Trace。
        """
        threshold = self.freq_spin.value()
        try:
            if self.current_log is None:
                QMessageBox.critical(self, "错误", "当前日志为空，无法进行过滤。")
                return

            from collections import Counter
            act_counter = Counter()
            for trace in self.current_log:
                for event in trace:
                    act_counter[event.get("concept:name", "undefined")] += 1

            low_freq_acts = {act for act, freq in act_counter.items() if freq < threshold}
            filtered_log = []
            for trace in self.current_log:
                # 如果trace里出现了低频活动，则整条丢弃
                if any(event.get("concept:name") in low_freq_acts for event in trace):
                    continue
                filtered_log.append(trace)

            if not filtered_log:
                QMessageBox.warning(self, "无数据", "过滤后没有剩余日志。请降低阈值。")
                return

            # 操作前将当前日志压栈，以便“撤销”
            self.log_history.append(self.current_log)
            # 更新 current_log
            self.current_log = filtered_log

            self.update_graph_with_filter()

        except Exception as e:
            QMessageBox.critical(self, "过滤失败", str(e))

        self.update_dataset_preview()

    def reset_log(self):
        """
        恢复到最初的原始日志（放弃所有操作）
        """
        # 将 current_log 还原成 original_log
        self.current_log = self.original_log
        # 清空操作列表（如你希望保留操作列表，可移除这行）
        self.merge_operations.clear()
        # 清空历史栈
        self.log_history.clear()

        self.update_graph_with_filter()
        self.update_dataset_preview()

    def undo_last_change(self):
        """
        撤销上一次对 current_log 的修改，回到修改前的状态
        """
        if self.log_history:
            self.current_log = self.log_history.pop()
            self.update_graph_with_filter()
        else:
            QMessageBox.information(self, "提示", "没有可以撤销的操作。")

        self.update_dataset_preview()

    def update_graph_with_filter(self):
        """
        根据滑条设定的显示比例，重新绘制。
        """
        if self.current_log is None:
            QMessageBox.critical(self, "错误", "当前日志为空，无法绘制流程图。")
            return

        act_percent = self.slider_act.value()
        edge_percent = self.slider_edge.value()
        self.graph_view.draw_from_event_log(self.current_log, act_percent=act_percent, edge_percent=edge_percent)

    def cpa_keep_first(self):
        """
        保留每条 trace 中每种活动的首次出现
        """
        if self.current_log is None:
            QMessageBox.warning(self, "无数据", "当前日志为空，无法保留首次出现。")
            return

        try:
            from cpa_utils import keep_first_occurrence_only
            self.log_history.append(self.current_log)

            new_log = keep_first_occurrence_only(self.current_log)
            if not new_log:
                QMessageBox.warning(self, "无数据", "执行后日志为空。")
                self.log_history.pop()
                return

            self.current_log = new_log
            self.update_graph_with_filter()
            QMessageBox.information(self, "完成", "已保留每条trace的首次活动事件。")
        except Exception as e:
            if self.log_history:
                self.log_history.pop()
            QMessageBox.critical(self, "出错", str(e))

        self.update_dataset_preview()

    def update_dataset_preview(self):
        """
        将 current_log 转为 DataFrame 并显示前 visible_rows 行
        """
        try:
            if self.current_log is None:
                QMessageBox.critical(self, "错误", "当前日志为空，无法展示数据。")
                return

            df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
            if not isinstance(df, pd.DataFrame) or df.empty:
                self.dataset_table.clear()
                return

            self._dataset_df = df.reset_index(drop=True)
            self.visible_rows = 20
            self._refresh_dataset_table()

        except Exception as e:
            print("无法更新数据集展示：", e)

    def _refresh_dataset_table(self):
        df = getattr(self, "_dataset_df", None)
        if df is None or df.empty:
            self.dataset_table.clear()
            return

        nrows = min(self.visible_rows, len(df))
        self.dataset_table.setRowCount(nrows)
        self.dataset_table.setColumnCount(len(df.columns))
        self.dataset_table.setHorizontalHeaderLabels(df.columns.tolist())

        for r in range(nrows):
            for c in range(len(df.columns)):
                val = str(df.iloc[r, c])
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.dataset_table.setItem(r, c, item)

    def load_more_rows(self):
        """滚动到底时动态加载更多行"""
        scroll_bar = self.dataset_table.verticalScrollBar()
        if scroll_bar.value() == scroll_bar.maximum():
            if hasattr(self, "_dataset_df") and self._dataset_df is not None:
                if self.visible_rows < len(self._dataset_df):
                    self.visible_rows += 20
                    self._refresh_dataset_table()

    def toggle_dataset_visibility(self):
        """展开/收起数据集展示"""
        expanded = self.dataset_group.isChecked()
        self.dataset_table.setVisible(expanded)
        self.dataset_group.setTitle("▼ 数据集" if expanded else "▶ 数据集")

    def open_merge_keep_dialog(self):
        from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QComboBox, QLineEdit, QFormLayout

        if self.current_log is None:
            QMessageBox.warning(self, "数据为空", "当前日志为空，无法配置。")
            return

        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        if df.empty:
            QMessageBox.warning(self, "数据为空", "当前日志为空，无法配置。")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("合并/保留活动设置")

        layout = QFormLayout()
        act_list = sorted(df["concept:name"].unique())
        combo_activity = QComboBox()
        combo_activity.addItems(act_list)

        combo_strategy = QComboBox()
        combo_strategy.addItems(["保留首次", "保留最后", "合并全部"])

        agg_input = QLineEdit()
        agg_input.setPlaceholderText("聚合字段，如 org:resource,other:info")

        newcol_input = QLineEdit()
        newcol_input.setPlaceholderText("新列名（可选）")

        layout.addRow("目标活动：", combo_activity)
        layout.addRow("策略：", combo_strategy)
        layout.addRow("聚合字段（逗号分隔）：", agg_input)
        layout.addRow("新增列名（可选）：", newcol_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addRow(buttons)
        dialog.setLayout(layout)

        def accept():
            act = combo_activity.currentText()
            strat = combo_strategy.currentText()
            aggs = [x.strip() for x in agg_input.text().split(",") if x.strip()]
            newcol = newcol_input.text().strip()
            self.add_merge_operation(act, strat, aggs, newcol)
            dialog.accept()

        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        dialog.exec_()

    def add_merge_operation(self, activity, strategy, agg_columns, new_colname):
        """
        新增一条合并操作记录
        """
        from functools import partial
        op = {
            "activity": activity,
            "strategy": strategy,
            "agg_cols": agg_columns,
            "new_col": new_colname
        }

        self.merge_operations.append(op)

        row_widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        desc = f"{strategy}：{activity}"
        if strategy == "合并全部":
            desc += f"（聚合字段：{','.join(agg_columns)}"
            if new_colname:
                desc += f"，新列名：{new_colname}"
            desc += "）"

        label = QLabel(desc)
        btn_del = QPushButton("删除")
        btn_up = QPushButton("↑")
        btn_down = QPushButton("↓")

        idx = len(self.merge_operations) - 1
        btn_del.clicked.connect(partial(self.remove_merge_operation, idx))
        btn_up.clicked.connect(partial(self.move_merge_operation, idx, -1))
        btn_down.clicked.connect(partial(self.move_merge_operation, idx, 1))

        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(btn_up)
        layout.addWidget(btn_down)
        layout.addWidget(btn_del)
        row_widget.setLayout(layout)
        self.merge_ops_layout.addWidget(row_widget)

        self.refresh_log_after_merge_ops()

    def remove_merge_operation(self, idx):
        """
        从列表中删除某条操作
        """
        if idx < 0 or idx >= len(self.merge_operations):
            return
        # 从操作列表中移除
        self.merge_operations.pop(idx)

        # 重建UI
        self.rebuild_merge_ops_ui()
        self.refresh_log_after_merge_ops()

    def move_merge_operation(self, idx, direction):
        """
        上移/下移操作顺序
        """
        new_idx = idx + direction
        if 0 <= idx < len(self.merge_operations) and 0 <= new_idx < len(self.merge_operations):
            self.merge_operations[idx], self.merge_operations[new_idx] = \
                self.merge_operations[new_idx], self.merge_operations[idx]
            self.rebuild_merge_ops_ui()
            self.refresh_log_after_merge_ops()

    def rebuild_merge_ops_ui(self):
        # 清空布局
        while self.merge_ops_layout.count():
            w = self.merge_ops_layout.takeAt(0).widget()
            if w: w.deleteLater()

        # 重新添加所有操作
        for op in self.merge_operations:
            self.add_merge_operation(op["activity"], op["strategy"], op["agg_cols"], op["new_col"])

    def refresh_log_after_merge_ops(self):
        """
        根据 self.merge_operations 从 self.original_log 重新生成 current_log
        并刷新流程图 & 数据
        """
        if self.original_log is None:
            QMessageBox.critical(self, "错误", "原始日志为空，无法重新应用操作。")
            return
        if not self.merge_operations:
            # 如果没有操作，直接把 current_log 设为 original_log
            self.current_log = self.original_log
            self.update_graph_with_filter()
            self.update_dataset_preview()
            return

        try:
            from cpa_utils import apply_merge_operations

            # 历史记录
            self.log_history.append(self.current_log)
            # 应用操作
            self.current_log = apply_merge_operations(self.original_log, self.merge_operations)

            if self.current_log is None:
                QMessageBox.critical(self, "错误", "合并操作返回空日志，请检查配置。")
                return

            self.update_graph_with_filter()
            self.update_dataset_preview()

        except Exception as e:
            QMessageBox.critical(self, "执行失败", str(e))


    def remove_selected_activity_op(self):
        # 这里如需实现删除选中项，需要我们知道列表控件的行
        row_idx = self.activity_ops_list.currentRow()
        if row_idx < 0 or row_idx >= len(self.merge_operations):
            QMessageBox.information(self, "提示", "未选中任何操作。")
            return

        self.merge_operations.pop(row_idx)
        self.rebuild_merge_ops_ui()
        self.refresh_log_after_merge_ops()


def launch_analysis_window(event_log):
    """
    供外部程序调用入口
    """
    global _analysis_window
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    _analysis_window = ProcessAnalysisWindow(event_log)
    _analysis_window.show()
