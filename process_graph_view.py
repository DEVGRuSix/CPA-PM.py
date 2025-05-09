import networkx as nx
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPathItem, QGraphicsItem,
    QGraphicsTextItem, QDialog, QLabel, QVBoxLayout, QPushButton
)
from PyQt5.QtGui import (
    QPen, QBrush, QColor, QFont, QPainter, QFontMetrics, QPainterPath, QPolygonF
)
from PyQt5.QtCore import Qt, QPointF, QTimer

from pm4py.algo.discovery.dfg import algorithm as dfg_discovery
from networkx.drawing.nx_pydot import graphviz_layout
from remove_self_loop_dialog import RemoveSelfLoopDialog
from cpa_utils import remove_consecutive_self_loops

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
        self._current_scale = 1.0
        self.scale(self._current_scale, self._current_scale)

        # ===== 缩放控制按钮（右下角） =====
        self.zoom_label = QLabel("100%", self)
        self.zoom_label.setStyleSheet("""
            QLabel {
                background-color: rgba(255,255,255,230);
                border: 1px solid gray;
                border-radius: 4px;
                padding: 2px 6px;
            }
        """)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.mousePressEvent = self._on_zoom_reset

        self.btn_zoom_in = QPushButton("＋", self)
        self.btn_zoom_in.setFixedSize(20, 20)
        self.btn_zoom_in.clicked.connect(self._zoom_in)

        self.btn_zoom_out = QPushButton("－", self)
        self.btn_zoom_out.setFixedSize(20, 20)
        self.btn_zoom_out.clicked.connect(self._zoom_out)

        self._update_zoom_controls()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_zoom_controls()

    def _update_zoom_controls(self):
        spacing = 6
        w, h = self.viewport().width(), self.viewport().height()

        self.zoom_label.move(w - self.zoom_label.width() - spacing, h - 30)
        self.btn_zoom_in.move(w - 50, h - 60)
        self.btn_zoom_out.move(w - 25, h - 60)

        self.zoom_label.show()
        self.btn_zoom_in.show()
        self.btn_zoom_out.show()

    def _update_zoom_label(self):
        percent = int(self._current_scale * 100)
        self.zoom_label.setText(f"{percent}%")
        self.zoom_label.adjustSize()
        self._update_zoom_controls()

    def _on_zoom_reset(self, event):
        self.reset_view()

    def _zoom_in(self):
        self._scale_view(1.15)

    def _zoom_out(self):
        self._scale_view(1 / 1.15)

    def _scale_view(self, factor):
        self._current_scale *= factor
        self.scale(factor, factor)
        self._update_zoom_label()

    def draw_from_event_log(self, event_log, act_percent=100, edge_percent=100):
        self.scene.clear()
        self._current_scale = 1.0
        self.resetTransform()

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
        keep_acts = set(sanitize_label(act) for act, _ in act_freqs[:max(1, len(act_freqs) * act_percent // 100)])

        edge_freqs = sorted(dfg.items(), key=lambda x: x[1], reverse=True)
        keep_edges = set((sanitize_label(src), sanitize_label(tgt)) for (src, tgt), _ in
                         edge_freqs[:max(1, len(edge_freqs) * edge_percent // 100)])

        try:
            start_acts = [trace[0]['concept:name'] for trace in event_log if trace]
            most_common_start, _ = Counter(start_acts).most_common(1)[0]
            root_node = sanitize_label(most_common_start)

            # ✅ Disco 风格布局关键参数
            G.graph['graph'] = {
                'rankdir': 'TB',  # 自上而下（vertical layout）
                'splines': 'polyline',  # 折线
                'overlap': 'false',  # 避免节点重叠
                'nodesep': '0.6',  # 横向间距
                'ranksep': '0.7',  # 纵向间距
                'margin': '0.2'
            }

            pos = graphviz_layout(G, prog='dot', root=root_node)
            pos = {n: (x, -y) for n, (x, y) in pos.items()}
        except Exception as e:
            print("Graphviz layout failed, fallback to spring_layout:", e)
            pos = nx.spring_layout(G, scale=800, k=300)
            pos = {n: (x, -y) for n, (x, y) in pos.items()}

        max_edge_weight = max([freq for (_, _), freq in dfg.items()] or [1])
        max_node_count = max(activity_counts.values() or [1])

        # ===== 统一节点宽度：找出最长 label 的宽度并存入 self =====
        max_text_width = 0
        font = QFont("Arial", 10)
        fm = QFontMetrics(font)
        for act_clean in keep_acts:
            act_name = label_map.get(act_clean, act_clean)
            freq_count = activity_counts.get(act_name, 1)
            node_text = f"{act_name}\n({freq_count})"
            lines = node_text.split('\n')
            text_width = max(fm.horizontalAdvance(line) for line in lines)
            max_text_width = max(max_text_width, text_width)

        padding_w = 12
        self.max_node_width = max(70, max_text_width + padding_w * 2)  # 用于箭头计算

        drawn_edges = set()

        for (src, tgt), weight in dfg.items():
            src_clean = sanitize_label(src)
            tgt_clean = sanitize_label(tgt)

            edge_key = (src_clean, tgt_clean)
            if edge_key in drawn_edges:
                continue
            drawn_edges.add(edge_key)

            if (src_clean, tgt_clean) not in keep_edges:
                continue
            if src_clean not in keep_acts or tgt_clean not in keep_acts:
                continue
            if src_clean not in pos or tgt_clean not in pos:
                continue

            (x1, y1) = pos[src_clean]
            (x2, y2) = pos[tgt_clean]

            pen_width = 1 + 3 * (weight / max_edge_weight)
            pen_color = QColor(80, 80, 80 + int(175 * (weight / max_edge_weight)))
            pen = QPen(pen_color, pen_width)

            if src_clean == tgt_clean:
                loop_width = 50
                loop_height = 30

                # 起点右上角
                loop_center_x = x1 + self.max_node_width / 2
                loop_center_y = y1

                arc_path = QPainterPath()
                arc_path.moveTo(loop_center_x, loop_center_y - loop_height / 2)
                arc_path.arcTo(loop_center_x - loop_width / 2, loop_center_y - loop_height / 2,
                               loop_width, loop_height, 90, -180)

                loop_item = QGraphicsPathItem(arc_path)
                loop_item.setPen(pen)
                loop_item.setZValue(0)
                loop_item.setToolTip(f"{src} → {tgt}\n频次: {weight}")
                self.scene.addItem(loop_item)

                freq_text = QGraphicsTextItem(str(weight))
                freq_text.setFont(QFont("Arial", 12))
                freq_text.setDefaultTextColor(Qt.darkGray)
                freq_text.setPos(loop_center_x + loop_width / 2 + 4, loop_center_y - loop_height / 2)
                freq_text.setZValue(2)
                self.scene.addItem(freq_text)


            else:
                line = QGraphicsPathItem()
                path = QPainterPath(QPointF(x1, y1))
                path.lineTo(QPointF(x2, y2))
                line.setPath(path)
                line.setPen(pen)
                line.setZValue(0)
                line.setToolTip(f"{src} → {tgt}\n频次: {weight}")
                self.scene.addItem(line)

                dx = x2 - x1
                dy = y2 - y1
                is_vertical = abs(dy) > abs(dx)

                fx = x1 + dx * 0.33
                fy = y1 + dy * 0.33

                freq_text = QGraphicsTextItem(str(weight))
                freq_text.setFont(QFont("Arial", 12))
                freq_text.setDefaultTextColor(Qt.darkGray)
                if is_vertical:
                    freq_text.setPos(fx + 10, fy)
                else:
                    freq_text.setPos(fx, fy - 14)

                freq_text.setZValue(2)
                self.scene.addItem(freq_text)

                self._add_arrow_head(x1, y1, x2, y2, pen)



        for act_clean in keep_acts:
            if act_clean not in pos:
                continue
            x, y = pos[act_clean]
            act_name = label_map.get(act_clean, act_clean)
            freq_count = activity_counts.get(act_name, 1)
            node_text = f"{act_name}\n({freq_count})"

            font = QFont("Arial", 10)
            fm = QFontMetrics(font)
            lines = node_text.split('\n')
            line_heights = [fm.boundingRect(line).height() for line in lines]
            text_height = sum(line_heights)
            text_width = max(fm.horizontalAdvance(line) for line in lines)
            padding_w, padding_h = 12, 8
            min_width, min_height = 70, 40

            rect_w = self.max_node_width
            rect_h = max(min_height, text_height + padding_h * 2)

            path = QPainterPath()
            corner_radius = 10
            path.addRoundedRect(x - rect_w / 2, y - rect_h / 2, rect_w, rect_h, corner_radius, corner_radius)

            node_item = QGraphicsPathItem(path)
            node_item.setBrush(QBrush(QColor(255 - int(200 * (freq_count / max_node_count)), 255, 200)))
            node_item.setPen(QPen(Qt.gray, 2))
            node_item.setToolTip(f"{act_name}\n出现次数: {freq_count}")
            node_item.setZValue(1)
            self.scene.addItem(node_item)

            current_y = y - rect_h / 2 + padding_h
            for line in lines:
                tw = fm.horizontalAdvance(line)
                line_item = QGraphicsTextItem(line)
                line_item.setFont(font)
                line_item.setPos(x - tw / 2, current_y)
                current_y += fm.boundingRect(line).height()
                line_item.setZValue(3)
                self.scene.addItem(line_item)

            node_item.setFlag(QGraphicsItem.ItemIsSelectable)
            node_item.setData(0, act_name)
            node_item.mousePressEvent = self._make_node_click_handler(act_name, freq_count)

        QTimer.singleShot(0, self.auto_fit_view)

    def auto_fit_view(self):
        if self.scene.items():
            rect = self.scene.itemsBoundingRect()
            self.fitInView(rect, Qt.KeepAspectRatio)
            self.centerOn(rect.center())
            self._current_scale = 1.0  # 与视觉保持一致
            self._update_zoom_label()

    def reset_view(self):
        self.auto_fit_view()
    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            delta = event.angleDelta().y()
            zoom_factor = 1.15 if delta > 0 else 1 / 1.15
            self._scale_view(zoom_factor)
        else:
            super().wheelEvent(event)

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
        arrow_size = 15.0  # 放大箭头尺寸
        dx = x2 - x1
        dy = y2 - y1
        angle = math.atan2(dy, dx)

        # 获取目标节点宽度（来自 draw_from_event_log 中统一设定）
        target_width = getattr(self, 'max_node_width', 70)  # 默认最小值
        distance_to_edge = target_width / 2 + 5  # 加一点偏移

        line_length = math.hypot(dx, dy)
        if line_length == 0:
            return  # 避免除以零
        effective_ratio = max(0, (line_length - distance_to_edge) / line_length)

        arrow_x = x1 + effective_ratio * dx
        arrow_y = y1 + effective_ratio * dy

        p1 = QPointF(arrow_x, arrow_y)
        p2 = QPointF(arrow_x - arrow_size * math.cos(angle - math.radians(20)),
                     arrow_y - arrow_size * math.sin(angle - math.radians(20)))
        p3 = QPointF(arrow_x - arrow_size * math.cos(angle + math.radians(20)),
                     arrow_y - arrow_size * math.sin(angle + math.radians(20)))

        triangle = QPolygonF([p1, p2, p3])
        path = QPainterPath()
        path.addPolygon(triangle)

        arrow_item = QGraphicsPathItem(path)
        arrow_item.setBrush(Qt.darkGray)
        arrow_item.setPen(pen)
        arrow_item.setZValue(10)
        self.scene.addItem(arrow_item)

