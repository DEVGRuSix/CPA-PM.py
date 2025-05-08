# csv2xes_improved.py  —— 修正版
import sys, os, re, pandas as pd, chardet
from typing import Dict, Callable
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QLabel, QPushButton, QComboBox,
    QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QMessageBox,
    QGroupBox, QGridLayout, QListWidget, QListWidgetItem, QSizePolicy, QProgressDialog, QDialog
)
from PyQt5.QtCore import Qt, QTimer
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.util import dataframe_utils
from pm4py.objects.conversion.log import converter as log_converter

# ---------- 常量 ----------
PREVIEW_ROWS = 200

# ---------- 辅助 ----------
def clean_headers_unique(df: pd.DataFrame) -> pd.DataFrame:
    """去除列名空格/特殊字符并转小写，确保唯一"""
    new_cols, seen = [], {}
    for col in df.columns:
        c = re.sub(r'[^0-9a-zA-Z_]+', '', col.strip().lower()) or "col"
        seen[c] = seen.get(c, 0) + 1
        new_cols.append(c if seen[c] == 1 else f"{c}_{seen[c]-1}")
    df.columns = new_cols
    return df

TYPE_RULES: Dict[str, Callable[[pd.Series], pd.Series]] = {
    r'^-?\d+$'           : pd.to_numeric,
    r'^-?\d+\.\d+$'      : pd.to_numeric,
    r'^(true|false)$'    : lambda s: s.map({'true': True, 'false': False}),
    r'^(yes|no)$'        : lambda s: s.map({'yes': True, 'no': False}),
    r'^\d+(\.\d+)?%$'    : lambda s: pd.to_numeric(s.str.rstrip('%')) / 100,
    r'^\d{4}-\d{2}-\d{2}': pd.to_datetime
}
def smart_cast_columns(df: pd.DataFrame) -> pd.DataFrame:
    """智能类型转换"""
    for col in df.columns:
        if df[col].dtype.kind in "biufcM":
            continue
        sample = df[col].dropna().astype(str).head(50)
        for pat, func in TYPE_RULES.items():
            if sample.str.match(pat).all():
                try:
                    df[col] = func(df[col])
                except Exception:
                    pass
                break
        if df[col].nunique(dropna=True) <= 20:
            df[col] = df[col].astype("category")
    return df

def show_preview(tbl: QTableWidget, df: pd.DataFrame):
    """在预览表格中显示前 PREVIEW_ROWS 行"""
    tbl.clear()
    if df is None or df.empty:
        tbl.setRowCount(0)
        tbl.setColumnCount(0)
        return
    m, n = min(PREVIEW_ROWS, len(df)), len(df.columns)
    tbl.setRowCount(m)
    tbl.setColumnCount(n)
    tbl.setHorizontalHeaderLabels(df.columns.astype(str).tolist())
    for r in range(m):
        for c in range(n):
            tbl.setItem(r, c, QTableWidgetItem(str(df.iat[r, c])))
    tbl.resizeColumnsToContents()  # 自动调整列宽

class ProcessingDialog(QDialog):
    def __init__(self, parent=None, message="正在处理..."):
        super().__init__(parent)
        self.setWindowTitle("请稍候")
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedSize(200, 80)

        label = QLabel(message, self)
        label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(label)
        self.setLayout(layout)


