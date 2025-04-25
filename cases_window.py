# cases_window.py
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QSplitter, QTableWidget, QTableWidgetItem
)
from PyQt5.QtCore import Qt
import pandas as pd
from typing import Dict
from cases_utils import extract_variants, get_case_event_details

class CasesWindow(QWidget):
    def __init__(self, df: pd.DataFrame, col_mapping: Dict[str, str]):
        super().__init__()
        self.setWindowTitle("查看 Cases")
        self.resize(1100, 700)
        self.df_raw = df
        self.col_mapping = col_mapping
        self.case_col = "case:concept:name"
        self.act_col = "concept:name"
        self.time_col = "time:timestamp"
        self.case_col_raw = self.col_mapping.get(self.case_col, self.case_col)
        self.act_col_raw = self.col_mapping.get(self.act_col, self.act_col)
        self.time_col_raw = self.col_mapping.get(self.time_col, self.time_col)
        self.variants_map, self.case_events_map = extract_variants(df, self.case_col, self.act_col, self.time_col)
        self.init_ui()
        self.showMaximized()

    def init_ui(self):
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        self.lst_variants = QListWidget()
        self.lst_cases = QListWidget()
        self.tbl_events = QTableWidget()
        self.tbl_events.setColumnCount(0)
        self.tbl_events.setRowCount(0)
        self.lst_variants.currentItemChanged.connect(self.on_variant_selected)
        self.lst_cases.currentItemChanged.connect(self.on_case_selected)
        splitter.addWidget(self.lst_variants)
        splitter.addWidget(self.lst_cases)
        splitter.addWidget(self.tbl_events)
        splitter.setSizes([200, 200, 700])
        layout.addWidget(splitter)
        self.load_variants()

    def load_variants(self):
        # 对变体排序：按其事件数总量（所有 cases 的 event 总和）降序
        variant_stats = []
        for variant, case_ids in self.variants_map.items():
            total_events = sum(len(self.case_events_map[case_id]) for case_id in case_ids)
            variant_stats.append((variant, case_ids, total_events))
        variant_stats.sort(key=lambda x: x[2], reverse=True)

        self.lst_variants.clear()
        for i, (variant, case_ids, total_events) in enumerate(variant_stats, start=1):
            case_pct = 100 * len(case_ids) / len(self.case_events_map)
            item = QListWidgetItem(f"Variant {i} | Cases: {len(case_ids)} ({case_pct:.1f}%) | Events: {total_events}")
            item.setData(Qt.UserRole, variant)
            self.lst_variants.addItem(item)

        # 默认选中第一个变体并展开其第一个 case
        if self.lst_variants.count() > 0:
            self.lst_variants.setCurrentRow(0)

    def on_variant_selected(self, current, _prev):
        if not current:
            return
        variant = current.data(Qt.UserRole)
        case_ids = self.variants_map.get(variant, [])
        self.lst_cases.clear()
        self.tbl_events.clear()
        for case_id in case_ids:
            item = QListWidgetItem(case_id)
            self.lst_cases.addItem(item)
        # 默认选中第一个 case
        if self.lst_cases.count() > 0:
            self.lst_cases.setCurrentRow(0)

    def on_case_selected(self, current, _prev):
        if not current:
            return
        case_id = current.text()
        df_case = get_case_event_details(self.df_raw, case_id, self.case_col, self.time_col)
        self.show_event_table(df_case)

    def show_event_table(self, df: pd.DataFrame):
        # 将三大主列优先显示
        raw_cols = list(self.df_raw.columns)
        main_cols = [self.case_col_raw, self.act_col_raw, self.time_col_raw]
        other_cols = [col for col in raw_cols if col not in main_cols]
        display_cols = main_cols + other_cols

        if "lifecycle:transition" in display_cols:
            display_cols.remove("lifecycle:transition")
        df = df[display_cols].sort_values(by=self.time_col)
        self.tbl_events.setRowCount(len(df))
        self.tbl_events.setColumnCount(len(display_cols))
        headers = [self.col_mapping.get(col, col) for col in display_cols]
        self.tbl_events.setHorizontalHeaderLabels(headers)
        for r in range(len(df)):
            for c, col in enumerate(display_cols):
                item = QTableWidgetItem(str(df.iloc[r, c]))
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.tbl_events.setItem(r, c, item)
        self.tbl_events.resizeColumnsToContents()
