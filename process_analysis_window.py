# process_analysis_window.py
import sys

import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QSplitter, QLabel, QSpinBox, QMessageBox, QSlider, QGroupBox, QTableWidget, QTableWidgetItem
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
        # 当前日志
        self.current_log = event_log
        # 日志历史栈（用于撤销上一操作）
        self.log_history = []

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

        splitter = QSplitter(Qt.Horizontal)
        from PyQt5.QtWidgets import QSizePolicy

        # 垂直分割器让顶部“数据集”与下方流程图&控制面板区域可调高度
        vsplitter = QSplitter(Qt.Vertical)
        vsplitter.addWidget(self.dataset_group)
        vsplitter.addWidget(splitter)
        vsplitter.setSizes([200, 500])  # 初始高度比例可自行调节

        # 设置 dataset_group 支持拉伸
        self.dataset_group.setMinimumHeight(100)
        self.dataset_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        main_layout = QVBoxLayout()
        main_widget = QWidget()
        main_layout.addWidget(vsplitter)
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        self.graph_view = ProcessGraphView()
        self.graph_view.draw_from_event_log(self.current_log)
        splitter.addWidget(self.graph_view)

        control_panel = QWidget()
        control_layout = QVBoxLayout()

        btn_cpa_first_only = QPushButton("CPA：保留首次活动")
        btn_cpa_first_only.clicked.connect(self.cpa_keep_first)
        control_layout.addWidget(btn_cpa_first_only)

        lbl_freq = QLabel("过滤低频活动（最小出现次数）：")
        self.freq_spin = QSpinBox()
        self.freq_spin.setMinimum(1)
        self.freq_spin.setMaximum(999)
        self.freq_spin.setValue(2)

        btn_filter_freq = QPushButton("应用频次过滤")
        btn_filter_freq.clicked.connect(self.filter_by_frequency)


        btn_reset = QPushButton("重置为原始日志")
        btn_reset.clicked.connect(self.reset_log)

        # 新增 “撤销上一步修改” 按钮
        btn_undo_last = QPushButton("撤销上一步修改")
        btn_undo_last.clicked.connect(self.undo_last_change)

        btn_keep_last = QPushButton("CPA: 保留最后一次事件")
        btn_keep_last.clicked.connect(self.cpa_keep_last)
        control_layout.addWidget(btn_keep_last)

        btn_merge_cpa = QPushButton("CPA: 合并重复活动")
        btn_merge_cpa.clicked.connect(self.cpa_merge_duplicates)
        control_layout.addWidget(btn_merge_cpa)

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

        # 将控件加入布局
        control_layout.addWidget(lbl_freq)
        control_layout.addWidget(self.freq_spin)
        control_layout.addWidget(btn_filter_freq)
        control_layout.addSpacing(20)
        control_layout.addWidget(btn_reset)
        control_layout.addWidget(btn_undo_last)
        control_layout.addSpacing(20)
        control_layout.addWidget(self.label_act_slider)
        control_layout.addWidget(self.slider_act)
        control_layout.addWidget(self.label_edge_slider)
        control_layout.addWidget(self.slider_edge)
        control_layout.addStretch()

        control_panel.setLayout(control_layout)
        splitter.addWidget(control_panel)
        splitter.setSizes([800, 300])
        self.update_dataset_preview()  # ⬅ 添加这一行，使得窗口一打开就显示数据集

    def filter_by_frequency(self):
        """
        根据活动出现的总频次进行过滤。
        若有活动 < 阈值，则丢弃包含该活动的整条Trace。
        """
        threshold = self.freq_spin.value()
        try:
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
        恢复到最初的原始日志
        """
        self.current_log = self.original_log
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
        act_percent = self.slider_act.value()
        edge_percent = self.slider_edge.value()
        self.graph_view.draw_from_event_log(self.current_log, act_percent=act_percent, edge_percent=edge_percent)

    def cpa_keep_first(self):
        from cpa_utils import keep_first_occurrence_only

        try:
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

    def cpa_keep_last(self):
        try:
            from cpa_utils import cpa_keep_last
            self.log_history.append(self.current_log)
            self.current_log = cpa_keep_last(self.current_log)
            self.update_graph_with_filter()
            QMessageBox.information(self, "完成", "已保留每个活动的最后一次事件。")
        except Exception as e:
            if self.log_history:
                self.log_history.pop()
            QMessageBox.critical(self, "处理失败", f"CPA处理时出错：\n{e}")
        self.update_dataset_preview()


    def cpa_merge_duplicates(self):
        """
        调用 cpa_utils 中的活动合并 API
        """
        try:
            from cpa_utils import cpa_merge_duplicate_activities
            self.log_history.append(self.current_log)
            self.current_log = cpa_merge_duplicate_activities(self.current_log, time_strategy='min',
                                                              agg_columns=["org:resource", "other:info"])
            self.update_graph_with_filter()
            QMessageBox.information(self, "完成", "重复活动已按 CPA 合并策略处理完成。")
        except Exception as e:
            if self.log_history:
                self.log_history.pop()
            QMessageBox.critical(self, "处理失败", f"合并出错：\n{e}")


    def update_dataset_preview(self):
        """
        将 current_log 转为 DataFrame 并显示前 visible_rows 行
        """
        try:
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
        df = self._dataset_df
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
            if self.visible_rows < len(self._dataset_df):
                self.visible_rows += 20
                self._refresh_dataset_table()

    def toggle_dataset_visibility(self):
        """展开/收起数据集展示"""
        expanded = self.dataset_group.isChecked()
        self.dataset_table.setVisible(expanded)
        self.dataset_group.setTitle("▼ 数据集" if expanded else "▶ 数据集")


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
