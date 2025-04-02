"""
改进版 CSV 转 XES 的 PyQt GUI
==========================================
依赖库版本 (示例):
 - Python 3.11
 - PyQt5==5.15.7
 - pandas==1.5.3
 - pm4py==2.7.1
 - (可选) graphviz==0.20.1    # 若PM4Py需要流程可视化等功能

功能改进：
1. 列名清洗(可选)：去除空格/特殊符号、转小写。
2. 大小写修正(可选)：对活动名称列统一小写或首字母大写。
3. 空值处理：
   - Case ID / Activity / Timestamp 列如有空值，是否剔除？
   - 其他列若出现空值，是否剔除？
4. 自定义时间格式：用户可填写解析格式，如 '%Y/%m/%d %H:%M:%S'。
5. 增强异常捕获，防止程序无提示退出。
"""

import sys
import os
import re
import pandas as pd

from PyQt5.QtWidgets import (QApplication, QMainWindow, QFileDialog,
                             QWidget, QLabel, QPushButton, QComboBox,
                             QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                             QMessageBox, QGroupBox, QGridLayout, QCheckBox,
                             QRadioButton, QLineEdit)
from PyQt5.QtCore import Qt

# PM4Py相关导入
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.util import dataframe_utils
from pm4py.objects.conversion.log import converter as log_converter

