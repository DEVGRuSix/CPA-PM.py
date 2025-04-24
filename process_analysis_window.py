# process_analysis_window.py
import os
import sys
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QSplitter, QLabel, QSpinBox, QMessageBox, QSlider,
    QGroupBox, QTableWidget, QTableWidgetItem, QListWidget, QDialog, QListWidgetItem, QFileDialog
)
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDateTimeEdit, QLineEdit, QGroupBox
from PyQt5.QtCore import QDateTime
# 引入预处理函数
from cpa_pm_preprocessing import (
    delete_truncated_traces_start,
    delete_truncated_traces_end,
    delete_traces_with_short_length
)

from process_graph_view import ProcessGraphView
from pm4py.objects.conversion.log import converter as log_converter
from merge_activity_dialog import MergeActivityDialog


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
        self.dataset_group = QGroupBox("数据集 ▼")
        self.dataset_group.setCheckable(True)
        self.dataset_group.setChecked(True)
        self.dataset_group.clicked.connect(self.toggle_dataset_visibility)
        self.dataset_group.setStyleSheet("QGroupBox::indicator { width: 0px; height: 0px; }")

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
        self.splitter_main = QSplitter(Qt.Vertical)
        self.setCentralWidget(self.splitter_main)
        # —— 新增：概况显示（事件数 / 流程数 / 活动数 / 变体数） ——
        self.summary_group = QWidget()
        summary_layout = QHBoxLayout(self.summary_group)
        self.lbl_summary_events = QLabel("事件数: 0")
        self.lbl_summary_traces = QLabel("流程数: 0")
        self.lbl_summary_activities = QLabel("活动数: 0")
        self.lbl_summary_variants = QLabel("变体数: 0")
        for lbl in (
                self.lbl_summary_events,
                self.lbl_summary_traces,
                self.lbl_summary_activities,
                self.lbl_summary_variants
        ):
            summary_layout.addWidget(lbl)
        # 将概况插入 splitter_main 第一行
        self.splitter_main.insertWidget(0, self.summary_group)
        self.summary_group.setFixedHeight(self.summary_group.sizeHint().height())
        # 将顶部的“数据集”面板放入 splitter_main
        self.splitter_main.addWidget(self.dataset_group)

        # 再创建一个水平splitter，用来分割左侧流程图与右侧控制区
        splitter_h = QSplitter(Qt.Horizontal)
        self.splitter_main.addWidget(splitter_h)

        self.splitter_main.setSizes([40, 100, 480])  # 初始高度可自行调节

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

        btn_merge_activity = QPushButton("活动合并")
        btn_merge_activity.clicked.connect(self.open_merge_activity_dialog)
        control_layout.addWidget(btn_merge_activity)

        # 下方：可排序列表 + 删除按钮
        self.activity_ops = []
        self.activity_ops_list = QListWidget()
        self.activity_ops_list.setDragDropMode(QListWidget.InternalMove)

        btn_aggregate_activity = QPushButton("活动聚合")
        btn_aggregate_activity.clicked.connect(self.open_aggregate_activity_dialog)
        control_layout.addWidget(btn_aggregate_activity)

        control_layout.addWidget(QLabel("已定义的活动处理操作（可排序）:"))
        control_layout.addWidget(self.activity_ops_list)

        btns_layout = QHBoxLayout()
        btn_remove_selected_op = QPushButton("删除选中操作")
        btn_remove_selected_op.clicked.connect(self.remove_selected_activity_op)
        btns_layout.addWidget(btn_remove_selected_op)

        btn_undo_last = QPushButton("撤销上一步修改")
        btn_undo_last.clicked.connect(self.undo_last_change)
        btns_layout.addWidget(btn_undo_last)

        btn_container = QWidget()
        btn_container.setLayout(btns_layout)
        control_layout.addWidget(btn_container)

        btn_redo = QPushButton("重做上一步修改")
        btn_redo.clicked.connect(self.redo_last_change)
        btns_layout.addWidget(btn_redo)  # ✅ 放在撤销按钮后面

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

        # —— 新增：高级筛选与操作区 ——
        adv_group = QGroupBox("高级筛选与操作")
        adv_layout = QVBoxLayout()

        # 1) 删除不符合起始/结束事件的案例
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("起始事件:"))
        self.edit_req_start = QLineEdit()
        h1.addWidget(self.edit_req_start)
        btn_req_start = QPushButton("删除起始不符案例")
        btn_req_start.clicked.connect(self.delete_traces_by_start)
        adv_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("结束事件:"))
        self.edit_req_end = QLineEdit()
        h2.addWidget(self.edit_req_end)
        btn_req_end = QPushButton("删除结束不符案例")
        btn_req_end.clicked.connect(self.delete_traces_by_end)
        adv_layout.addLayout(h2)

        # 2) 删除过短案例（按事件数）
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("最小事件数:"))
        self.spin_min_events = QSpinBox()
        self.spin_min_events.setMinimum(1)
        h3.addWidget(self.spin_min_events)
        btn_short = QPushButton("删除过短案例")
        btn_short.clicked.connect(self.delete_short_traces)
        adv_layout.addLayout(h3)

        # 3) 删除短持续案例（按总时长秒）
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("最小持续(秒):"))
        self.spin_min_dur = QSpinBox()
        self.spin_min_dur.setMinimum(0)
        h4.addWidget(self.spin_min_dur)
        btn_dur = QPushButton("删除短持续案例")
        btn_dur.clicked.connect(self.delete_short_duration)
        adv_layout.addLayout(h4)

        # 4) 时间区间筛选
        h5 = QHBoxLayout()
        h5.addWidget(QLabel("开始时间:"))
        self.dt_start = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_start.setCalendarPopup(True)
        h5.addWidget(self.dt_start)
        h5.addWidget(QLabel("结束时间:"))
        self.dt_end = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_end.setCalendarPopup(True)
        h5.addWidget(self.dt_end)
        btn_time = QPushButton("时间区间筛选")
        btn_time.clicked.connect(self.filter_by_time_interval)
        adv_layout.addLayout(h5)

        # 5) 自定义条件
        h6 = QHBoxLayout()
        self.edit_custom = QLineEdit()
        self.edit_custom.setPlaceholderText("如 city=='Ottawa' & `concept:name`=='Start'")
        h6.addWidget(self.edit_custom)
        btn_custom = QPushButton("应用自定义筛选")
        btn_custom.clicked.connect(self.filter_by_custom_condition)
        adv_layout.addLayout(h6)

        # 6) Top-K 活动
        h7 = QHBoxLayout()
        h7.addWidget(QLabel("Top K 活动:"))
        self.spin_topk = QSpinBox()
        self.spin_topk.setMinimum(1)
        self.spin_topk.setValue(5)
        h7.addWidget(self.spin_topk)
        btn_topk = QPushButton("显示TopK")
        btn_topk.clicked.connect(self.show_topk_events)
        adv_layout.addLayout(h7)

        # 7) 导出CSV 按钮
        btn_export_csv = QPushButton("导出CSV")
        btn_export_csv.clicked.connect(self.export_csv)
        adv_layout.addWidget(btn_export_csv)

        adv_group.setLayout(adv_layout)
        control_layout.addWidget(adv_group)

        control_layout.addStretch()
        splitter_h.addWidget(control_panel)
        splitter_h.setSizes([800, 300])

        self.merge_rules = []  # 每条规则是一个 dict
        self.merge_list_panel = QWidget()
        self.merge_list_layout = QVBoxLayout()
        self.merge_list_panel.setLayout(self.merge_list_layout)
        control_layout.addWidget(self.merge_list_panel)



        # 让窗口初始化时直接展示数据
        self.update_dataset_preview()
        # 操作记录堆栈，用于支持撤销功能
        self.activity_ops_history = []
        self.redo_stack = []  # ✅ 初始化重做栈

    def filter_by_frequency(self):
        """
        根据活动出现的总频次进行过滤。
        若有活动 < 阈值，则丢弃包含该活动的整条Trace。
        """
        min_freq = self.freq_spin.value()
        self.redo_stack.clear()  # ✅ 清空 redo 栈，防止误重做

        try:
            if self.current_log is None:
                QMessageBox.critical(self, "错误", "当前日志为空，无法进行过滤。")
                return

            from collections import Counter
            act_counter = Counter()
            for trace in self.current_log:
                for event in trace:
                    act_counter[event.get("concept:name", "undefined")] += 1

            low_freq_acts = {act for act, freq in act_counter.items() if freq < min_freq}
            filtered_log = []
            for trace in self.current_log:
                if any(event.get("concept:name") in low_freq_acts for event in trace):
                    continue
                filtered_log.append(trace)

            if not filtered_log:
                QMessageBox.warning(self, "无数据", "过滤后没有剩余日志。请降低阈值。")
                return

            self.log_history.append(self.current_log)
            self.current_log = filtered_log

            self.update_graph_with_filter()
            self.update_dataset_preview()

            # ✅ 更新操作记录（只执行一次）
            self.activity_ops_history.append(self.activity_ops.copy())
            self.redo_stack.clear()
            self.activity_ops.append({"type": "filter", "threshold": min_freq})
            self.update_activity_ops_list()

        except Exception as e:
            QMessageBox.critical(self, "过滤失败", str(e))

    def reset_log(self):
        self.activity_ops_history.append(self.activity_ops.copy())
        self.redo_stack = []
        self.activity_ops.append({"type": "reset"})
        self.update_activity_ops_list()

        self.reapply_activity_ops()

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

        self.update_summary()

    def undo_last_change(self):
        if self.activity_ops_history:
            self.redo_stack.append(self.activity_ops.copy())  # ✅ 添加当前状态进 redo
            self.activity_ops = self.activity_ops_history.pop()
            self.update_activity_ops_list()
            self.reapply_activity_ops()
        else:
            QMessageBox.information(self, "提示", "没有可以撤销的操作。")

    def cpa_keep_first(self):
        """
        保留每条 trace 中每种活动的首次出现
        """
        if self.current_log is None:
            QMessageBox.warning(self, "无数据", "当前日志为空，无法保留首次出现。")
            return
        self.redo_stack.clear()

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
        self.activity_ops_history.append(self.activity_ops.copy())  # ✅ 添加这一行
        self.activity_ops.append({"type": "aggregate", "activities": ["ALL"], "strategy": "first"})
        self.update_activity_ops_list()

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

        self.update_summary()

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
        self.dataset_table.resizeColumnsToContents()
    def load_more_rows(self):
        """滚动到底时动态加载更多行"""
        scroll_bar = self.dataset_table.verticalScrollBar()
        if scroll_bar.value() == scroll_bar.maximum():
            if hasattr(self, "_dataset_df") and self._dataset_df is not None:
                if self.visible_rows < len(self._dataset_df):
                    self.visible_rows += 20
                    self._refresh_dataset_table()

    def toggle_dataset_visibility(self):
        """展开/收起数据集表格区域，仅隐藏表格，并调整最小高度"""
        expanded = self.dataset_group.isChecked()

        self.dataset_table.setVisible(expanded)  # ✅ 控制表格可见性
        self.dataset_group.setTitle("数据集 ▼" if expanded else "数据集 ▶")

        if not expanded:
            self.dataset_group.setMinimumHeight(30)  # ✅ 收起后最小高度（只显示标题栏）
            self.dataset_group.setMaximumHeight(30)
        else:
            self.dataset_group.setMinimumHeight(100)  # ✅ 展开时允许恢复拖动
            self.dataset_group.setMaximumHeight(16777215)  # 恢复最大高度为默认值

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

            # 构造统一格式的操作记录
            op = {
                "type": "aggregate" if strat in ["保留首次", "保留最后"] else "merge",
                "activities": [act],
                "target": act if strat != "合并全部" else newcol or act,
                "strategy": "first" if strat == "保留首次" else (
                    "last" if strat == "保留最后" else "merge"
                ),
                "fields": aggs,
                "new_col": newcol
            }

            self.activity_ops.append(op)
            self.update_activity_ops_list()
            self.reapply_activity_ops()
            dialog.accept()

    def remove_selected_activity_op(self):
        self.redo_stack.clear()
        row_idx = self.activity_ops_list.currentRow()
        if 0 <= row_idx < len(self.activity_ops):
            self.activity_ops_history.append(self.activity_ops.copy())  # ✅ 添加这一行
            self.activity_ops.pop(row_idx)
            self.update_activity_ops_list()
            self.reapply_activity_ops()

    def open_merge_dialog(self):
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        if df is None or df.empty:
            QMessageBox.warning(self, "数据缺失", "当前数据为空，无法设置活动合并。")
            return

        activity_list = sorted(df["concept:name"].unique())
        field_list = [col for col in df.columns if
                      col not in ["case:concept:name", "concept:name", "time:timestamp", "lifecycle:transition"]]

        dialog = MergeActivityDialog(self, activity_list, field_list)
        if dialog.exec_():
            activities, new_name, strategy, fields = dialog.get_values()

            if not activities or not new_name:
                QMessageBox.warning(self, "输入不完整", "请至少选择活动，并填写合并后的名称。")
                return

            # 添加到操作列表
            self.merge_ops.append({
                "activities": activities,
                "new_name": new_name,
                "strategy": strategy,
                "fields": fields
            })

            self.update_merge_ops_list()
            self.refresh_log_after_merge_ops()

    def add_merge_rule(self, rule_dict):
        self.merge_rules.append(rule_dict)
        self.refresh_merge_rule_list()
        self.refresh_log_after_merge_ops()

    def refresh_log_after_merge_ops(self):
        try:
            from cpa_utils import apply_activity_merge_rules
            self.log_history.append(self.current_log)
            self.current_log = apply_activity_merge_rules(self.current_log, self.merge_rules)
            self.update_graph_with_filter()
            self.update_dataset_preview()
        except Exception as e:
            QMessageBox.critical(self, "执行失败", str(e))



    def refresh_log_after_merge_ops(self):
        from cpa_utils import apply_merge_operations
        try:
            self.log_history.append(self.current_log)
            self.current_log = apply_merge_operations(self.original_log, self.merge_ops)
            self.update_graph_with_filter()
            self.update_dataset_preview()
        except Exception as e:
            QMessageBox.critical(self, "合并失败", str(e))

    def open_merge_activity_dialog(self):
        from merge_activity_dialog import MergeActivityDialog

        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        all_activities = df["concept:name"].dropna().unique().tolist()

        dialog = MergeActivityDialog(all_activities, self)
        if dialog.exec_():
            selected_acts, new_name = dialog.selected_activities, dialog.new_activity_name

            if not selected_acts or not new_name:
                QMessageBox.warning(self, "错误", "请选择至少一个活动，并输入合并后名称。")
                return

            self.redo_stack.clear()  # ✅ 清空重做栈，防止误重做

            # 新建操作记录（合并操作）
            operation = {
                "type": "merge",
                "activities": selected_acts,
                "target": new_name,
                "strategy": "first",
                "fields": []
            }

            self.activity_ops_history.append(self.activity_ops.copy())  # ✅ 添加历史记录
            self.activity_ops.append(operation)
            self.update_activity_ops_list()
            self.reapply_activity_ops()

    def update_activity_ops_list(self):
        self.activity_ops_list.clear()
        for idx, op in enumerate(self.activity_ops):
            if op["type"] == "merge":
                desc = f"合并 {' + '.join(op['activities'])} → {op['target']}"
            elif op["type"] == "aggregate":
                target = op['activities'][0]
                strategy = op['strategy']
                fields = op.get("fields", [])
                new_col = op.get("new_col", "")
                field_str = " + ".join(fields) if fields else ""
                if new_col:
                    desc = f"聚合 {target} → {field_str} = {new_col}（保留 {strategy}）"
                else:
                    desc = f"聚合 {target}（保留 {strategy}）字段：{field_str}"
            elif op["type"] == "filter":
                desc = f"过滤频次 < {op['threshold']}"
            elif op["type"] == "reset":
                desc = "重置为原始日志"
            else:
                desc = f"未知操作 {idx}"
            self.activity_ops_list.addItem(QListWidgetItem(desc))

    def reapply_activity_ops(self):
        from pm4py.objects.conversion.log import converter as log_converter

        df = log_converter.apply(self.original_log, variant=log_converter.Variants.TO_DATA_FRAME)

        for op in self.activity_ops:
            if op["type"] == "reset":
                df = log_converter.apply(self.original_log, variant=log_converter.Variants.TO_DATA_FRAME)
            elif op["type"] == "filter":
                from cpa_pm_preprocessing import remove_events_low_frequency
                df = remove_events_low_frequency(df, event_col="concept:name", min_freq=op["threshold"])
            elif op["type"] == "merge":
                df = df.copy()
                from cpa_utils import merge_activities_in_dataframe
                df = merge_activities_in_dataframe(df, op["activities"], op["target"])
            elif op["type"] == "aggregate":
                from cpa_utils import aggregate_activity_occurrences
                df = aggregate_activity_occurrences(
                    df,
                    target_activity=op["activities"][0],
                    keep=op["strategy"],
                    timestamp_col="time:timestamp",
                    agg_fields=op.get("fields"),
                    new_col=op.get("new_col", None)  # ✅ 支持写入新列
                )

        df["lifecycle:transition"] = "complete"
        self.current_log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
        self.update_graph_with_filter()
        self.update_dataset_preview()

    def redo_last_change(self):
        if hasattr(self, "redo_stack") and self.redo_stack:
            self.activity_ops_history.append(self.activity_ops.copy())  # ✅ 备份当前状态
            self.activity_ops = self.redo_stack.pop()
            self.update_activity_ops_list()
            self.reapply_activity_ops()
        else:
            QMessageBox.information(self, "提示", "没有可以重做的操作。")

    def open_aggregate_activity_dialog(self):
        from aggregate_activity_dialog import AggregateActivityDialog

        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        if df.empty:
            QMessageBox.warning(self, "数据缺失", "当前数据为空，无法设置活动聚合。")
            return

        all_activities = sorted(df["concept:name"].dropna().unique())
        all_fields = [col for col in df.columns if
                      col not in ["case:concept:name", "concept:name", "time:timestamp", "lifecycle:transition"]]

        dialog = AggregateActivityDialog(all_activities, all_fields, self)
        if dialog.exec_():
            selected_activity, strategy, fields, new_col = dialog.get_values()

            # 构造聚合操作记录
            # 添加到操作记录中
            operation = {
                "type": "aggregate",
                "activities": [selected_activity],
                "strategy": strategy,
                "fields": fields,
                "new_col": new_col  # ✅ 新增
            }

            self.activity_ops_history.append(self.activity_ops.copy())
            self.activity_ops.append(operation)
            self.update_activity_ops_list()
            self.reapply_activity_ops()

    def update_summary(self):
        """更新概况显示"""
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        num_events    = len(df)
        num_traces    = df['case:concept:name'].nunique()
        num_activities= df['concept:name'].nunique()
        num_variants  = df.sort_values(
            ['case:concept:name','time:timestamp']
        ).groupby('case:concept:name')['concept:name'] \
         .apply(tuple).nunique()

        self.lbl_summary_events.setText(f"事件数: {num_events}")
        self.lbl_summary_traces.setText(f"流程数: {num_traces}")
        self.lbl_summary_activities.setText(f"活动数: {num_activities}")
        self.lbl_summary_variants.setText(f"变体数: {num_variants}")

    def apply_dataframe_op(self, df, desc):
        """统一将 DataFrame 应用到 current_log，并更新历史/操作列表/UI"""
        df['lifecycle:transition'] = 'complete'
        new_log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
        self.log_history.append(self.current_log)
        self.current_log = new_log
        self.activity_ops_history.append(self.activity_ops.copy())
        self.activity_ops.append({'type':'custom','desc':desc})
        self.update_activity_ops_list()
        self.update_graph_with_filter()
        self.update_dataset_preview()

    def delete_traces_by_start(self):
        ev = self.edit_req_start.text().strip()
        if not ev:
            QMessageBox.warning(self, "提示", "请输入起始事件名称。"); return
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        df2 = delete_truncated_traces_start(df, 'case:concept:name', 'concept:name', ev)
        self.apply_dataframe_op(df2, f"删除未以[{ev}]开头案例")

    def delete_traces_by_end(self):
        ev = self.edit_req_end.text().strip()
        if not ev:
            QMessageBox.warning(self, "提示", "请输入结束事件名称。"); return
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        df2 = delete_truncated_traces_end(df, 'case:concept:name', 'concept:name', ev)
        self.apply_dataframe_op(df2, f"删除未以[{ev}]结尾案例")

    def delete_short_traces(self):
        n = self.spin_min_events.value()
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        df2= delete_traces_with_short_length(df, 'case:concept:name', n)
        self.apply_dataframe_op(df2, f"删除事件数< {n}案例")

    def delete_short_duration(self):
        secs = self.spin_min_dur.value()
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        # 计算每条 trace 持续：max(ts)-min(ts)
        dur = df.groupby('case:concept:name')['time:timestamp'] \
                .agg(lambda x: (x.max()-x.min()).total_seconds())
        keep = dur[dur>=secs].index
        df2 = df[df['case:concept:name'].isin(keep)].copy()
        self.apply_dataframe_op(df2, f"删除持续<{secs}秒案例")

    def filter_by_time_interval(self):
        start = self.dt_start.dateTime().toPyDateTime()
        end   = self.dt_end.dateTime().toPyDateTime()
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        df2 = df[(df['time:timestamp']>=start)&(df['time:timestamp']<=end)].copy()
        self.apply_dataframe_op(df2, f"时间区间筛选[{start}~{end}]")

    def filter_by_custom_condition(self):
        expr = self.edit_custom.text().strip()
        if not expr:
            QMessageBox.warning(self, "提示", "请输入筛选表达式。"); return
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        try:
            df2 = df.query(expr).copy()
        except Exception as e:
            QMessageBox.critical(self, "表达式错误", str(e)); return
        self.apply_dataframe_op(df2, f"自定义筛选[{expr}]")

    def show_topk_events(self):
        k = self.spin_topk.value()
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        topk = df['concept:name'].value_counts().head(k)
        QMessageBox.information(
            self, "TopK 活动",
            "\n".join(f"{evt}: {cnt}" for evt,cnt in topk.items())
        )

    def export_csv(self):
        """将 current_log 导出为 CSV"""
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        path, _ = QFileDialog.getSaveFileName(self, "保存 CSV", os.getcwd(), "CSV 文件 (*.csv)")
        if not path: return
        if not path.lower().endswith('.csv'): path += '.csv'
        try:
            df.to_csv(path, index=False)
            QMessageBox.information(self, "导出成功", f"已保存：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

def launch_analysis_window(event_log):
    """
    供外部程序调用入口，默认全屏显示并返回窗口对象
    """
    global _analysis_window
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    _analysis_window = ProcessAnalysisWindow(event_log)
    _analysis_window.showMaximized()  # ✅ 默认最大化显示
    return _analysis_window           # ✅ 返回窗口对象

