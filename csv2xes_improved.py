# csv2xes_improved.py  —— 修正版
import sys, os, re, pandas as pd, chardet
from typing import Dict, Callable
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QLabel, QPushButton, QComboBox,
    QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QMessageBox,
    QGroupBox, QGridLayout, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.util import dataframe_utils
from pm4py.objects.conversion.log import converter as log_converter

# ---------- 常量 ----------
PREVIEW_ROWS = 200

# ---------- 辅助 ----------
def clean_headers_unique(df: pd.DataFrame) -> pd.DataFrame:
    new_cols, seen = [], {}
    for col in df.columns:
        c = re.sub(r'[^0-9a-zA-Z_]+', '', col.strip().lower()) or "col"
        seen[c] = seen.get(c, 0) + 1
        new_cols.append(c if seen[c] == 1 else f"{c}_{seen[c]-1}")
    df.columns = new_cols; return df

TYPE_RULES: Dict[str, Callable[[pd.Series], pd.Series]] = {
    r'^-?\d+$'           : pd.to_numeric,
    r'^-?\d+\.\d+$'      : pd.to_numeric,
    r'^(true|false)$'    : lambda s: s.map({'true': True, 'false': False}),
    r'^(yes|no)$'        : lambda s: s.map({'yes': True, 'no': False}),
    r'^\d+(\.\d+)?%$'    : lambda s: pd.to_numeric(s.str.rstrip('%')) / 100,
    r'^\d{4}-\d{2}-\d{2}': pd.to_datetime
}
def smart_cast_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].dtype.kind in "biufcM": continue
        sample = df[col].dropna().astype(str).head(50)
        for pat, func in TYPE_RULES.items():
            if sample.str.match(pat).all():
                try: df[col] = func(df[col]); break
                except Exception: pass
        if df[col].nunique(dropna=True) <= 20:
            df[col] = df[col].astype("category")
    return df

def show_preview(tbl: QTableWidget, df: pd.DataFrame):
    tbl.clear()
    if df is None or df.empty:
        tbl.setRowCount(0); tbl.setColumnCount(0); return
    m, n = min(PREVIEW_ROWS, len(df)), len(df.columns)
    tbl.setRowCount(m); tbl.setColumnCount(n)
    tbl.setHorizontalHeaderLabels(df.columns.astype(str).tolist())
    for r in range(m):
        for c in range(n):
            tbl.setItem(r, c, QTableWidgetItem(str(df.iat[r, c])))

