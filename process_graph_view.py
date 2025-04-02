import networkx as nx
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsSimpleTextItem, QGraphicsTextItem, QGraphicsItem,
    QDialog, QLabel, QVBoxLayout
)
from PyQt5.QtGui import QPen, QBrush, QColor, QFont, QPainter
from PyQt5.QtCore import Qt

from pm4py.algo.discovery.dfg import algorithm as dfg_discovery
from networkx.drawing.nx_pydot import graphviz_layout

import re

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
            pos = graphviz_layout(G, prog='dot')
        except Exception as e:
            print("Graphviz layout failed, fallback to spring_layout:", e)
            pos = nx.spring_layout(G, scale=500, k=150)

        for (src, tgt), weight in dfg.items():
            src_clean = sanitize_label(src)
            tgt_clean = sanitize_label(tgt)
            if (src_clean, tgt_clean) not in keep_edges:
                continue
            if src_clean not in keep_acts or tgt_clean not in keep_acts:
                continue
            if src_clean not in pos or tgt_clean not in pos:
                continue
            x1, y1 = pos[src_clean]
            x2, y2 = pos[tgt_clean]
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(QPen(Qt.darkGray, 2))
            line.setData(0, (src, tgt, weight))
            line.setToolTip(f"{src} → {tgt}\n频次: {weight}")
            self.scene.addItem(line)

            text = QGraphicsSimpleTextItem(str(weight))
            text.setPos((x1 + x2) / 2, (y1 + y2) / 2)
            self.scene.addItem(text)

            line.setFlag(QGraphicsItem.ItemIsSelectable)
            line.mousePressEvent = self.make_edge_click_handler(src, tgt, weight)

        for act_clean in keep_acts:
            if act_clean not in pos:
                continue
            x, y = pos[act_clean]
            act = label_map.get(act_clean, act_clean)
            count = activity_counts.get(act, 1)
            node = QGraphicsEllipseItem(x - 30, y - 30, 60, 60)
            node.setBrush(QBrush(Qt.lightGray))
            node.setToolTip(f"{act}\n频次: {count}")
            self.scene.addItem(node)

            label = QGraphicsTextItem(act)
            label.setFont(QFont("Arial", 10))
            label.setPos(x - 25, y - 10)
            label.setDefaultTextColor(Qt.black)
            self.scene.addItem(label)

            node.setFlag(QGraphicsItem.ItemIsSelectable)
            node.setData(0, act)
            node.mousePressEvent = self.make_node_click_handler(act, count)

    def make_node_click_handler(self, act, count):
        def handler(event):
            dialog = QDialog()
            dialog.setWindowTitle("活动详情")
            layout = QVBoxLayout()
            label = QLabel(f"活动名称: {act}\n出现次数: {count}")
            layout.addWidget(label)
            dialog.setLayout(layout)
            dialog.exec_()
        return handler

    def make_edge_click_handler(self, src, tgt, weight):
        def handler(event):
            dialog = QDialog()
            dialog.setWindowTitle("路径详情")
            layout = QVBoxLayout()
            label = QLabel(f"路径: {src} → {tgt}\n频次: {weight}")
            layout.addWidget(label)
            dialog.setLayout(layout)
            dialog.exec_()
        return handler
