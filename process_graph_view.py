import networkx as nx
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPathItem, QGraphicsItem,
    QGraphicsTextItem, QDialog, QLabel, QVBoxLayout
)
from PyQt5.QtGui import (
    QPen, QBrush, QColor, QFont, QPainter, QFontMetrics, QPainterPath, QPolygonF
)
from PyQt5.QtCore import Qt, QPointF

from pm4py.algo.discovery.dfg import algorithm as dfg_discovery
from networkx.drawing.nx_pydot import graphviz_layout

import re
from collections import Counter
import math


def sanitize_label(label):
    """
    将活动名里的特殊字符转成下划线，以便 graphviz 识别。
    """
    return re.sub(r'[^a-zA-Z0-9_]', '_', str(label))


class ProcessGraphView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.scene = QGraphicsScene()
        self.setScene(self.scene)

        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        self.scale(1.0, 1.0)

    def draw_from_event_log(self, event_log, act_percent=100, edge_percent=100):
        """
        主绘图函数：读入日志 -> 构建DFG -> 用graphviz布局节点 -> 在PyQt中绘制圆角矩形 + 贝塞尔曲线箭头
        """
        self.scene.clear()
        if not event_log:
            return

        dfg = dfg_discovery.apply(event_log)

        # ========== 统计活动频次 ==========
        activity_counts = {}
        for trace in event_log:
            for event in trace:
                act = event.get("concept:name", "undefined")
                activity_counts[act] = activity_counts.get(act, 0) + 1

        # ========== 构建有向图 ==========
        G = nx.DiGraph()
        label_map = {}

        # 添加 DFG 边
        for (src, tgt), freq in dfg.items():
            src_clean = sanitize_label(src)
            tgt_clean = sanitize_label(tgt)
            G.add_edge(src_clean, tgt_clean, weight=freq)
            label_map[src_clean] = src
            label_map[tgt_clean] = tgt

        # 单独添加没有出现在 DFG 边中的节点
        for act, freq in activity_counts.items():
            act_clean = sanitize_label(act)
            if not G.has_node(act_clean):
                G.add_node(act_clean)
            G.nodes[act_clean]["count"] = freq
            label_map[act_clean] = act

        # ========== 根据频次筛选活动 / 边 ==========
        act_freqs = sorted(activity_counts.items(), key=lambda x: x[1], reverse=True)
        keep_acts = set(
            sanitize_label(act) for act, _ in act_freqs[:max(1, len(act_freqs) * act_percent // 100)]
        )

        edge_freqs = sorted(dfg.items(), key=lambda x: x[1], reverse=True)
        keep_edges = set(
            (sanitize_label(src), sanitize_label(tgt))
            for (src, tgt), _ in edge_freqs[:max(1, len(edge_freqs) * edge_percent // 100)]
        )

        # ========== 用 graphviz_layout 获得节点坐标 ==========
        try:
            # 猜测最常见的“首活动”作为root，以便自上而下
            start_acts = [trace[0]['concept:name'] for trace in event_log if trace]
            most_common_start, _ = Counter(start_acts).most_common(1)[0]
            root_node = sanitize_label(most_common_start)

            # 我们想让 dot 做自上而下、且使用曲线、避免重叠
            G.graph['graph'] = {
                'rankdir': 'TB',
                'splines': 'curved',
                'overlap': 'false'
            }
            pos = graphviz_layout(G, prog='dot', root=root_node)

            # QGraphicsView坐标系 y轴向下递增，为了让图看起来从上到下不倒置，可选择把y取反
            # 这里根据需求可选：
            pos = {n: (x, -y) for n, (x, y) in pos.items()}

        except Exception as e:
            print("Graphviz layout failed, fallback to spring_layout:", e)
            pos = nx.spring_layout(G, scale=500, k=150)
            pos = {n: (x, -y) for n, (x, y) in pos.items()}

        # ========== 绘制边(用贝塞尔曲线 + 箭头) ==========
        for (src, tgt), weight in dfg.items():
            src_clean = sanitize_label(src)
            tgt_clean = sanitize_label(tgt)

            # 若该边不在保留列表，跳过
            if (src_clean, tgt_clean) not in keep_edges:
                continue
            # 节点不在保留列表时，也跳过
            if src_clean not in keep_acts or tgt_clean not in keep_acts:
                continue
            if src_clean not in pos or tgt_clean not in pos:
                continue

            (x1, y1) = pos[src_clean]
            (x2, y2) = pos[tgt_clean]

            # 构建三次贝塞尔曲线（简单地以中间点做控制）
            path = QPainterPath(QPointF(x1, y1))
            ctrl_x = (x1 + x2) / 2
            # 稍微做个偏移，以产生弧度
            ctrl_y1 = y1
            ctrl_y2 = y2
            path.cubicTo(ctrl_x, ctrl_y1, ctrl_x, ctrl_y2, x2, y2)

            path_item = QGraphicsPathItem(path)
            path_pen = QPen(Qt.darkGray, 2)
            path_item.setPen(path_pen)
            # 提示信息
            path_item.setToolTip(f"{src} → {tgt}\n频次: {weight}")

            self.scene.addItem(path_item)

            # 在曲线上添加“箭头”
            self._add_arrow_head(x1, y1, x2, y2, path_pen)

        # ========== 绘制节点(圆角矩形) ==========
        # 此处我们将频次也放入矩形内部
        for act_clean in keep_acts:
            if act_clean not in pos:
                continue
            x, y = pos[act_clean]
            act_name = label_map.get(act_clean, act_clean)
            freq_count = activity_counts.get(act_name, 1)

            # 准备文本(活动 + 频次)
            node_text = f"{act_name}\n({freq_count})"

            # 先计算文本大小
            font = QFont("Arial", 10)
            fm = QFontMetrics(font)
            lines = node_text.split('\n')
            line_heights = [fm.boundingRect(line).height() for line in lines]
            text_height = sum(line_heights)
            text_width = max(fm.horizontalAdvance(line) for line in lines)

            # 给点留白
            padding_w = 12
            padding_h = 8
            min_width = 70
            min_height = 40

            rect_w = max(min_width, text_width + padding_w * 2)
            rect_h = max(min_height, text_height + padding_h * 2)

            # 圆角矩形 path
            path = QPainterPath()
            corner_radius = 10
            path.addRoundedRect(
                x - rect_w / 2, y - rect_h / 2,
                rect_w, rect_h,
                corner_radius, corner_radius
            )
            node_item = QGraphicsPathItem(path)
            node_item.setBrush(QBrush(Qt.white))
            node_item.setPen(QPen(Qt.gray, 2))
            node_item.setToolTip(f"{act_name}\n出现次数: {freq_count}")

            self.scene.addItem(node_item)

            # 将文字画在矩形中心
            # 因为有多行，逐行输出
            current_y = y - rect_h / 2 + padding_h
            for line in lines:
                tw = fm.horizontalAdvance(line)
                line_item = QGraphicsTextItem(line)
                line_item.setFont(font)
                # 让文字居中
                line_item.setPos(x - tw/2, current_y)
                current_y += fm.boundingRect(line).height()
                self.scene.addItem(line_item)

            # 绑定点击事件
            node_item.setFlag(QGraphicsItem.ItemIsSelectable)
            node_item.setData(0, act_name)
            node_item.mousePressEvent = self._make_node_click_handler(act_name, freq_count)

    def _make_node_click_handler(self, act, count):
        def handler(event):
            dialog = QDialog()
            dialog.setWindowTitle("活动详情")
            layout = QVBoxLayout()
            label = QLabel(f"活动名称: {act}\n出现次数: {count}")
            layout.addWidget(label)
            dialog.setLayout(layout)
            dialog.exec_()
        return handler

    def _add_arrow_head(self, x1, y1, x2, y2, pen):
        """
        在 (x2,y2) 附近画一个小三角箭头，指向 (x2,y2) 方向。
        """
        arrow_size = 8.0
        line_angle = math.atan2((y2 - y1), (x2 - x1))

        # 箭头三角形三个点
        p1 = QPointF(x2, y2)
        p2 = QPointF(
            x2 - arrow_size * math.cos(line_angle - math.radians(20)),
            y2 - arrow_size * math.sin(line_angle - math.radians(20))
        )
        p3 = QPointF(
            x2 - arrow_size * math.cos(line_angle + math.radians(20)),
            y2 - arrow_size * math.sin(line_angle + math.radians(20))
        )

        triangle = QPolygonF([p1, p2, p3])
        path = QPainterPath()
        path.addPolygon(triangle)

        arrow_item = QGraphicsPathItem(path)
        arrow_item.setBrush(Qt.darkGray)
        arrow_item.setPen(pen)
        self.scene.addItem(arrow_item)