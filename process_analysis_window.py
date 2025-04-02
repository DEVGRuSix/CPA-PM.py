_analysis_window = None  # 放在文件顶部，全局作用域

import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QSplitter, QLabel, QSpinBox, QMessageBox
)
from PyQt5.QtCore import Qt
from process_graph_view import ProcessGraphView

# 导入 PM4Py 的事件日志支持
from pm4py.objects.conversion.log import converter as log_converter

class ProcessAnalysisWindow(QMainWindow):
    def __init__(self, event_log, parent=None):
        super().__init__(parent)
        self.setWindowTitle("流程图分析与交互控制")
        self.setGeometry(200, 100, 1200, 700)

        self.original_log = event_log  # 原始日志（不可变）
        self.current_log = event_log   # 当前日志状态（可变）

        # 主分区
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        # --- 左侧流程图区域 ---
        self.graph_view = ProcessGraphView()
        self.graph_view.draw_from_event_log(self.current_log)
        splitter.addWidget(self.graph_view)

        # --- 右侧控制面板 ---
        control_panel = QWidget()
        control_layout = QVBoxLayout()

        # 控件：过滤低频
        lbl_freq = QLabel("过滤低频活动（最小出现次数）：")
        self.freq_spin = QSpinBox()
        self.freq_spin.setMinimum(1)
        self.freq_spin.setMaximum(999)
        self.freq_spin.setValue(2)

        btn_filter_freq = QPushButton("应用频次过滤")
        btn_filter_freq.clicked.connect(self.filter_by_frequency)

        # 控件：恢复原始
        btn_reset = QPushButton("重置为原始日志")
        btn_reset.clicked.connect(self.reset_log)

        # 添加控件到布局
        control_layout.addWidget(lbl_freq)
        control_layout.addWidget(self.freq_spin)
        control_layout.addWidget(btn_filter_freq)
        control_layout.addSpacing(20)
        control_layout.addWidget(btn_reset)
        control_layout.addStretch()

        control_panel.setLayout(control_layout)
        splitter.addWidget(control_panel)
        splitter.setSizes([800, 300])

    def filter_by_frequency(self):
        threshold = self.freq_spin.value()
        try:
            from collections import Counter

            # 统计每个活动出现频率
            act_counter = Counter()
            for trace in self.current_log:
                for event in trace:
                    act = event.get("concept:name", "undefined")
                    act_counter[act] += 1

            # 找出低于阈值的活动
            low_freq_acts = {act for act, freq in act_counter.items() if freq < threshold}

            # 过滤包含这些活动的 trace
            filtered_log = []
            for trace in self.current_log:
                if any(event.get("concept:name") in low_freq_acts for event in trace):
                    continue
                filtered_log.append(trace)

            if not filtered_log:
                QMessageBox.warning(self, "无数据", "过滤后没有剩余日志。请降低阈值。")
                return

            self.current_log = filtered_log
            self.graph_view.draw_from_event_log(self.current_log)

            # 统计每个活动频率
            from collections import Counter
            act_counter = Counter()
            for trace in self.current_log:
                for event in trace:
                    act_counter[event["concept:name"]] += 1

            low_acts = {act for act, cnt in act_counter.items() if cnt < threshold}

            # 过滤所有包含低频活动的 trace
            filtered_log = []
            for trace in self.current_log:
                if any(event["concept:name"] in low_acts for event in trace):
                    continue
                filtered_log.append(trace)

            if not filtered_log:
                QMessageBox.warning(self, "无数据", "过滤后没有剩余日志。请降低阈值。")
                return

            self.current_log = filtered_log
            self.graph_view.draw_from_event_log(self.current_log)

        except Exception as e:
            QMessageBox.critical(self, "过滤失败", str(e))

    def reset_log(self):
        self.current_log = self.original_log
        self.graph_view.draw_from_event_log(self.current_log)


# 用于从主程序调用的启动函数
def launch_analysis_window(event_log):
    global _analysis_window
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    _analysis_window = ProcessAnalysisWindow(event_log)
    _analysis_window.show()

