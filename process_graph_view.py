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
        self.scene.clear()
        if not event_log:
            return

        dfg = dfg_discovery.apply(event_log)

        activity_counts = {}
        for trace in event_log:
            for event in trace:
                act = event.get("concept:name", "undefined")
                activity_counts[act] = activity_counts.get(act, 0) + 1

        G = nx.DiGraph()
        label_map = {}

        for (src, tgt), freq in dfg.items():
            src_clean = sanitize_label(src)
            tgt_clean = sanitize_label(tgt)
            G.add_edge(src_clean, tgt_clean, weight=freq)
            label_map[src_clean] = src
            label_map[tgt_clean] = tgt

        for act, freq in activity_counts.items():
            act_clean = sanitize_label(act)
            if not G.has_node(act_clean):
                G.add_node(act_clean)
            G.nodes[act_clean]["count"] = freq
            label_map[act_clean] = act

        act_freqs = sorted(activity_counts.items(), key=lambda x: x[1], reverse=True)
        keep_acts = set(sanitize_label(act) for act, _ in act_freqs[:max(1, len(act_freqs)*act_percent//100)])

        edge_freqs = sorted(dfg.items(), key=lambda x: x[1], reverse=True)
        keep_edges = set((sanitize_label(src), sanitize_label(tgt)) for (src, tgt), _ in edge_freqs[:max(1, len(edge_freqs)*edge_percent//100)])

        try:
            start_acts = [trace[0]['concept:name'] for trace in event_log if trace]
            most_common_start, _ = Counter(start_acts).most_common(1)[0]
            root_node = sanitize_label(most_common_start)
            G.graph['graph'] = {'rankdir': 'TB', 'splines': 'line', 'overlap': 'false'}
            pos = graphviz_layout(G, prog='dot', root=root_node)
            pos = {n: (x, -y) for n, (x, y) in pos.items()}
        except Exception as e:
            print("Graphviz layout failed, fallback to spring_layout:", e)
            pos = nx.spring_layout(G, scale=500, k=150)
            pos = {n: (x, -y) for n, (x, y) in pos.items()}

        max_weight = max((freq for (_, _), freq in dfg.items()), default=1)

        for (src, tgt), weight in dfg.items():
            src_clean = sanitize_label(src)
            tgt_clean = sanitize_label(tgt)
            if (src_clean, tgt_clean) not in keep_edges:
                continue
            if src_clean not in keep_acts or tgt_clean not in keep_acts:
                continue
            if src_clean not in pos or tgt_clean not in pos:
                continue

            (x1, y1) = pos[src_clean]
            (x2, y2) = pos[tgt_clean]

            line = QPainterPath()
            line.moveTo(x1, y1)
            line.lineTo(x2, y2)
            path_item = QGraphicsPathItem(line)
            pen = QPen(Qt.darkGray)
            pen.setWidthF(1 + 3 * (weight / max_weight))
            path_item.setPen(pen)
            path_item.setToolTip(f"{src} → {tgt}\n频次: {weight}")
            self.scene.addItem(path_item)

            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            text = QGraphicsTextItem(str(weight))
            text.setFont(QFont("Arial", 8))
            text.setPos(mx, my)
            text.setDefaultTextColor(Qt.darkBlue)
            self.scene.addItem(text)

            self._add_arrow_head(x1, y1, x2, y2, pen)

        max_count = max(activity_counts.values())
        for act_clean in keep_acts:
            if act_clean not in pos:
                continue
            x, y = pos[act_clean]
            act_name = label_map.get(act_clean, act_clean)
            count = activity_counts.get(act_name, 1)

            node_text = f"{act_name}\n({count})"
            font = QFont("Arial", 10)
            fm = QFontMetrics(font)
            lines = node_text.split('\n')
            line_heights = [fm.boundingRect(line).height() for line in lines]
            text_height = sum(line_heights)
            text_width = max(fm.horizontalAdvance(line) for line in lines)

            padding_w, padding_h = 12, 8
            rect_w = max(70, text_width + 2 * padding_w)
            rect_h = max(40, text_height + 2 * padding_h)

            path = QPainterPath()
            path.addRoundedRect(x - rect_w / 2, y - rect_h / 2, rect_w, rect_h, 10, 10)
            node_item = QGraphicsPathItem(path)
            ratio = count / max_count
            color = QColor.fromHsv(200 - int(200 * ratio), 180, 255)
            node_item.setBrush(QBrush(color))
            node_item.setPen(QPen(Qt.gray, 2))
            node_item.setToolTip(f"{act_name}\n出现次数: {count}")
            self.scene.addItem(node_item)

            current_y = y - rect_h / 2 + padding_h
            for line in lines:
                tw = fm.horizontalAdvance(line)
                line_item = QGraphicsTextItem(line)
                line_item.setFont(font)
                line_item.setPos(x - tw / 2, current_y)
                current_y += fm.boundingRect(line).height()
                self.scene.addItem(line_item)

            node_item.setFlag(QGraphicsItem.ItemIsSelectable)
            node_item.setData(0, act_name)
            node_item.mousePressEvent = self._make_node_click_handler(act_name, count)

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
        arrow_size = 8.0
        angle = math.atan2(y2 - y1, x2 - x1)
        p1 = QPointF(x2, y2)
        p2 = QPointF(x2 - arrow_size * math.cos(angle - math.radians(20)), y2 - arrow_size * math.sin(angle - math.radians(20)))
        p3 = QPointF(x2 - arrow_size * math.cos(angle + math.radians(20)), y2 - arrow_size * math.sin(angle + math.radians(20)))
        triangle = QPolygonF([p1, p2, p3])
        path = QPainterPath()
        path.addPolygon(triangle)
        arrow_item = QGraphicsPathItem(path)
        arrow_item.setBrush(Qt.darkGray)
        arrow_item.setPen(pen)
        self.scene.addItem(arrow_item)