# ---------- 主窗口 ----------
class CSV2XESConverter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CSV → XES 预处理工具")
        self.resize(1050, 680)

        self.df_orig = None      # 原始数据
        self.df_work = None      # 工作副本
        self.all_cols = []       # 原始列全集
        self.undo_stack = []
        # 保存当前在复选栏中选中的额外列
        self.selected_extra_cols = []

        self.build_ui()

    # ---- UI 构建 ----
    def build_ui(self):
        cw = QWidget(self)
        self.setCentralWidget(cw)
        out = QVBoxLayout(cw)

        # 文件栏
        bar = QHBoxLayout()
        self.lab_file = QLabel("未加载文件")
        btn_open = QPushButton("浏览…")
        btn_open.clicked.connect(self.open_file)
        bar.addWidget(self.lab_file)
        bar.addStretch()
        bar.addWidget(btn_open)
        out.addLayout(bar)

        # 预览表格
        self.tbl = QTableWidget(editTriggers=QTableWidget.NoEditTriggers)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        out.addWidget(self.tbl)

        # 列映射与时间格式
        # 列映射与时间格式 —— 左Label + 右控件整体右对齐
        grp = QGroupBox("列映射与时间格式")
        vbox_all = QVBoxLayout(grp)

        def make_right_aligned_row(label_text, widget1, widget2=None):
            row = QHBoxLayout()

            # Label：左对齐、固定宽度
            lbl = QLabel(label_text)
            lbl.setFixedWidth(90)
            lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            row.addWidget(lbl)

            row.addStretch()  # 控件整体右对齐的关键

            if widget2 is None:
                widget1.setFixedWidth(300)
                widget1.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                row.addWidget(widget1, alignment=Qt.AlignRight)
            else:
                widget1.setFixedWidth(190)
                widget2.setFixedWidth(100)

                # 控件组合区（不使用额外 QWidget，直接用 Layout 放进去）
                hbox_controls = QHBoxLayout()
                hbox_controls.setContentsMargins(0, 0, 0, 0)  # 防止边缘间距撑开
                hbox_controls.setSpacing(10)
                hbox_controls.addStretch()  # 控件组合整体右对齐
                hbox_controls.addWidget(widget1)
                hbox_controls.addWidget(widget2)

                row.addLayout(hbox_controls)  # 不用 QWidget，直接加进去

            return row

        # ---- 控件初始化 ----
        self.cbo_case = QComboBox()
        self.cbo_act = QComboBox()
        self.cbo_time = QComboBox()

        self.cbo_fmt = QComboBox(editable=True)
        self.cbo_fmt.addItems([
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y_%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y.%m.%d %H:%M:%S",
            "自动检测"
        ])
        self.btn_clean_time = QPushButton("清理时间格式")
        self.btn_clean_time.clicked.connect(self.clean_time)

        # ---- 构建每行 ----
        vbox_all.addLayout(make_right_aligned_row("CaseID", self.cbo_case))
        vbox_all.addLayout(make_right_aligned_row("Activity", self.cbo_act))
        vbox_all.addLayout(make_right_aligned_row("Timestamp", self.cbo_time))
        vbox_all.addLayout(make_right_aligned_row("原时间格式", self.cbo_fmt, self.btn_clean_time))

        out.addWidget(grp)

        # 保留列复选栏（除三主列外，内容固定，选中=保留）
        out.addWidget(QLabel("保留列（选中后参与导出与分析）"))
        self.lst = QListWidget(selectionMode=QListWidget.MultiSelection, maximumHeight=160)
        out.addWidget(self.lst)

        # 底部按钮行
        btn_row = QHBoxLayout()
        btns = {
            "撤销":        self.undo,
            "应用列选择":  self.apply_cols,
            "按 Case+Time 排序": self.sort_case_time,
            "类型转换":    self.cast_types,
            "导出 XES":    self.export_xes,
            "开始分析":    self.analyse
        }
        for text, func in btns.items():
            b = QPushButton(text)
            b.clicked.connect(func)
            btn_row.addWidget(b)
        btn_row.addStretch()
        out.addLayout(btn_row)

    # ---- 文件处理 ----
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", os.getcwd(), "CSV/XES (*.csv *.xes)")

        if not path:
            return
        import tempfile

        try:
            if path.lower().endswith(".xes"):
                from pm4py.objects.log.importer.xes import importer as xes_importer
                from pm4py.objects.log.util import dataframe_utils

                # 读取 XES 文件
                log = xes_importer.apply(path)
                df = log_converter.apply(log, variant=log_converter.Variants.TO_DATA_FRAME)

                # 创建临时 CSV 文件
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
                df.to_csv(temp_file.name, index=False)
                path = temp_file.name  # 更新路径为临时 CSV 文件

            # 使用更新的路径加载 CSV
            df = pd.read_csv(path, engine="pyarrow", low_memory=True)

        except UnicodeDecodeError:
            with open(path, 'rb') as fh:
                enc = chardet.detect(fh.read(200_000))['encoding'] or 'utf-8'
            df = pd.read_csv(path, encoding=enc, low_memory=False)
        except Exception as e:
            QMessageBox.critical(self, "加载失败", str(e))
            return

        # 自动清理列标题
        df = clean_headers_unique(df)

        self.df_orig = df
        self.df_work = df.copy()
        self.all_cols = df.columns.tolist()
        self.lab_file.setText(os.path.basename(path))
        self.selected_extra_cols = []  # 重置复选状态
        self.refresh_ui()

    # ---- UI 刷新 ----
    def refresh_ui(self):
        if self.df_work is None:
            return
        cols = self.all_cols
        mains = {
            self.cbo_case.currentText(),
            self.cbo_act.currentText(),
            self.cbo_time.currentText()
        }

        # 刷新下拉映射
        for cbo in (self.cbo_case, self.cbo_act, self.cbo_time):
            cbo.blockSignals(True)
            cbo.clear()
            cbo.addItems(cols)
            cbo.blockSignals(False)
        self.auto_map(cols)

        # 刷新保留列列表，仅剩余列可选
        self.lst.blockSignals(True)
        self.lst.clear()
        mains = {self.cbo_case.currentText(), self.cbo_act.currentText(), self.cbo_time.currentText()}
        for c in cols:
            if c in mains:
                continue
            item = QListWidgetItem(c)
            item.setSelected(c in self.selected_extra_cols)
            self.lst.addItem(item)
        self.lst.blockSignals(False)

        # 预览
        show_preview(self.tbl, self.df_work)

    def auto_map(self, cols):
        def pick(keys, target):
            for k in keys:
                for c in cols:
                    if k in c.lower():
                        target.setCurrentText(c)
                        return
        pick(("case","case_id","company"), self.cbo_case)
        pick(("event","activity"), self.cbo_act)
        pick(("time","date","timestamp"), self.cbo_time)

    # ---- 撤销 ----
    def push_undo(self):
        if self.df_work is not None:
            self.undo_stack.append(self.df_work.copy())

    def undo(self):
        if not self.undo_stack:
            QMessageBox.information(self, "提示", "无可撤销")
            return
        self.df_work = self.undo_stack.pop()
        self.refresh_ui()

    # ---- 核心功能 ----
    def apply_cols(self):
        if self.df_work is None:
            return
        mains = [
            self.cbo_case.currentText(),
            self.cbo_act.currentText(),
            self.cbo_time.currentText()
        ]
        # 记录当前复选栏选中的额外列
        self.selected_extra_cols = [item.text() for item in self.lst.selectedItems()]
        keep = mains + self.selected_extra_cols

        self.push_undo()
        # 保留清洗结果 + 加入新列
        cleaned_cols = [col for col in keep if col in self.df_work.columns]
        new_cols = [col for col in keep if col not in self.df_work.columns]
        self.df_work = pd.concat([
            self.df_work[cleaned_cols],
            self.df_orig[new_cols]
        ], axis=1)

        # 只更新预览表格，保留复选框选中状态
        show_preview(self.tbl, self.df_work)

    def clean_time(self):
        """清理/转换时间列格式，并删除非法时间记录，保持为 datetime 类型"""
        if self.df_work is None:
            return

        ts = self.cbo_time.currentText()
        if not ts:
            QMessageBox.warning(self, "缺少映射", "请先指定 Timestamp 列")
            return

        fmt = self.cbo_fmt.currentText().strip()
        self.push_undo()

        try:
            if fmt in ("", "自动检测"):
                self.df_work = dataframe_utils.convert_timestamp_columns_in_df(self.df_work, [ts])
                self.df_work[ts] = pd.to_datetime(self.df_work[ts], errors="coerce")
            else:
                self.df_work[ts] = pd.to_datetime(self.df_work[ts], format=fmt, errors="coerce")

            # 记录非法时间行数
            n_invalid = self.df_work[ts].isna().sum()
            self.df_work = self.df_work[self.df_work[ts].notna()].copy()

            self.cbo_fmt.setCurrentText("%Y-%m-%d %H:%M:%S")  # ✅ 标明最终格式

            show_preview(self.tbl, self.df_work)
            msg = f"已清理时间格式，统一为 datetime 类型"
            if n_invalid > 0:
                msg += f"\n并删除了 {n_invalid} 条无法解析的记录"
            QMessageBox.information(self, "时间清洗完成", msg)

        except Exception as e:
            self.undo()
            QMessageBox.critical(self, "时间解析失败", str(e))

    def sort_case_time(self):
        if self.df_work is None:
            return
        case, ts = self.cbo_case.currentText(), self.cbo_time.currentText()
        if not case or not ts:
            QMessageBox.warning(self, "映射缺失", "请映射 Case 与 Timestamp")
            return
        self.push_undo()
        self.df_work.sort_values([case, ts], inplace=True)
        show_preview(self.tbl, self.df_work)

    def cast_types(self):
        if self.df_work is None:
            return
        self.push_undo()
        self.df_work = smart_cast_columns(self.df_work)
        show_preview(self.tbl, self.df_work)
        QMessageBox.information(self, "完成", "已尝试类型转换")

    # ---- 导出 / 分析 ----
    def export_xes(self):
        if self.df_work is None or self.df_work.empty:
            QMessageBox.warning(self, "提示", "无数据可导出")
            return
        case, act, ts = (
            self.cbo_case.currentText(),
            self.cbo_act.currentText(),
            self.cbo_time.currentText()
        )
        if "" in (case, act, ts):
            QMessageBox.warning(self, "提示", "映射未完成")
            return
        save, _ = QFileDialog.getSaveFileName(self, "保存 XES", os.getcwd(), "XES (*.xes)")
        if not save:
            return
        if not save.lower().endswith(".xes"):
            save += ".xes"
        df = self.df_work.rename(columns={
            case: "case:concept:name",
            act:  "concept:name",
            ts:   "time:timestamp"
        })
        df["lifecycle:transition"] = "complete"
        df.fillna("unknown", inplace=True)
        try:
            log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
            xes_exporter.apply(log, save)
            QMessageBox.information(self, "成功", f"已导出：\n{save}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def analyse(self):
        if self.df_work is None or self.df_work.empty:
            QMessageBox.warning(self, "提示", "无数据")
            return

        case, act, ts = (
            self.cbo_case.currentText(),
            self.cbo_act.currentText(),
            self.cbo_time.currentText()
        )
        df = self.df_work.rename(columns={
            case: "case:concept:name",
            act: "concept:name",
            ts: "time:timestamp"
        })

        # ✅ 再次确保时间字段为 datetime（防止用户没点“清理时间格式”按钮）
        try:
            df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
            df = df[df["time:timestamp"].notna()]
        except Exception as e:
            QMessageBox.critical(self, "时间字段错误", str(e))
            return

        df["lifecycle:transition"] = "complete"
        df.fillna("unknown", inplace=True)

        # 显示“正在处理”弹窗
        dlg = ProcessingDialog(self)
        dlg.show()

        def do_analysis():
            try:
                log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
                from process_analysis_window import launch_analysis_window

                col_mapping = {
                    "case:concept:name": case,
                    "concept:name": act,
                    "time:timestamp": ts
                }
                analysis_win = launch_analysis_window(log, col_mapping)

                analysis_win.raise_()
            except Exception as e:
                QMessageBox.critical(self, "分析入口错误", str(e))
            finally:
                dlg.close()
                self.showMinimized()

        QTimer.singleShot(100, do_analysis)


# ---- 入口 ----
def main():
    import warnings
    warnings.filterwarnings("ignore")
    app = QApplication(sys.argv)
    win = CSV2XESConverter()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
