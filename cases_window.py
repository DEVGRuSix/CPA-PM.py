# cases_window.py
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QSplitter, QTableWidget, QTableWidgetItem
)
from PyQt5.QtCore import Qt, QSize
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
        self.lst_variants.clear()

        # 添加表头
        header = QListWidgetItem(f"Variants ({len(self.variants_map)})")
        header.setFlags(Qt.NoItemFlags)
        self.lst_variants.addItem(header)

        # 计算事件总数
        total_events = sum(len(events) for events in self.case_events_map.values())

        # 构建并排序
        variant_stats = []
        for variant, case_ids in self.variants_map.items():
            event_count = sum(len(self.case_events_map[case_id]) for case_id in case_ids)
            variant_stats.append((variant, case_ids, event_count))

        # 排序：先按 case 数降序，再按事件数占比降序
        variant_stats.sort(key=lambda x: (-len(x[1]), -x[2]))

        for i, (variant, case_ids, event_count) in enumerate(variant_stats, start=1):
            case_count = len(case_ids)
            percent = 100 * event_count / total_events if total_events > 0 else 0
            text = f"Variant {i}\n{case_count} cases ({percent:.1f}%)\n{event_count} events"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, variant)
            item.setSizeHint(QSize(200, 60))  # 三行显示
            self.lst_variants.addItem(item)

        # 默认选中第一个变体
        if self.lst_variants.count() > 1:
            self.lst_variants.setCurrentRow(1)

    def on_variant_selected(self, current, _prev):
        if not current or not current.data(Qt.UserRole):
            return
        variant = current.data(Qt.UserRole)
        case_ids = self.variants_map.get(variant, [])
        self.lst_cases.clear()
        self.tbl_events.clear()

        # 添加 case 列表标题
        header = QListWidgetItem(f"Cases ({len(case_ids)})")
        header.setFlags(Qt.NoItemFlags)
        self.lst_cases.addItem(header)

        for case_id in case_ids:
            num_events = len(self.case_events_map.get(case_id, []))
            item = QListWidgetItem(f"{case_id}\n{num_events} events")
            item.setData(Qt.UserRole, case_id)
            item.setSizeHint(QSize(200, 44))
            self.lst_cases.addItem(item)

        # 默认选中第一个 case
        if self.lst_cases.count() > 1:
            self.lst_cases.setCurrentRow(1)

    def on_case_selected(self, current, _prev):
        if not current or not current.data(Qt.UserRole):
            return
        case_id = current.data(Qt.UserRole)
        df_case = get_case_event_details(self.df_raw, case_id, self.case_col, self.time_col)
        self.show_event_table(df_case)

    def show_event_table(self, df: pd.DataFrame):
        display_cols = [self.act_col_raw, self.time_col_raw] + [
            col for col in df.columns if col not in [
                self.case_col_raw, self.act_col_raw, self.time_col_raw, "lifecycle:transition"
            ]
        ]
        df = df.sort_values(by=self.time_col_raw)

        # 拆分 Date 和 Time
        df["__date__"] = pd.to_datetime(df[self.time_col_raw]).dt.date.astype(str)
        df["__time__"] = pd.to_datetime(df[self.time_col_raw]).dt.time.astype(str)

        # 构建最终列顺序
        final_cols = ["__date__", "__time__"] + [col for col in display_cols if col not in [self.time_col_raw]]
        headers = ["Date", "Time"] + [
            "Activity" if col == self.act_col_raw else self.col_mapping.get(col, col) for col in final_cols[2:]
        ]

        self.tbl_events.setRowCount(len(df))
        self.tbl_events.setColumnCount(len(final_cols))
        self.tbl_events.setHorizontalHeaderLabels(headers)

        for r in range(len(df)):
            for c, col in enumerate(final_cols):
                val = str(df.iloc[r][col])
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.tbl_events.setItem(r, c, item)

        self.tbl_events.resizeColumnsToContents()