class CSV2XESConverter(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CSV 转 XES 工具示例 - 改进版")
        self.setGeometry(300, 80, 900, 600)

        self.df = None  # 原始DataFrame
        self.file_path = None

        # 主容器
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # --- 上方文件选择与预览区 ---
        file_layout = QHBoxLayout()
        self.label_file = QLabel("请选择CSV文件：")
        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.clicked.connect(self.browse_csv)

        file_layout.addWidget(self.label_file)
        file_layout.addWidget(self.btn_browse)
        file_layout.addStretch()

        # CSV预览表
        self.table_preview = QTableWidget()
        self.table_preview.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_preview.setRowCount(0)
        self.table_preview.setColumnCount(0)
        self.table_preview.horizontalHeader().setStretchLastSection(True)

        # --- 中部“列映射”区 ---
        mapping_group = QGroupBox("列映射与设置")
        mapping_layout = QGridLayout()

        # 1) 列映射
        self.label_caseid = QLabel("案例ID列：")
        self.combo_caseid = QComboBox()
        self.label_activity = QLabel("活动名称列：")
        self.combo_activity = QComboBox()
        self.label_timestamp = QLabel("时间戳列：")
        self.combo_timestamp = QComboBox()

        mapping_layout.addWidget(self.label_caseid, 0, 0)
        mapping_layout.addWidget(self.combo_caseid, 0, 1)
        mapping_layout.addWidget(self.label_activity, 1, 0)
        mapping_layout.addWidget(self.combo_activity, 1, 1)
        mapping_layout.addWidget(self.label_timestamp, 2, 0)
        mapping_layout.addWidget(self.combo_timestamp, 2, 1)

        # 2) 列名清洗
        self.check_clean_headers = QCheckBox("清洗列名（去空格与特殊字符并转小写）")
        mapping_layout.addWidget(self.check_clean_headers, 3, 0, 1, 2)

        # 3) 活动名称大小写修正
        self.label_case_fix = QLabel("活动名称大小写：")
        self.radio_lower = QRadioButton("统一小写")
        self.radio_capitalize = QRadioButton("首字母大写")
        self.radio_nochange = QRadioButton("不修改")
        self.radio_nochange.setChecked(True)

        casefix_layout = QHBoxLayout()
        casefix_layout.addWidget(self.radio_lower)
        casefix_layout.addWidget(self.radio_capitalize)
        casefix_layout.addWidget(self.radio_nochange)

        mapping_layout.addWidget(self.label_case_fix, 4, 0)
        mapping_layout.addLayout(casefix_layout, 4, 1)

        # 4) 空值处理
        self.check_drop_empty_id = QCheckBox("删除CaseID/Activity/Timestamp为空的行")
        self.check_drop_empty_other = QCheckBox("删除其它列的空值行")
        mapping_layout.addWidget(self.check_drop_empty_id, 5, 0, 1, 2)
        mapping_layout.addWidget(self.check_drop_empty_other, 6, 0, 1, 2)

        # 5) 自定义时间格式
        self.label_timeformat = QLabel("时间格式(可选)：")
        self.edit_timeformat = QLineEdit()
        self.edit_timeformat.setPlaceholderText("如：%Y/%m/%d %H:%M:%S，留空则自动检测")

        mapping_layout.addWidget(self.label_timeformat, 7, 0)
        mapping_layout.addWidget(self.edit_timeformat, 7, 1)

        mapping_group.setLayout(mapping_layout)

        # --- 导出与分析 按钮 ---
        self.btn_export_xes = QPushButton("导出XES文件")
        self.btn_export_xes.clicked.connect(self.export_xes)

        self.btn_start_analysis = QPushButton("开始分析")
        self.btn_start_analysis.clicked.connect(self.start_analysis)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_export_xes)
        btn_layout.addWidget(self.btn_start_analysis)
        btn_layout.addStretch()

        # --- 整体布局 ---
        layout = QVBoxLayout(main_widget)
        layout.addLayout(file_layout)
        layout.addWidget(self.table_preview)
        layout.addWidget(mapping_group)
        layout.addLayout(btn_layout)

    def browse_csv(self):
        """
        用户选择CSV文件后，读取并预览前5行数据
        并填充下拉框选项
        """
        file_dialog = QFileDialog(self, "选择CSV文件", os.getcwd(), "CSV Files (*.csv);;All Files (*)")
        if file_dialog.exec_() == QFileDialog.Accepted:
            selected_file = file_dialog.selectedFiles()[0]
            if selected_file:
                self.file_path = selected_file
                try:
                    # 先读取
                    self.df = pd.read_csv(self.file_path)
                    # 是否需要列名清洗(只在加载时处理，避免重复勾选造成混乱)
                    if self.check_clean_headers.isChecked():
                        self.df = self.clean_headers(self.df)

                    # 显示文件名
                    self.label_file.setText(f"已选择文件：{os.path.basename(self.file_path)}")

                    # 在表格中预览前5行
                    self.show_csv_preview(self.df)

                    # 更新下拉框列名
                    columns = list(self.df.columns)
                    self.combo_caseid.clear()
                    self.combo_activity.clear()
                    self.combo_timestamp.clear()
                    self.combo_caseid.addItems(columns)
                    self.combo_activity.addItems(columns)
                    self.combo_timestamp.addItems(columns)
                except Exception as e:
                    QMessageBox.warning(self, "读取错误", f"无法读取CSV文件:\n{e}")
                    self.df = None
                    self.file_path = None
                    self.table_preview.setRowCount(0)
                    self.table_preview.setColumnCount(0)
                    return

    def clean_headers(self, df: pd.DataFrame):
        """
        将列名里的空格、特殊字符去除，并转为小写
        例如： 'Case ID ' -> 'case_id', 'Event(Name)' -> 'eventname'
        """
        new_cols = []
        for col in df.columns:
            # 去除前后空格
            c = col.strip()
            # 去掉非字母数字下划线
            c = re.sub(r'[^0-9a-zA-Z_]+', '', c)
            # 转小写
            c = c.lower()
            new_cols.append(c)
        df.columns = new_cols
        return df

    def show_csv_preview(self, df: pd.DataFrame):
        """
        将DataFrame的前5行显示到 QTableWidget 中
        """
        preview_rows = min(len(df), 5)   # 只展示前5行
        preview_cols = len(df.columns)

        self.table_preview.setRowCount(preview_rows)
        self.table_preview.setColumnCount(preview_cols)
        self.table_preview.setHorizontalHeaderLabels(df.columns.tolist())

        for r in range(preview_rows):
            for c in range(preview_cols):
                val = str(df.iloc[r, c])
                item = QTableWidgetItem(val)
                # 让单元格不可编辑
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.table_preview.setItem(r, c, item)

    def export_xes(self):
        """
        导出当前DataFrame为XES文件 (利用pm4py)
        需要用户先选择好Case ID、Activity、Timestamp列
        并根据用户勾选处理空值与时间格式
        """
        if self.df is None:
            QMessageBox.information(self, "提示", "请先选择并加载CSV文件。")
            return

        # 获取列映射
        col_caseid = self.combo_caseid.currentText()
        col_activity = self.combo_activity.currentText()
        col_timestamp = self.combo_timestamp.currentText()

        if not col_caseid or not col_activity or not col_timestamp:
            QMessageBox.warning(self, "列未选择", "请先在下拉框中指定 案例ID/活动名称/时间戳 列。")
            return

        # 选择保存XES文件路径
        save_dialog = QFileDialog(self, "另存为XES文件", os.getcwd(), "XES Files (*.xes);;All Files (*)")
        save_dialog.setAcceptMode(QFileDialog.AcceptSave)
        if save_dialog.exec_() != QFileDialog.Accepted:
            return
        xes_file_path = save_dialog.selectedFiles()[0]
        if not xes_file_path.lower().endswith(".xes"):
            xes_file_path += ".xes"

        # 复制一份临时DataFrame 用于导出
        tmp_df = self.df.copy()

        # 1) 处理活动名称大小写
        case_fix_mode = "nochange"
        if self.radio_lower.isChecked():
            case_fix_mode = "lower"
        elif self.radio_capitalize.isChecked():
            case_fix_mode = "capitalize"

        if case_fix_mode != "nochange":
            try:
                if case_fix_mode == "lower":
                    tmp_df[col_activity] = tmp_df[col_activity].astype(str).str.lower()
                else:  # capitalize
                    # 首字母大写, 其余小写
                    tmp_df[col_activity] = tmp_df[col_activity].astype(str).apply(
                        lambda s: s.capitalize()
                    )
            except Exception as e:
                QMessageBox.warning(self, "活动名称修正错误", f"无法修正活动大小写:\n{e}")
                return

        # 2) 空值处理
        # a) CaseID / Activity / Timestamp为空 => 是否剔除？
        if self.check_drop_empty_id.isChecked():
            tmp_df = tmp_df.dropna(subset=[col_caseid, col_activity, col_timestamp], how='any')

        # b) 其余列为空 => 是否剔除？
        if self.check_drop_empty_other.isChecked():
            # 找出 除CAT列外 所有列
            other_cols = [c for c in tmp_df.columns if c not in [col_caseid, col_activity, col_timestamp]]
            # 如有空值则剔除整行
            tmp_df = tmp_df.dropna(subset=other_cols, how='any')

        # 3) 时间格式
        user_time_format = self.edit_timeformat.text().strip()
        if user_time_format:
            # 用户自定义了格式
            try:
                tmp_df[col_timestamp] = pd.to_datetime(tmp_df[col_timestamp], format=user_time_format)
            except Exception as e:
                QMessageBox.warning(self, "时间格式错误", f"无法按指定格式转换时间戳:\n{e}")
                return
        else:
            # 未填写 => 使用 pm4py 的自动检测
            try:
                tmp_df = dataframe_utils.convert_timestamp_columns_in_df(
                    tmp_df, timest_columns=[col_timestamp]
                )
            except Exception as e:
                QMessageBox.warning(self, "时间自动检测失败", f"尝试自动转换时间戳失败:\n{e}")
                return

        # 修复 header 中的错误版本号
        import re

        def fix_xes_version(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 修正 pm4py 导出的旧版本号
            content = content.replace('xes.version="1849-2016"', 'xes.version="1.0"')
            # 用正则去除 xes.features="xxx"
            content = re.sub(r'\s?xes\.features="[^"]+"', '', content)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)




        # 若经过空值处理后数据为空, 则无法导出
        # 若经过空值处理后数据为空, 则无法导出
        if tmp_df.empty:
            QMessageBox.warning(self, "数据为空", "经过空值/格式清洗后, 数据集已为空, 无法导出XES。")
            return

        try:
            # 重命名为标准字段
            df_renamed = tmp_df.rename(columns={
                col_caseid: "case:concept:name",
                col_activity: "concept:name",
                col_timestamp: "time:timestamp"
            })
            # ❗关键：替换所有 NaN 为 None（防止 XES 导出 value="nan"）
            import numpy as np
            df_renamed = df_renamed.fillna("unknown")

            # 添加生命周期标记
            df_renamed["lifecycle:transition"] = "complete"

            # 转换为事件日志
            event_log = log_converter.apply(df_renamed, variant=log_converter.Variants.TO_EVENT_LOG)

            # 为每个 trace 添加必需属性
            for trace in event_log:
                if "concept:name" not in trace.attributes:
                    trace.attributes["concept:name"] = "missing_case"

            # 为每个事件补齐字段
            for trace in event_log:
                for event in trace:
                    if "concept:name" not in event:
                        event["concept:name"] = "undefined"
                    if "time:timestamp" not in event:
                        event["time:timestamp"] = pd.Timestamp.now()
                    if "lifecycle:transition" not in event:
                        event["lifecycle:transition"] = "complete"

            # 添加扩展信息
            # ✅ 清空后避免重复（关键！）
            if hasattr(event_log, "extensions") and isinstance(event_log.extensions, dict):
                event_log.extensions.clear()
                event_log.extensions["concept"] = {
                    "name": "Concept",
                    "prefix": "concept",
                    "uri": "http://www.xes-standard.org/concept.xesext"
                }
                event_log.extensions["time"] = {
                    "name": "Time",
                    "prefix": "time",
                    "uri": "http://www.xes-standard.org/time.xesext"
                }
                event_log.extensions["lifecycle"] = {
                    "name": "Lifecycle",
                    "prefix": "lifecycle",
                    "uri": "http://www.xes-standard.org/lifecycle.xesext"
                }

            # 添加全局属性
            event_log.global_trace_attributes = ["concept:name"]
            event_log.global_event_attributes = ["concept:name", "time:timestamp", "lifecycle:transition"]

            # ✅ 正确操作 classifiers（只调用 clear 和 extend，绝不会报错）
            # ✅ 正确操作 classifiers（适配你的 dict 结构）
            if hasattr(event_log, "classifiers"):
                if isinstance(event_log.classifiers, list):
                    event_log.classifiers.clear()
                    event_log.classifiers.append({
                        "name": "Activity classifier",
                        "keys": ["concept:name", "lifecycle:transition"]
                    })
                elif isinstance(event_log.classifiers, dict):
                    event_log.classifiers.clear()
                    event_log.classifiers["Activity classifier"] = ["concept:name", "lifecycle:transition"]

            # 设置其他元属性
            event_log.attributes["concept:name"] = "log"
            event_log.attributes["creator"] = "CPA_PM Python Tool"
            event_log.attributes["origin"] = "csv"

        except Exception as e:
            QMessageBox.critical(self, "转换失败", f"无法转换为事件日志:\n{e}")
            return

        # 导出为XES
        try:
            xes_exporter.apply(event_log, xes_file_path)
            fix_xes_version(xes_file_path)
            QMessageBox.information(self, "导出成功", f"已成功导出 XES 文件：\n{xes_file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"无法导出XES文件:\n{e}")

    def start_analysis(self):
        if self.df is None or self.df.empty:
            QMessageBox.information(self, "提示", "还没有有效数据，无法分析。")
            return

        try:
            # 字段重命名和转换
            df = self.df.copy()
            col_caseid = self.combo_caseid.currentText()
            col_activity = self.combo_activity.currentText()
            col_timestamp = self.combo_timestamp.currentText()

            df = df.rename(columns={
                col_caseid: "case:concept:name",
                col_activity: "concept:name",
                col_timestamp: "time:timestamp"
            })
            df["lifecycle:transition"] = "complete"

            import numpy as np
            df = df.fillna("unknown")

            from pm4py.objects.conversion.log import converter as log_converter
            event_log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)

            from process_analysis_window import launch_analysis_window
            launch_analysis_window(event_log)

        except Exception as e:
            QMessageBox.critical(self, "转换失败", f"无法进入分析阶段:\n{e}")


def main():
    import warnings
    # 如果想要隐藏可能来自PyQt5或pm4py的FutureWarning/DeprecationWarning，可在此抑制
    warnings.simplefilter("default", category=DeprecationWarning)
    # 或者 warnings.filterwarnings("ignore", category=DeprecationWarning)

    app = QApplication(sys.argv)
    window = CSV2XESConverter()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
