# process_analysis_window.py
import os
import sys
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QSplitter, QLabel, QSpinBox, QMessageBox, QSlider,
    QGroupBox, QTableWidget, QTableWidgetItem, QListWidget, QDialog, QListWidgetItem, QFileDialog, QComboBox, QCompleter
)
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDateTimeEdit, QLineEdit, QGroupBox
from PyQt5.QtCore import QDateTime
from typing import List
from cpa_utils import remove_consecutive_self_loops

from process_graph_view import ProcessGraphView
from pm4py.objects.conversion.log import converter as log_converter
from merge_activity_dialog import MergeActivityDialog
from remove_self_loop_dialog import RemoveSelfLoopDialog


class ProcessAnalysisWindow(QMainWindow):
    def __init__(self, event_log, col_mapping=None, parent=None):
        self.col_mapping = col_mapping or {
            "case:concept:name": "case:concept:name",
            "concept:name": "concept:name",
            "time:timestamp": "time:timestamp"
        }

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

        # —— 高级筛选与操作区 ——
        adv_group = QGroupBox("高级筛选与操作")
        adv_layout = QVBoxLayout()

        # ① 起止事件筛选
        h_start_end = QHBoxLayout()
        h_start_end.addWidget(QLabel("起始事件:"))
        self.cbo_filter_start = QComboBox()
        self.cbo_filter_start.setEditable(True)
        self.cbo_filter_start.setInsertPolicy(QComboBox.NoInsert)
        h_start_end.addWidget(self.cbo_filter_start)

        h_start_end.addWidget(QLabel("结束事件:"))
        self.cbo_filter_end = QComboBox()
        self.cbo_filter_end.setEditable(True)
        self.cbo_filter_end.setInsertPolicy(QComboBox.NoInsert)
        h_start_end.addWidget(self.cbo_filter_end)

        btn_filter_start_end = QPushButton("筛选")
        btn_filter_start_end.clicked.connect(self.filter_by_start_end_events)
        h_start_end.addWidget(btn_filter_start_end)

        adv_layout.addLayout(h_start_end)

        # ② 过滤低频活动（新的位置）
        h_freq = QHBoxLayout()
        h_freq.addWidget(QLabel("过滤低频活动 ≥"))
        self.freq_spin = QSpinBox()
        self.freq_spin.setMinimum(1)
        self.freq_spin.setMaximum(999)
        self.freq_spin.setValue(2)
        h_freq.addWidget(self.freq_spin)

        btn_filter_freq = QPushButton("应用频次过滤")
        btn_filter_freq.clicked.connect(self.filter_events_by_global_frequency)
        h_freq.addWidget(btn_filter_freq)

        adv_layout.addLayout(h_freq)

        # ③ 删除过短案例（按事件数）
        h_short = QHBoxLayout()
        h_short.addWidget(QLabel("筛选流程事件数 ≥"))
        self.spin_trace_len = QSpinBox()
        self.spin_trace_len.setMinimum(1)
        self.spin_trace_len.setValue(2)
        h_short.addWidget(self.spin_trace_len)

        btn_trace_len_filter = QPushButton("筛选")
        btn_trace_len_filter.clicked.connect(self.filter_short_traces)
        h_short.addWidget(btn_trace_len_filter)

        adv_layout.addLayout(h_short)

        # ④ 流程持续时间筛选
        h_dur = QHBoxLayout()
        h_dur.addWidget(QLabel("流程持续时间范围 (秒):"))

        self.spin_min_dur = QSpinBox()
        self.spin_min_dur.setMinimum(0)
        self.spin_min_dur.setMaximum(999999)
        self.spin_min_dur.setValue(0)
        h_dur.addWidget(QLabel("≥"))
        h_dur.addWidget(self.spin_min_dur)

        self.spin_max_dur = QSpinBox()
        self.spin_max_dur.setMinimum(0)
        self.spin_max_dur.setMaximum(999999)
        self.spin_max_dur.setValue(0)
        h_dur.addWidget(QLabel("≤"))
        h_dur.addWidget(self.spin_max_dur)

        btn_filter_dur = QPushButton("筛选")
        btn_filter_dur.clicked.connect(self.filter_by_trace_duration)
        h_dur.addWidget(btn_filter_dur)

        adv_layout.addLayout(h_dur)

        # ⑤ 流程起止时间筛选
        layout_trace_time = QHBoxLayout()
        layout_trace_time.addWidget(QLabel("开始时间:"))
        self.dt_trace_start = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_trace_start.setCalendarPopup(True)
        layout_trace_time.addWidget(self.dt_trace_start)

        layout_trace_time.addWidget(QLabel("结束时间:"))
        self.dt_trace_end = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_trace_end.setCalendarPopup(True)
        layout_trace_time.addWidget(self.dt_trace_end)

        default_time = QDateTime.fromString("2018-08-01 00:00:00", "yyyy-MM-dd HH:mm:ss")
        self.dt_trace_start.setDateTime(default_time)
        self.dt_trace_end.setDateTime(default_time)

        btn_trace_time_filter = QPushButton("筛选")
        btn_trace_time_filter.clicked.connect(self.filter_by_trace_start_end_time_range)
        layout_trace_time.addWidget(btn_trace_time_filter)

        adv_layout.addLayout(layout_trace_time)

        # 删除记录功能
        lbl_del = QLabel("删除记录条件：")
        adv_layout.addWidget(lbl_del)

        layout_del = QHBoxLayout()
        self.cbo_del_level = QComboBox()
        self.cbo_del_level.addItems(["事件级", "流程级"])
        self.cbo_del_level.setFixedWidth(70)
        layout_del.addWidget(self.cbo_del_level)

        self.cbo_del_col = QComboBox()
        self.cbo_del_col.setEditable(True)
        self.cbo_del_col.setInsertPolicy(QComboBox.NoInsert)
        layout_del.addWidget(self.cbo_del_col)

        self.cbo_del_op = QComboBox()
        self.cbo_del_op.addItems(["==", "!=", ">", "<", ">=", "<="])
        self.cbo_del_op.setFixedWidth(60)
        layout_del.addWidget(self.cbo_del_op)

        self.edit_del_val = QLineEdit()
        self.edit_del_val.setPlaceholderText("输入值")
        layout_del.addWidget(self.edit_del_val)

        btn_del_apply = QPushButton("删除")
        btn_del_apply.clicked.connect(self.delete_records_by_condition)
        layout_del.addWidget(btn_del_apply)

        adv_layout.addLayout(layout_del)

        # ⑥ 活动合并按钮
        btn_merge_activity = QPushButton("活动合并")
        btn_merge_activity.clicked.connect(self.open_merge_activity_dialog)
        adv_layout.addWidget(btn_merge_activity)

        # ⑦ 活动聚合按钮
        btn_aggregate_activity = QPushButton("活动聚合")
        btn_aggregate_activity.clicked.connect(self.open_aggregate_activity_dialog)
        adv_layout.addWidget(btn_aggregate_activity)

        # ⑧ 清除自循环片段
        btn_remove_loops = QPushButton("清除自循环片段")
        btn_remove_loops.clicked.connect(self.remove_self_loops)
        adv_layout.addWidget(btn_remove_loops)

        # ⑨ 已定义操作记录列表
        adv_layout.addWidget(QLabel("已定义的活动处理操作（可排序）:"))
        self.activity_ops = []
        self.activity_ops_list = QListWidget()
        self.activity_ops_list.setDragDropMode(QListWidget.InternalMove)
        adv_layout.addWidget(self.activity_ops_list)

        # ⑩ 删除/撤销/重做按钮行
        btns_layout = QHBoxLayout()
        btn_remove_selected_op = QPushButton("删除选中操作")
        btn_remove_selected_op.clicked.connect(self.remove_selected_activity_op)
        btns_layout.addWidget(btn_remove_selected_op)

        btn_undo_last = QPushButton("撤销上一步修改")
        btn_undo_last.clicked.connect(self.undo_last_change)
        btns_layout.addWidget(btn_undo_last)

        btn_redo = QPushButton("重做上一步修改")
        btn_redo.clicked.connect(self.redo_last_change)
        btns_layout.addWidget(btn_redo)

        btn_container = QWidget()
        btn_container.setLayout(btns_layout)
        adv_layout.addWidget(btn_container)

        # ⑪ 重置为原始日志按钮（新位置）
        btn_reset = QPushButton("重置为原始日志")
        btn_reset.clicked.connect(self.reset_log)
        adv_layout.addWidget(btn_reset)

        # ⑫ 滑块（节点比例 / 边比例）
        self.label_act_slider = QLabel("活动节点显示比例：")
        self.slider_act = QSlider(Qt.Horizontal)
        self.slider_act.setMinimum(1)
        self.slider_act.setMaximum(100)
        self.slider_act.setValue(100)
        self.slider_act.valueChanged.connect(self.update_graph_with_filter)

        self.label_edge_slider = QLabel("路径边显示比例：")
        self.slider_edge = QSlider(Qt.Horizontal)
        self.slider_edge.setMinimum(1)
        self.slider_edge.setMaximum(100)
        self.slider_edge.setValue(100)
        self.slider_edge.valueChanged.connect(self.update_graph_with_filter)

        adv_layout.addWidget(self.label_act_slider)
        adv_layout.addWidget(self.slider_act)
        adv_layout.addWidget(self.label_edge_slider)
        adv_layout.addWidget(self.slider_edge)

        # 查看 Cases 按钮
        btn_cases = QPushButton("查看 Cases")
        btn_cases.clicked.connect(self.open_cases_window)
        adv_layout.addWidget(btn_cases)

        adv_group.setLayout(adv_layout)
        control_layout.addWidget(adv_group)
        control_layout.addStretch()
        splitter_h.addWidget(control_panel)
        splitter_h.setSizes([2000, 50])

        self.merge_rules = []  # 每条规则是一个 dict
        self.merge_list_panel = QWidget()
        self.merge_list_layout = QVBoxLayout()
        self.merge_list_panel.setLayout(self.merge_list_layout)
        control_layout.addWidget(self.merge_list_panel)

        # --- 窗口初始化与操作记录部分 ---
        self.update_dataset_preview()  # 让窗口初始化时直接展示数据
        self.activity_ops_history = []  # 操作记录堆栈，用于撤销功能
        self.redo_stack = []  # 初始化重做栈
        self.activity_ops_list.setDragDropMode(QListWidget.InternalMove)
        self.activity_ops_list.model().rowsMoved.connect(self.sync_ops_after_sort)

    def filter_events_by_global_frequency(self):
        """
        删除频次 < 阈值 的事件（只删 event，不删整条 trace）
        """
        from cpa_utils import filter_events_by_global_frequency
        from pm4py.objects.conversion.log import converter as log_converter

        min_freq = self.freq_spin.value()
        self.redo_stack.clear()

        if self.current_log is None:
            QMessageBox.critical(self, "错误", "当前日志为空。")
            return

        try:
            df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)

            # ✅ 判断是否有活动频次低于阈值
            value_counts = df["concept:name"].value_counts()
            low_freq_events = value_counts[value_counts < min_freq]

            if low_freq_events.empty:
                QMessageBox.information(self, "提示", f"所有活动频次 ≥ {min_freq}，无需过滤。")
                return

            # ✅ 执行真正的过滤
            df2 = filter_events_by_global_frequency(df, event_col="concept:name", min_freq=min_freq)

            if df2.empty:
                QMessageBox.warning(self, "无数据", "过滤后日志为空，请降低阈值。")
                return

            self.apply_dataframe_op(df2, f"过滤低频活动：{min_freq}")

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
        if self.activity_ops_history and self.log_history:
            # ✅ 同时备份当前状态（用于重做）
            self.redo_stack.append((self.activity_ops.copy(), self.current_log))

            # ✅ 同步恢复
            self.activity_ops = self.activity_ops_history.pop()
            self.current_log = self.log_history.pop()

            self.update_activity_ops_list()
            self.update_graph_with_filter()
            self.update_dataset_preview()
        else:
            QMessageBox.information(self, "提示", "没有可以撤销的操作。")

    def redo_last_change(self):
        if hasattr(self, "redo_stack") and self.redo_stack:
            # ✅ 同时备份当前状态（用于再撤销）
            self.activity_ops_history.append(self.activity_ops.copy())
            self.log_history.append(self.current_log)

            # ✅ 恢复 redo 的状态
            self.activity_ops, self.current_log = self.redo_stack.pop()

            self.update_activity_ops_list()
            self.update_graph_with_filter()
            self.update_dataset_preview()
        else:
            QMessageBox.information(self, "提示", "没有可以重做的操作。")

    def update_dataset_preview(self):
        """
        将 current_log 转回 DataFrame 并显示前 visible_rows 行，
        同时把内部列名(case:concept:name / concept:name / time:timestamp)
        还原成用户在预处理阶段看到的原列名。
        """
        if self.current_log is None:
            return

        # 拿到 PM4Py DataFrame
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        if df.empty:
            self.dataset_table.clear()
            return

        # 还原列名（使用标准→原始 的 col_mapping）
        df = df.rename(columns=self.col_mapping)

        act_col = self.col_mapping.get("concept:name", "concept:name")
        self._dataset_df = df.reset_index(drop=True)
        self.visible_rows = 20
        self._refresh_dataset_table()
        self.update_summary()

        # ✅ 更新组合删除功能的活动下拉框（带模糊搜索）
        if hasattr(self, "cbo_comb_start"):
            acts = self._dataset_df[act_col].dropna().astype(str).unique().tolist()
            acts.sort()
            for cbo in [self.cbo_comb_start, self.cbo_comb_end]:
                cbo.clear()
                cbo.addItems(acts)
                completer = QCompleter(acts, cbo)
                completer.setFilterMode(Qt.MatchContains)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                cbo.setCompleter(completer)
        # ✅ 更新起止筛选下拉框
        if hasattr(self, "cbo_filter_start"):
            acts = self._dataset_df["concept:name"].dropna().astype(str).unique().tolist()
            acts.sort()
            for cbo in [self.cbo_filter_start, self.cbo_filter_end]:
                cbo.blockSignals(True)
                cbo.clear()
                cbo.addItem("")  # 空值选项（表示未选中）
                cbo.addItems(acts)
                completer = QCompleter(acts, cbo)
                completer.setFilterMode(Qt.MatchContains)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                cbo.setCompleter(completer)
                cbo.blockSignals(False)
        # ✅ 更新删除记录功能的列名下拉框
        if hasattr(self, "cbo_del_col"):
            # 添加列名选项时，统一做字段名替换
            df_columns = df.columns.tolist()
            friendly_cols = [
                "Company_ID" if c == "case:concept:name" else
                "event" if c == "concept:name" else
                "time" if c == "time:timestamp" else
                c for c in df_columns
            ]
            self.cbo_del_col.clear()
            self.cbo_del_col.addItems(friendly_cols)
            self.cbo_del_col.addItems(df.columns.astype(str).tolist())
            self.cbo_del_col.blockSignals(False)

    def _refresh_dataset_table(self):
        df = getattr(self, "_dataset_df", None)
        if df is None or df.empty:
            self.dataset_table.clear()
            return

        # ✅ 删除 lifecycle:transition 列
        df = df.drop(columns=["lifecycle:transition"], errors="ignore")

        # ✅ 强制列顺序：前三列为固定主列，其他列保持原顺序在后
        base_cols = ["case:concept:name", "concept:name", "time:timestamp"]
        other_cols = [col for col in df.columns if col not in base_cols]
        final_cols = base_cols + other_cols
        df_display = df[final_cols]

        nrows = min(self.visible_rows, len(df_display))
        self.dataset_table.setRowCount(nrows)
        self.dataset_table.setColumnCount(len(df_display.columns))

        # ✅ 显示列名映射为：Company_ID / event / time
        col_alias = {
            "case:concept:name": "Company_ID",
            "concept:name": "Event",
            "time:timestamp": "Time"
        }
        headers = [col_alias.get(col, col) for col in df_display.columns]
        self.dataset_table.setHorizontalHeaderLabels(headers)

        for r in range(nrows):
            for c in range(len(df_display.columns)):
                val = str(df_display.iloc[r, c])
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
        row_idx = self.activity_ops_list.currentRow()
        if 0 <= row_idx < len(self.activity_ops):
            self.redo_stack.clear()
            self.activity_ops_history.append(self.activity_ops.copy())
            self.activity_ops.pop(row_idx)

            self.update_activity_ops_list()
            self.reapply_activity_ops()  # ✅ 重新应用剩下的操作链

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

    def update_activity_ops_list(self):######添加历史记录函数
        self.activity_ops_list.clear()
        for op in self.activity_ops:
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
            elif op["type"] == "filter_start_end":
                desc = f"起止事件筛选（起={op.get('start') or '-'}，终={op.get('end') or '-'})"
            elif op["type"] == "reset":
                desc = "重置为原始日志"
            elif op["type"] == "custom":
                desc = op.get("desc", "自定义操作")
            elif op["type"] == "filter_short_trace":
                desc = f"删除事件数 < {op['min_len']} 的 trace"
            elif op["type"] == "filter_duration":
                min_sec = op.get("min_sec", 0)
                max_sec = op.get("max_sec", 0)
                if min_sec > 0 and (max_sec == 0 or max_sec == float('inf')):
                    desc = f"删除持续时间短于 {min_sec} 秒的流程"
                elif max_sec > 0 and min_sec == 0:
                    desc = f"删除持续时间长于 {max_sec} 秒的流程"
                elif min_sec > 0 and max_sec > 0:
                    desc = f"筛选持续时间在 [{min_sec} ~ {max_sec}] 秒的流程"
                else:
                    desc = "筛选持续时间"
            elif op["type"] == "remove_self_loops":
                strat = op.get("strategy", "first")
                desc = "清除自循环片段（保留首次）" if strat == "first" else "清除自循环片段（保留最后）"
            elif op["type"] == "delete_condition":
                level = op.get("level", "事件级")
                desc = f"删除{'事件' if level == '事件级' else '流程'}中满足 {op['col']} {op['op']} {op['val']} 的记录"

            else:
                desc = f"未知操作"

            item = QListWidgetItem(desc)
            item.setData(Qt.UserRole, op)  # ✅ 绑定原始操作对象
            self.activity_ops_list.addItem(item)

    def reapply_activity_ops(self):
        from pm4py.objects.conversion.log import converter as log_converter

        df = log_converter.apply(self.original_log, variant=log_converter.Variants.TO_DATA_FRAME)

        for op in self.activity_ops:
            if op["type"] == "reset":
                df = log_converter.apply(self.original_log, variant=log_converter.Variants.TO_DATA_FRAME)
            elif op["type"] == "filter":
                from cpa_utils import filter_events_by_global_frequency
                df = filter_events_by_global_frequency(df, event_col="concept:name", min_freq=op["threshold"])
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
            elif op["type"] == "filter_start_end":
                from cpa_utils import filter_incomplete_traces
                df = filter_incomplete_traces(
                    df,
                    start_event=op.get("start"),
                    end_event=op.get("end"),
                    mode=op.get("mode", "不同时满足起止")
                )
            elif op["type"] == "filter_short_trace":
                trace_counts = df['case:concept:name'].value_counts()
                keep_cases = trace_counts[trace_counts >= op["min_len"]].index
                df = df[df['case:concept:name'].isin(keep_cases)].copy()
            elif op["type"] == "filter_duration":
                dur = df.groupby('case:concept:name')['time:timestamp'].agg(
                    lambda x: (x.max() - x.min()).total_seconds()
                )
                keep_cases = dur[(dur >= op["min_sec"]) & (dur <= op["max_sec"])].index
                df = df[df['case:concept:name'].isin(keep_cases)].copy()
            elif op["type"] == "remove_self_loops":
                from cpa_utils import remove_consecutive_self_loops
                df = remove_consecutive_self_loops(
                    df,
                    case_col="case:concept:name",
                    act_col="concept:name",
                    time_col="time:timestamp",
                    keep=op.get("strategy", "first")
                )
            elif op["type"] == "delete_condition":
                col = op["col"]
                operator = op["op"]
                val = op["val"]
                level = op.get("level", "事件级")

                try:
                    val_eval = eval(val, {}, {})
                except:
                    val_eval = val.strip("'\"")

                expr = f"`{col}` {operator} @val_eval"

                if level == "事件级":
                    df = df.query(f"not ({expr})", local_dict={"val_eval": val_eval})
                else:  # 流程级
                    match_cases = df.query(expr, local_dict={"val_eval": val_eval})["case:concept:name"].unique()
                    df = df[~df["case:concept:name"].isin(match_cases)]

        df["lifecycle:transition"] = "complete"
        self.current_log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
        self.update_graph_with_filter()
        self.update_dataset_preview()



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

    # ────────────────────────────────────────────────────
    # 顶部四个概况标签：记录数 / 流程数 / 活动数 / 变体数
    # ────────────────────────────────────────────────────
    def update_summary(self):
        """
        刷新概况显示
        records   : 当前 DataFrame 行数
        traces    : case:concept:name（流程）唯一值个数
        activities: concept:name 唯一值个数
        variants  : 排序后事件序列去重个数
        """
        df = log_converter.apply(
            self.current_log,
            variant=log_converter.Variants.TO_DATA_FRAME
        )

        # ① 记录数（rows）
        num_records = len(df)

        # ② 流程数（trace 数）
        num_traces = df['case:concept:name'].nunique()

        # ③ 活动数（事件类型）
        num_activities = df['concept:name'].nunique()

        # ④ 变体数（唯一的事件序列）
        num_variants = (
            df.sort_values(['case:concept:name', 'time:timestamp'])
              .groupby('case:concept:name')['concept:name']
              .apply(tuple)
              .nunique()
        )

        # 更新 4 个 QLabel
        self.lbl_summary_events.setText(f"记录数: {num_records}")
        self.lbl_summary_traces.setText(f"流程数: {num_traces}")
        self.lbl_summary_activities.setText(f"活动数: {num_activities}")
        self.lbl_summary_variants.setText(f"变体数: {num_variants}")

    def apply_dataframe_op(self, df, desc, extra_op=None):
        from pm4py.objects.conversion.log import converter as log_converter

        df['lifecycle:transition'] = 'complete'
        new_log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)

        self.log_history.append(self.current_log)
        self.activity_ops_history.append(self.activity_ops.copy())
        self.redo_stack.clear()

        self.current_log = new_log

        if extra_op:
            self.activity_ops.append(extra_op)
        else:
            self.activity_ops.append({'type': 'custom', 'desc': desc})

        self.update_activity_ops_list()
        self.update_graph_with_filter()
        self.update_dataset_preview()

    def delete_incomplete_traces(self):
        from cpa_utils import filter_incomplete_traces
        from pm4py.objects.conversion.log import converter as log_converter

        start_ev = self.cbo_comb_start.currentText().strip()
        end_ev = self.cbo_comb_end.currentText().strip()
        mode = self.cbo_comb_mode.currentText()

        if not start_ev and not end_ev:
            QMessageBox.warning(self, "提示", "请至少选择起始或结束事件。")
            return

        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        df2 = filter_incomplete_traces(
            df,
            start_event=start_ev or None,
            end_event=end_ev or None,
            mode=mode
        )

        if df2.empty:
            QMessageBox.warning(self, "无数据", "过滤后为空，请检查起止事件。")
            return

        desc = f"删除不完整 trace（模式：{mode}，起始={start_ev}，结束={end_ev}）"
        self.apply_dataframe_op(df2, desc)


    def filter_by_time_interval(self):
        start = self.dt_start.dateTime().toPyDateTime()
        end   = self.dt_end.dateTime().toPyDateTime()
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        df2 = df[(df['time:timestamp']>=start)&(df['time:timestamp']<=end)].copy()
        self.apply_dataframe_op(df2, f"时间区间筛选[{start}~{end}]")



    def filter_by_start_end_events(self):
        from cpa_utils import filter_incomplete_traces
        from pm4py.objects.conversion.log import converter as log_converter

        start_ev = self.cbo_filter_start.currentText().strip()
        end_ev = self.cbo_filter_end.currentText().strip()

        if not start_ev and not end_ev:
            QMessageBox.warning(self, "提示", "请至少选择起始或结束事件。")
            return

        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        mode = "不同时满足起止" if (start_ev and end_ev) else ("不以起始事件开头" if start_ev else "不以结束事件结尾")

        df2 = filter_incomplete_traces(
            df,
            start_event=start_ev or None,
            end_event=end_ev or None,
            mode=mode
        )

        if df2.empty:
            QMessageBox.warning(self, "无数据", "筛选后为空，请检查设置。")
            return

        # ✅ 添加一次操作记录（带可恢复信息）
        self.activity_ops_history.append(self.activity_ops.copy())
        self.redo_stack.clear()
        self.activity_ops.append({
            "type": "filter_start_end",
            "start": start_ev,
            "end": end_ev,
            "mode": mode
        })
        self.update_activity_ops_list()

        # ✅ 应用 DataFrame（不添加新操作记录）
        self.apply_dataframe_direct(df2)

    def on_activity_ops_reordered(self):
        new_ops = []
        for i in range(self.activity_ops_list.count()):
            item = self.activity_ops_list.item(i)
            op = item.data(Qt.UserRole)
            new_ops.append(op)
        self.activity_ops = new_ops
        self.reapply_activity_ops()

    def apply_dataframe_direct(self, df):
        from pm4py.objects.conversion.log import converter as log_converter
        df['lifecycle:transition'] = 'complete'
        self.current_log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
        self.update_graph_with_filter()
        self.update_dataset_preview()

    def filter_short_traces(self):
        from pm4py.objects.conversion.log import converter as log_converter

        min_len = self.spin_trace_len.value()
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)

        trace_lengths = df['case:concept:name'].value_counts()
        keep_cases = trace_lengths[trace_lengths >= min_len].index
        df2 = df[df['case:concept:name'].isin(keep_cases)].copy()

        if df2.empty:
            QMessageBox.warning(self, "无结果", "筛选后数据为空，请降低阈值。")
            return

        # ✅ 添加操作记录，支持撤销重做
        self.activity_ops_history.append(self.activity_ops.copy())
        self.redo_stack.clear()
        self.activity_ops.append({
            "type": "filter_short_trace",
            "min_len": min_len
        })
        self.update_activity_ops_list()
        self.apply_dataframe_direct(df2)

    def filter_by_trace_duration(self):
        from pm4py.objects.conversion.log import converter as log_converter

        min_sec = self.spin_min_dur.value()
        max_sec = self.spin_max_dur.value()

        if min_sec > 0 and max_sec > 0 and min_sec > max_sec:
            QMessageBox.warning(self, "输入有误", "最小值不能大于最大值")
            return

        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], errors="coerce")

        # ✅ 将 max=0 解释为“不设上限”
        max_sec_effective = float('inf') if max_sec == 0 else max_sec

        durations = df.groupby("case:concept:name")["time:timestamp"].agg(
            lambda x: (x.max() - x.min()).total_seconds() if not x.isnull().any() else 0
        )

        keep_cases = durations[(durations >= min_sec) & (durations <= max_sec_effective)].index
        df2 = df[df["case:concept:name"].isin(keep_cases)].copy()

        if df2.empty:
            QMessageBox.warning(self, "无数据", "筛选后为空，请检查设置。")
            return

        # ✅ 构造描述 + 执行操作
        desc = self.build_duration_filter_description(min_sec, max_sec)
        self.apply_dataframe_op(df2, desc, extra_op={
            "type": "filter_duration",
            "min_sec": min_sec,
            "max_sec": max_sec
        })

    def build_duration_filter_description(self, min_sec, max_sec):
        if min_sec > 0 and max_sec == 0:
            return f"删除持续时间短于 {min_sec} 秒的流程"
        elif max_sec > 0 and min_sec == 0:
            return f"删除持续时间长于 {max_sec} 秒的流程"
        elif min_sec > 0 and max_sec > 0:
            return f"筛选持续时间在 [{min_sec} ~ {max_sec}] 秒的流程"
        else:
            return "筛选持续时间"

    def build_duration_filter_description(self, min_sec, max_sec):
        if min_sec > 0 and (max_sec == 0 or max_sec == float('inf')):
            return f"删除持续时间短于 {min_sec} 秒的流程"
        elif max_sec > 0 and min_sec == 0:
            return f"删除持续时间长于 {max_sec} 秒的流程"
        elif min_sec > 0 and max_sec > 0:
            return f"筛选持续时间在 [{min_sec} ~ {max_sec}] 秒的流程"
        else:
            return "筛选持续时间"

    def sync_ops_after_sort(self, parent, start, end, dest, row):
        """
        拖动 QListWidget 操作顺序后，更新 self.activity_ops 的顺序并重新应用
        """
        if start == row or start + 1 == row:
            return  # 无实际移动，不处理

        # ✅ 拿到当前 op 并移动顺序
        op = self.activity_ops.pop(start)
        insert_idx = row if row < start else row - 1
        self.activity_ops.insert(insert_idx, op)

        # ✅ 同步历史记录和图/表
        self.activity_ops_history.append(self.activity_ops.copy())
        self.redo_stack.clear()
        self.update_activity_ops_list()
        self.reapply_activity_ops()

    def filter_by_trace_start_end_time_range(self):
        """
        筛选 trace 的起止时间范围。
        保留 start_time >= X 且 end_time <= Y 的流程。
        """
        from pm4py.objects.conversion.log import converter as log_converter

        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)

        # 确保时间列为 datetime 类型
        if not pd.api.types.is_datetime64_any_dtype(df["time:timestamp"]):
            try:
                df["time:timestamp"] = pd.to_datetime(df["time:timestamp"])
            except Exception as e:
                QMessageBox.critical(self, "错误", f"时间格式错误：{str(e)}")
                return

        # 获取用户设置的起止时间（允许为空）
        start_dt = self.dt_trace_start.dateTime().toPyDateTime()
        end_dt = self.dt_trace_end.dateTime().toPyDateTime()

        # 获取每个 trace 的开始/结束时间
        trace_times = df.groupby("case:concept:name")["time:timestamp"].agg(["min", "max"]).reset_index()
        trace_times.columns = ["case_id", "start", "end"]
        from datetime import datetime

        # 默认时间为 2018-01-08 表示未修改
        default_dt = datetime(2018, 1, 8, 0, 0)
        use_start = start_dt != default_dt
        use_end = end_dt != default_dt

        if not use_start and not use_end:
            QMessageBox.information(self, "提示", "请至少设置开始时间或结束时间。")
            return

        keep_mask = pd.Series(True, index=trace_times.index)
        if use_start:
            keep_mask &= trace_times["start"] >= start_dt
        if use_end:
            keep_mask &= trace_times["end"] <= end_dt

        keep_cases = trace_times.loc[keep_mask, "case_id"]
        if keep_cases.empty:
            QMessageBox.warning(self, "无匹配", "未找到满足条件的流程。")
            return

        df2 = df[df["case:concept:name"].isin(keep_cases)].copy()

        # 构造记录描述
        if use_start and use_end:
            desc = f"筛选流程起止时间在 [{start_dt.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_dt.strftime('%Y-%m-%d %H:%M:%S')}]"
        elif use_start:
            desc = f"筛选流程开始时间 ≥ {start_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        else:
            desc = f"筛选流程结束时间 ≤ {end_dt.strftime('%Y-%m-%d %H:%M:%S')}"

        self.apply_dataframe_op(df2, desc)

    def remove_self_loops(self):
        if self.current_log is None:
            QMessageBox.warning(self, "无数据", "当前日志为空，无法清除自循环。")
            return

        dialog = RemoveSelfLoopDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return

        strategy = dialog.get_strategy()

        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        df2 = remove_consecutive_self_loops(
            df,
            case_col="case:concept:name",
            act_col="concept:name",
            time_col="time:timestamp",
            keep=strategy
        )

        if df2.empty:
            QMessageBox.warning(self, "结果为空", "清除后日志为空，请检查数据。")
            return

        desc = "清除自循环片段（保留首次）" if strategy == "first" else "清除自循环片段（保留最后）"
        self.apply_dataframe_op(df2, desc, extra_op={
            "type": "remove_self_loops",
            "strategy": strategy
        })

    # 移动进类内部（不需要加 @staticmethod）
    def reverse_display_column(self, display_col: str) -> str:
        DISPLAY_TO_INTERNAL_COLS = {
            "event": "concept:name",
            "Company_ID": "case:concept:name",
            "time": "time:timestamp"
        }
        return DISPLAY_TO_INTERNAL_COLS.get(display_col, display_col)

    def build_column_dropdown_options(self, df) -> list:
        DISPLAY_TO_INTERNAL_COLS = {
            "event": "concept:name",
            "Company_ID": "case:concept:name",
            "time": "time:timestamp"
        }
        INTERNAL_TO_DISPLAY_COLS = {v: k for k, v in DISPLAY_TO_INTERNAL_COLS.items()}

        result = []
        added = set()
        for col in df.columns.tolist():
            if col in INTERNAL_TO_DISPLAY_COLS:
                display = INTERNAL_TO_DISPLAY_COLS[col]
                if display not in added:
                    result.append(display)
                    added.add(display)
            elif col not in DISPLAY_TO_INTERNAL_COLS.values():
                if col not in added:
                    result.append(col)
                    added.add(col)
        return result

    def delete_records_by_condition(self):
        from pm4py.objects.conversion.log import converter as log_converter
        import pandas as pd

        # 获取界面输入项
        display_col = self.cbo_del_col.currentText().strip()
        op = self.cbo_del_op.currentText().strip()
        val = self.edit_del_val.text().strip()
        level = self.cbo_del_level.currentText().strip()

        if not display_col or not op or not val:
            QMessageBox.warning(self, "输入不完整", "请填写完整的列名、操作符和值。")
            return

        # 将用户选择的列名（如 "event"）映射回标准字段名（如 "concept:name"）
        col = self.reverse_display_column(display_col)


        try:
            df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)

            # 尝试将值转换为数字/布尔/时间；如果失败就当作字符串
            try:
                val_eval = eval(val, {}, {})
            except:
                val_eval = val.strip("'\"")

            expr = f"`{col}` {op} @val_eval"

            if level == "事件级":
                df2 = df.query(f"not ({expr})", local_dict={"val_eval": val_eval})
            elif level == "流程级":
                match_cases = df.query(expr, local_dict={"val_eval": val_eval})["case:concept:name"].unique()
                df2 = df[~df["case:concept:name"].isin(match_cases)]
            else:
                QMessageBox.warning(self, "未知操作", "未知的删除级别。")
                return

            if df2.empty:
                QMessageBox.warning(self, "无结果", "删除后数据为空，请检查条件。")
                return

            # 显示用户友好的列名描述
            desc = f"删除{'事件' if level == '事件级' else '流程'}中满足：{display_col} {op} {val} 的记录"

            # 添加操作记录，执行变更
            self.apply_dataframe_op(df2, desc, extra_op={
                "type": "delete_condition",
                "col": col,
                "op": op,
                "val": val,
                "level": level
            })

        except Exception as e:
            QMessageBox.critical(self, "删除失败", str(e))

    def open_cases_window(self):
        from cases_window import CasesWindow
        df = log_converter.apply(self.current_log, variant=log_converter.Variants.TO_DATA_FRAME)
        self.cases_win = CasesWindow(df, self.col_mapping)
        self.cases_win.show()


def launch_analysis_window(event_log, col_mapping=None):

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

