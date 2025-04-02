import networkx as nx
from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsSimpleTextItem, QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem, QGraphicsWidget, QGraphicsSceneMouseEvent, QDialog, QLabel, QVBoxLayout
from PyQt5.QtGui import QPen, QBrush, QColor, QFont
from PyQt5.QtCore import Qt, QPointF

from pm4py.algo.discovery.dfg import algorithm as dfg_discovery
from pm4py.objects.conversion.log import converter as log_converter
from PyQt5.QtGui import QPainter

class ProcessGraphView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.scene = QGraphicsScene()
        self.setScene(self.scene)

        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.scale(1.0, 1.0)

    def draw_from_event_log(self, event_log):
        """
        从PM4Py EventLog中提取DFG并绘制图形
        """
        self.scene.clear()

        # 构建直接后继图（DFG）
        dfg = dfg_discovery.apply(event_log)

        # 统计活动出现频次（用于节点大小或颜色）
        activity_counts = {}
        for trace in event_log:
            for event in trace:
                act = event["concept:name"]
                activity_counts[act] = activity_counts.get(act, 0) + 1

        # 转换为NetworkX图
        G = nx.DiGraph()
        for (src, tgt), freq in dfg.items():
            G.add_edge(src, tgt, weight=freq)

        for act, freq in activity_counts.items():
            if not G.has_node(act):
                G.add_node(act)
            G.nodes[act]["count"] = freq

        # 使用 spring_layout 自动布局（也可以改为 graphviz layout）
        pos = nx.spring_layout(G, scale=500, k=150)

        # 画边
        for src, tgt in G.edges():
            x1, y1 = pos[src]
            x2, y2 = pos[tgt]
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(QPen(Qt.darkGray, 2))
            self.scene.addItem(line)

            # 边权文字
            weight = G[src][tgt]['weight']
            text = QGraphicsSimpleTextItem(str(weight))
            text.setPos((x1 + x2) / 2, (y1 + y2) / 2)
            self.scene.addItem(text)

        # 画节点
        for act, (x, y) in pos.items():
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

            # 点击事件（简化示例）
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