# ---------- 主窗口 ----------
class CSV2XESConverter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CSV → XES 预处理工具")
        self.resize(1050, 680)

        self.df_orig = None      # 原始数据（保持列全集）
        self.df_work = None      # 工作副本
        self.all_cols = []       # 原始列全集（始终不变，仅列名可能因清理而变）
        self.undo_stack = []

        self.build_ui()

    # ---- UI ----
    def build_ui(self):
        cw = QWidget(self); self.setCentralWidget(cw)
        out = QVBoxLayout(cw)

        # 文件栏
        bar = QHBoxLayout()
        self.lab_file = QLabel("未加载文件")
        btn_open = QPushButton("浏览…"); btn_open.clicked.connect(self.open_file)
        bar.addWidget(self.lab_file); bar.addStretch(); bar.addWidget(btn_open)
        out.addLayout(bar)

        # 预览
        self.tbl = QTableWidget(editTriggers=QTableWidget.NoEditTriggers)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        out.addWidget(self.tbl)

        # 映射 / 时间
        grp = QGroupBox("列映射与时间格式"); grid = QGridLayout(grp)
        self.cbo_case = QComboBox(); self.cbo_act = QComboBox(); self.cbo_time = QComboBox()
        grid.addWidget(QLabel("CaseID"), 0, 0); grid.addWidget(self.cbo_case, 0, 1)
        grid.addWidget(QLabel("Activity"),1, 0); grid.addWidget(self.cbo_act, 1, 1)
        grid.addWidget(QLabel("Timestamp"),2,0); grid.addWidget(self.cbo_time,2, 1)
        self.cbo_fmt = QComboBox(editable=True)
        self.cbo_fmt.addItems([
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y_%H:%M",          # 新增
            "%Y-%m-%d %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y.%m.%d %H:%M:%S",
            "自动检测"
        ])
        grid.addWidget(QLabel("原时间格式"),3,0); grid.addWidget(self.cbo_fmt,3,1)
        out.addWidget(grp)

        # 保留列
        out.addWidget(QLabel("保留列（除三主列外，内容固定，勾选=保留）"))
        self.lst = QListWidget(selectionMode=QListWidget.MultiSelection, maximumHeight=160)
        out.addWidget(self.lst)

        # 按钮
        btn_row = QHBoxLayout()
        btns = {
            "撤销":      self.undo,
            "应用列选择": self.apply_cols,
            "清理列标题": self.clean_headers,
            "清理时间格式":self.clean_time,
            "按 Case+Time 排序": self.sort_case_time,
            "类型转换":  self.cast_types,
            "导出 XES": self.export_xes,
            "开始分析":  self.analyse
        }
        for t,f in btns.items():
            b = QPushButton(t); b.clicked.connect(f); btn_row.addWidget(b)
        btn_row.addStretch(); out.addLayout(btn_row)

    # ---- 文件 ----
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 CSV", os.getcwd(), "CSV (*.csv)")
        if not path: return
        try:
            self.df_orig = pd.read_csv(path, engine="pyarrow", low_memory=True)
        except UnicodeDecodeError:
            with open(path,'rb') as fh:
                enc = chardet.detect(fh.read(200_000))['encoding'] or 'utf-8'
            self.df_orig = pd.read_csv(path, encoding=enc, low_memory=False)
        except Exception as e:
            QMessageBox.critical(self,"加载失败",str(e)); return

        self.df_work = self.df_orig.copy()
        self.all_cols = self.df_orig.columns.tolist()
        self.lab_file.setText(os.path.basename(path))
        self.refresh_ui()

    # ---- UI 刷新 ----
    def refresh_ui(self):
        if self.df_work is None: return
        cols = self.all_cols

        # 下拉映射
        for cbo in (self.cbo_case, self.cbo_act, self.cbo_time):
            cbo.blockSignals(True); cbo.clear(); cbo.addItems(cols); cbo.blockSignals(False)
        self.auto_map(cols)

        # 保留列列表（内容固定）
        self.lst.blockSignals(True); self.lst.clear()
        mains = {self.cbo_case.currentText(), self.cbo_act.currentText(), self.cbo_time.currentText()}
        for c in cols:
            if c in mains: continue
            item = QListWidgetItem(c)
            item.setSelected(c in self.df_work.columns)   # 勾选状态=当前是否保留
            self.lst.addItem(item)
        self.lst.blockSignals(False)

        show_preview(self.tbl, self.df_work)

    def auto_map(self, cols):
        def pick(keys, target):
            for k in keys:
                for c in cols:
                    if k in c.lower(): target.setCurrentText(c); return
        pick(("case","case_id","company"), self.cbo_case)
        pick(("event","activity"), self.cbo_act)
        pick(("time","date","timestamp"), self.cbo_time)

    # ---- Undo ----
    def push_undo(self):
        if self.df_work is not None:
            self.undo_stack.append(self.df_work.copy())
    def undo(self):
        if not self.undo_stack:
            QMessageBox.information(self,"提示","无可撤销"); return
        self.df_work = self.undo_stack.pop(); self.refresh_ui()

    # ---- 功能 ----
    def apply_cols(self):
        if self.df_work is None: return
        mains = [self.cbo_case.currentText(), self.cbo_act.currentText(), self.cbo_time.currentText()]
        keep  = mains + [i.text() for i in self.lst.selectedItems()]
        keep  = list(dict.fromkeys(keep))  # 去重保持顺序
        self.push_undo(); self.df_work = self.df_orig[keep].copy()
        self.refresh_ui()                  # 仅勾选状态变化，列表内容不变

    def clean_headers(self):
        if self.df_work is None: return
        self.push_undo()
        self.df_work = clean_headers_unique(self.df_work)
        # 同步原始副本与列全集
        self.df_orig = self.df_work.copy()
        self.all_cols = self.df_work.columns.tolist()
        self.refresh_ui()

    def clean_time(self):
        if self.df_work is None: return
        ts = self.cbo_time.currentText()
        if not ts: QMessageBox.warning(self,"缺少映射","请先指定 Timestamp 列"); return
        fmt = self.cbo_fmt.currentText().strip()
        self.push_undo()
        try:
            if fmt in ("","自动检测"):
                self.df_work = dataframe_utils.convert_timestamp_columns_in_df(self.df_work,[ts])
            else:
                self.df_work[ts] = pd.to_datetime(self.df_work[ts], format=fmt)
        except Exception as e:
            QMessageBox.critical(self,"时间解析失败",str(e)); return
        self.df_work[ts] = self.df_work[ts].dt.strftime("%Y-%m-%d %H:%M:%S")
        show_preview(self.tbl, self.df_work)   # 小刷新即可

    def sort_case_time(self):
        if self.df_work is None: return
        case, ts = self.cbo_case.currentText(), self.cbo_time.currentText()
        if not case or not ts:
            QMessageBox.warning(self,"映射缺失","请映射 Case 与 Timestamp"); return
        self.push_undo(); self.df_work.sort_values([case, ts], inplace=True)
        show_preview(self.tbl, self.df_work)

    def cast_types(self):
        if self.df_work is None: return
        self.push_undo(); self.df_work = smart_cast_columns(self.df_work)
        show_preview(self.tbl, self.df_work)
        QMessageBox.information(self,"完成","已尝试类型转换")

    # ---- Export / Analyse ----
    def export_xes(self):
        if self.df_work is None or self.df_work.empty:
            QMessageBox.warning(self,"提示","无数据可导出"); return
        case, act, ts = self.cbo_case.currentText(), self.cbo_act.currentText(), self.cbo_time.currentText()
        if "" in (case, act, ts):
            QMessageBox.warning(self,"提示","映射未完成"); return
        save, _ = QFileDialog.getSaveFileName(self,"保存 XES", os.getcwd(),"XES (*.xes)")
        if not save: return
        if not save.lower().endswith(".xes"): save += ".xes"
        df = self.df_work.rename(columns={case:"case:concept:name", act:"concept:name", ts:"time:timestamp"})
        df["lifecycle:transition"]="complete"; df.fillna("unknown", inplace=True)
        try:
            log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
            xes_exporter.apply(log, save)
            QMessageBox.information(self,"成功",f"已导出：\n{save}")
        except Exception as e:
            QMessageBox.critical(self,"导出失败",str(e))

    def analyse(self):
        if self.df_work is None or self.df_work.empty:
            QMessageBox.warning(self,"提示","无数据"); return
        case, act, ts = self.cbo_case.currentText(), self.cbo_act.currentText(), self.cbo_time.currentText()
        df = self.df_work.rename(columns={case:"case:concept:name", act:"concept:name", ts:"time:timestamp"})
        df["lifecycle:transition"]="complete"; df.fillna("unknown", inplace=True)
        try:
            log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
            from process_analysis_window import launch_analysis_window
            launch_analysis_window(log)
        except Exception as e:
            QMessageBox.critical(self,"分析入口错误",str(e))

# ---- 入口 ----
def main():
    import warnings; warnings.filterwarnings("ignore")
    app = QApplication(sys.argv); win = CSV2XESConverter(); win.show(); sys.exit(app.exec_())
if __name__ == "__main__":
    main()
