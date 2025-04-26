from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QTextEdit
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from datetime import timedelta
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei']  # 中文字体
matplotlib.rcParams['axes.unicode_minus'] = False    # 正确显示负号

class StatisticWindow(QMainWindow):
    def __init__(self, df, threshold_min1=None, threshold_min2=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("统计指标结果")
        self.resize(800, 600)
        self.threshold_min1 = threshold_min1
        self.threshold_min2 = threshold_min2

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 时间阈值范围标题
        if threshold_min1 and threshold_min2:
            desc = f"分析范围：{threshold_min1}分钟 ~ {threshold_min2}分钟"
        elif threshold_min1:
            desc = f"分析范围：≤ {threshold_min1}分钟"
        elif threshold_min2:
            desc = f"分析范围：≤ {threshold_min2}分钟"
        else:
            desc = "分析范围：全部"

        range_label = QLabel(desc)
        layout.addWidget(range_label)

        # 图表
        fig = Figure(figsize=(5, 3))
        self.canvas = FigureCanvas(fig)
        self.ax = fig.add_subplot(111)
        layout.addWidget(self.canvas)

        # 统计文本
        self.text_box = QTextEdit()
        self.text_box.setReadOnly(True)
        layout.addWidget(self.text_box)

        self.setCentralWidget(widget)

        # 生成内容
        self.plot_weekday_distribution(df)
        self.generate_statistics(df)

    def plot_weekday_distribution(self, df):
        weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekday_map = {
            'Monday': '星期一', 'Tuesday': '星期二', 'Wednesday': '星期三',
            'Thursday': '星期四', 'Friday': '星期五',
            'Saturday': '星期六', 'Sunday': '星期日'
        }
        df_counts = df.groupby('weekday')["case:concept:name"].nunique()
        df_counts = df_counts.reindex(weekday_order).fillna(0)

        zh_labels = [weekday_map.get(day, day) for day in df_counts.index]
        self.ax.clear()
        self.ax.bar(zh_labels, df_counts.values, color='skyblue')
        self.ax.set_title("每周转化分布")
        self.ax.set_ylabel("流程数")
        self.canvas.draw()

    def generate_statistics(self, df):
        from pandas import to_datetime
        from collections import Counter

        df["time:timestamp"] = to_datetime(df["time:timestamp"], errors="coerce")
        df = df.dropna(subset=["time:timestamp"])

        durations = df.groupby("case:concept:name")["time:timestamp"].agg(lambda x: (x.max() - x.min()).total_seconds())
        total = len(durations)

        if total == 0:
            self.text_box.setText("⚠️ 没有流程数据。")
            return

        desc = ""

        # --- 📊 流程时长划分 ---
        if self.threshold_min1 and self.threshold_min2:
            min1_sec = self.threshold_min1 * 60
            min2_sec = self.threshold_min2 * 60
            count_low = (durations <= min1_sec).sum()
            count_mid = ((durations > min1_sec) & (durations <= min2_sec)).sum()
            count_high = (durations > min2_sec).sum()

            desc += "📊 流程时长划分：\n"
            desc += f"  - ≤{self.threshold_min1}分钟: {count_low} ({count_low / total:.1%})\n"
            desc += f"  - {self.threshold_min1}～{self.threshold_min2}分钟: {count_mid} ({count_mid / total:.1%})\n"
            desc += f"  - >{self.threshold_min2}分钟: {count_high} ({count_high / total:.1%})\n\n"
        elif self.threshold_min1:
            cutoff = self.threshold_min1 * 60
            count_low = (durations <= cutoff).sum()
            count_high = (durations > cutoff).sum()

            desc += "📊 流程时长划分：\n"
            desc += f"  - ≤{self.threshold_min1}分钟: {count_low} ({count_low / total:.1%})\n"
            desc += f"  - >{self.threshold_min1}分钟: {count_high} ({count_high / total:.1%})\n\n"
        else:
            desc += "📊 无有效时间划分，仅展示其他信息。\n\n"

        # --- 🔝 最常出现的活动 ---
        activities = df["concept:name"].dropna().tolist()
        act_counter = Counter(activities)
        top_activities = act_counter.most_common(5)

        if top_activities:
            desc += "🔝 最常出现的活动（前5名）：\n"
            for act, count in top_activities:
                desc += f"  📍 {act} ({count}次)\n"
            desc += "\n"
        else:
            desc += "🔝 未找到高频活动。\n\n"

        # --- ⏱️ 最长流程 ---
        max_dur = durations.max()
        max_case = durations.idxmax()
        from datetime import timedelta
        max_desc = str(timedelta(seconds=int(max_dur)))

        desc += f"⏱️ 最长流程:\n  📍 {max_case}\n  📍 持续时间: {max_desc}"

        self.text_box.setText(desc)

