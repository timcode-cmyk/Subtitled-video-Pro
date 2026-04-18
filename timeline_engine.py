# ==========================================
# 文件名: timeline_engine.py (无损升级版：6轨道平铺引擎)
# ==========================================
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsRectItem, QGraphicsItem, QWidget
from PySide6.QtCore import Qt, QRectF, QObject, Signal, Slot, QPointF
from PySide6.QtGui import QBrush, QColor, QPen, QPainter, QFont
import os

TRACK_H = 35
HEADER_H = 30

class TimelineHeader(QWidget):
    def __init__(self, parent=None, controller=None):
        super().__init__(parent); self.controller = controller; self.setFixedWidth(80); self.TRACK_H = TRACK_H 
        
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.fillRect(self.rect(), QColor("#11111b")) 
        painter.setPen(QColor("#313244")); painter.drawLine(79, 0, 79, self.height()); painter.drawLine(0, HEADER_H, 80, HEADER_H)
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold)); painter.setPen(QColor("#f9e2af"))
        
        # 👑 完美的 6 轨道层级命名
        painter.drawText(10, HEADER_H + self.TRACK_H*0 + 22, "T3 标题")
        painter.drawText(10, HEADER_H + self.TRACK_H*1 + 22, "T2 正文")
        painter.drawText(10, HEADER_H + self.TRACK_H*2 + 22, "T1 蒙版")
        painter.setPen(QColor("#89b4fa"))
        painter.drawText(10, HEADER_H + self.TRACK_H*3 + 22, "V1 画面")
        painter.setPen(QColor("#313244"))
        painter.drawLine(0, HEADER_H + self.TRACK_H*4 + 2, 80, HEADER_H + self.TRACK_H*4 + 2)
        painter.setPen(QColor("#a6e3a1"))
        painter.drawText(10, HEADER_H + self.TRACK_H*4 + 28, "A1 原声")
        painter.drawText(10, HEADER_H + self.TRACK_H*5 + 28, "A2 配音")

    def mousePressEvent(self, event):
        if not self.controller: return
        y = event.pos().y()
        if HEADER_H <= y < HEADER_H + self.TRACK_H: self.controller.select_entire_track("sub", 0) 
        elif HEADER_H + self.TRACK_H <= y < HEADER_H + self.TRACK_H * 2: self.controller.select_entire_track("sub", 1) 
        elif HEADER_H + self.TRACK_H * 2 <= y < HEADER_H + self.TRACK_H * 3: self.controller.select_entire_track("sub", 2) 

class ClipSignals(QObject):
    clicked = Signal(str, int) 
    moved = Signal(str, int, float, float, int)
    drag_finished = Signal(str, int, float)

class ClipItem(QGraphicsRectItem):
    def __init__(self, clip_type, idx, start_t, end_t, track_idx, pps, text="", media_dur=0):
        self.clip_type = clip_type; self.idx = idx; self.pps = pps; self.track_idx = track_idx; self.text = text; self.media_dur = media_dur; self.signals = ClipSignals()
        
        # 👑 动态坐标定位
        if clip_type == "sub": y_pos = HEADER_H + self.track_idx * TRACK_H
        elif clip_type == "video": y_pos = HEADER_H + TRACK_H * 3
        else: y_pos = HEADER_H + TRACK_H * 5 + 5 # 假设独立的配音永远在最底下A2
        
        x = start_t * pps; w = max(5.0, (end_t - start_t) * pps)
        super().__init__(0, 0, w, TRACK_H - 4); self.setPos(x, y_pos + 2)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        if clip_type == "video": self.base_color = QColor("#89b4fa")
        elif clip_type == "audio": self.base_color = QColor("#a6e3a1")
        else: self.base_color = QColor("#f9e2af")
        self.resize_mode = None; self.start_rect = None; self.start_scene_pos = None

    def hoverMoveEvent(self, event):
        pos_x = event.pos().x(); margin = 20 
        if pos_x <= margin or pos_x >= self.rect().width() - margin: self.setCursor(Qt.CursorShape.SizeHorCursor)
        else: self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            new_pos = value
            # 👑 允许字幕跨跃 3 个文字轨道
            if self.clip_type == "sub":
                if new_pos.y() < HEADER_H + TRACK_H: new_pos.setY(HEADER_H + 2); self.track_idx = 0
                elif new_pos.y() < HEADER_H + TRACK_H * 2: new_pos.setY(HEADER_H + TRACK_H + 2); self.track_idx = 1
                else: new_pos.setY(HEADER_H + TRACK_H * 2 + 2); self.track_idx = 2
            else: new_pos.setY(self.y())
            if new_pos.x() < 0: new_pos.setX(0)
            return new_pos
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if not self.resize_mode: self.emit_moved()
        return super().itemChange(change, value)

    def emit_moved(self):
        new_start = self.scenePos().x() / self.pps; new_end = new_start + (self.rect().width() / self.pps)
        self.signals.moved.emit(self.clip_type, self.idx, new_start, new_end, self.track_idx)

    def mousePressEvent(self, event):
        self.setZValue(100); self.setSelected(True); self.signals.clicked.emit(self.clip_type, self.idx)
        pos_x = event.pos().x(); margin = 20
        if pos_x <= margin: self.resize_mode = "left"
        elif pos_x >= self.rect().width() - margin: self.resize_mode = "right"
        else: self.resize_mode = None
        self.start_rect = self.rect(); self.start_scene_pos = self.scenePos()
        if not self.resize_mode: super().mousePressEvent(event)
        else: event.accept()

    def mouseMoveEvent(self, event):
        if self.resize_mode:
            scene_dx = event.scenePos().x() - event.buttonDownScenePos(Qt.MouseButton.LeftButton).x()
            if self.resize_mode == "left":
                new_w = self.start_rect.width() - scene_dx
                if new_w >= 2.0 and self.start_scene_pos.x() + scene_dx >= 0:
                    self.setPos(self.start_scene_pos.x() + scene_dx, self.start_scene_pos.y()); self.setRect(0, 0, new_w, self.start_rect.height()); self.emit_moved()
            elif self.resize_mode == "right":
                new_w = self.start_rect.width() + scene_dx
                if new_w >= 2.0: self.setRect(0, 0, new_w, self.start_rect.height()); self.emit_moved()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.resize_mode = None; self.setZValue(1)
        super().mouseReleaseEvent(event)
        final_start = self.scenePos().x() / self.pps
        self.signals.drag_finished.emit(self.clip_type, self.idx, final_start)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isSelected(): painter.setBrush(QBrush(QColor("#f38ba8"))); painter.setPen(QPen(QColor("white"), 2))
        else: painter.setBrush(QBrush(self.base_color)); painter.setPen(QPen(QColor("#313244"), 1))
        painter.drawRoundedRect(self.rect(), 4, 4)
        if self.clip_type == "video" and self.media_dur > 0:
            loop_w = self.media_dur * self.pps; curr_x = loop_w; painter.setPen(QPen(QColor(255, 255, 255, 180), 2, Qt.PenStyle.DashLine))
            while curr_x < self.rect().width(): painter.drawLine(QPointF(curr_x, 0), QPointF(curr_x, self.rect().height())); curr_x += loop_w
        controller = self.scene().views()[0].controller
        if self.clip_type == "audio" and hasattr(controller, 'a_wave_pixmap'):
            wave = controller.a_wave_pixmap
            if wave and not wave.isNull(): painter.setClipRect(self.rect()); painter.drawPixmap(self.rect(), wave, QRectF(wave.rect())); painter.setClipping(False)
        elif self.clip_type == "video" and hasattr(controller, 'video_thumbs'):
            thumbs = controller.video_thumbs
            if thumbs:
                thumb_w = (TRACK_H - 4) * (16/9); curr_x = 0; idx = self.idx % len(thumbs)
                painter.setClipRect(self.rect())
                while curr_x < self.rect().width() and idx < len(thumbs):
                    if thumbs[idx] and not thumbs[idx].isNull(): painter.drawPixmap(QRectF(curr_x, 0, thumb_w, TRACK_H - 4), thumbs[idx], QRectF(thumbs[idx].rect()))
                    curr_x += thumb_w; idx += 1
                painter.setClipping(False)
        painter.setPen(QPen(QColor("#11111b"))); painter.setFont(QFont("Arial", 9, QFont.Weight.Bold)); painter.drawText(self.rect().adjusted(5, 5, -5, -5), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text.replace("\n", " "))

class PlayheadItem(QGraphicsItem):
    def __init__(self, height):
        super().__init__(); self.line_height = height; self.setZValue(1000) 
    def boundingRect(self): return QRectF(-10, 0, 20, self.line_height)
    def paint(self, painter, option, widget=None):
        painter.setPen(QPen(QColor("#f38ba8"), 2)); painter.drawLine(0, 0, 0, int(self.line_height)); painter.setBrush(QBrush(QColor("#f38ba8"))); painter.drawPolygon([QPointF(-6, 0), QPointF(6, 0), QPointF(0, 10)])

class AdvancedTimeline(QGraphicsView):
    def __init__(self, controller):
        super().__init__(); self.controller = controller; self.scene = QGraphicsScene(self); self.setScene(self.scene); self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop); self.setRenderHint(QPainter.RenderHint.Antialiasing); self.setStyleSheet("background-color: #11111b; border: none;"); self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); self.playhead = PlayheadItem(800); self.scene.addItem(self.playhead); self.is_scrubbing = False

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect); pps = self.controller.zoom_factor; dur = max(10.0, self.controller.state.get("duration", 10.0)); w = max(rect.width(), dur * pps + 200); self.scene.setSceneRect(0, 0, w, 300)
        painter.fillRect(QRectF(0, 0, w, HEADER_H), QColor("#181825")); painter.setPen(QColor("gray")); painter.setFont(QFont("Arial", 8))
        for i in range(0, int(w / pps) + 1, max(1, int(100 / pps))):
            x = i * pps; painter.drawText(QPointF(x + 5, 15), f"{i}s"); painter.drawLine(QPointF(x, 20), QPointF(x, 30))
            
        # 👑 画出 6 条斑马线背景
        y_offsets = [HEADER_H, HEADER_H+TRACK_H, HEADER_H+TRACK_H*2, HEADER_H+TRACK_H*3, HEADER_H+TRACK_H*4, HEADER_H+TRACK_H*5]
        colors = ["#181825", "#1e1e2e", "#181825", "#1e1e2e", "#181825", "#1e1e2e"]
        for y, color in zip(y_offsets, colors): painter.fillRect(QRectF(0, y, w, TRACK_H), QColor(color))
        
        painter.setPen(QColor("#313244")); painter.drawLine(QPointF(0, HEADER_H+TRACK_H*4), QPointF(w, HEADER_H+TRACK_H*4))
        
        v_wave = getattr(self.controller, 'v_wave_pixmap', None); clips = self.controller.state.get("video_clips", [])
        if v_wave and not v_wave.isNull() and clips:
            min_x = min([c["start"] for c in clips]) * pps; max_x = max([c["end"] for c in clips]) * pps; t_rect = QRectF(min_x, HEADER_H + TRACK_H*4 + 5, max_x - min_x, TRACK_H - 4); painter.fillRect(t_rect, QColor("#1e2e24")); painter.setClipRect(t_rect); painter.drawPixmap(t_rect, v_wave, QRectF(v_wave.rect())); painter.setClipping(False)

    def sync_from_controller(self):
        for item in self.scene.items():
            if isinstance(item, ClipItem): self.scene.removeItem(item)
        pps = self.controller.zoom_factor
        
        # 👑 修复渲染轨道映射
        for i, clip in enumerate(self.controller.state.get("video_clips", [])):
            item = ClipItem("video", i, clip["start"], clip["end"], 3, pps, "🎥 复合片段块", media_dur=clip.get("dur", 0)); item.signals.clicked.connect(self.on_clip_clicked); item.signals.moved.connect(self.on_clip_moved); item.signals.drag_finished.connect(self.on_clip_drag_finished)
            if self.controller.selected_track == "video" and self.controller.current_v_idx == i: item.setSelected(True)
            self.scene.addItem(item)
            
        if self.controller.state.get("audio_path"):
            a_trim = self.controller.state.get("a_trim", [0, 10]); item = ClipItem("audio", 0, a_trim[0], a_trim[1], 5, pps, "🎵 独立配音"); item.signals.clicked.connect(self.on_clip_clicked); item.signals.moved.connect(self.on_clip_moved); item.signals.drag_finished.connect(self.on_clip_drag_finished); self.scene.addItem(item)
            
        for i, s in enumerate(self.controller.state.get("subs_data", [])):
            trk_idx = s.get('track', 1); item = ClipItem("sub", i, float(s.get('start', 0)), float(s.get('end', 1)), trk_idx, pps, s.get("text", "").replace("\n", " ")); item.signals.clicked.connect(self.on_clip_clicked); item.signals.moved.connect(self.on_clip_moved); item.signals.drag_finished.connect(self.on_clip_drag_finished)
            if i == self.controller.current_selected_idx: item.setSelected(True)
            self.scene.addItem(item)
        self.update_playhead(self.controller.current_play_time); self.scene.update()

    def update_playhead(self, time_sec):
        pps = self.controller.zoom_factor; self.playhead.setPos(time_sec * pps, 0); view_width = self.viewport().width(); head_x = time_sec * pps; scroll_bar = self.horizontalScrollBar()
        if head_x > scroll_bar.value() + view_width - 50: scroll_bar.setValue(int(head_x - view_width + 100))

    @Slot(str, int)
    def on_clip_clicked(self, clip_type, idx):
        if clip_type == "sub": self.controller.current_selected_idx = idx
        elif clip_type == "video": self.controller.current_v_idx = idx
        self.controller.switch_inspector(clip_type)

    @Slot(str, int, float, float, int)
    def on_clip_moved(self, clip_type, idx, new_start, new_end, new_track):
        if clip_type == "sub":
            sub = self.controller.state["subs_data"][idx]
            old_start = float(sub.get("start", 0)); old_end = float(sub.get("end", 1))
            old_dur = max(0.001, old_end - old_start); new_dur = max(0.001, new_end - new_start)

            words = sub.get("words", [])
            for w in words:
                rel_s = (float(w.get("start", 0)) - old_start) / old_dur
                rel_e = (float(w.get("end", 1)) - old_start) / old_dur
                w["start"] = new_start + rel_s * new_dur; w["end"] = new_start + rel_e * new_dur

            sub["start"] = new_start; sub["end"] = new_end; sub["track"] = new_track
            
            if hasattr(self.controller, 'ui_entries') and 0 <= idx < len(self.controller.ui_entries):
                entry_dict = self.controller.ui_entries[idx]
                if "start_spin" in entry_dict and "end_spin" in entry_dict:
                    entry_dict["start_spin"].blockSignals(True); entry_dict["end_spin"].blockSignals(True)
                    entry_dict["start_spin"].setValue(new_start); entry_dict["end_spin"].setValue(new_end)
                    entry_dict["start_spin"].blockSignals(False); entry_dict["end_spin"].blockSignals(False)
            
            if getattr(self.controller, 'current_selected_idx', -1) == idx and getattr(self.controller, 'selected_track', '') == 'sub':
                self.controller.sub_start_spin.blockSignals(True); self.controller.sub_end_spin.blockSignals(True)
                self.controller.sub_start_spin.setValue(new_start); self.controller.sub_end_spin.setValue(new_end)
                self.controller.sub_start_spin.blockSignals(False); self.controller.sub_end_spin.blockSignals(False)
                
        elif clip_type == "video":
            self.controller.state["video_clips"][idx]["start"] = new_start; self.controller.state["video_clips"][idx]["end"] = new_end
        elif clip_type == "audio":
            self.controller.state["a_trim"] = [new_start, new_end]

    @Slot(str, int, float)
    def on_clip_drag_finished(self, clip_type, idx, final_start):
        self.controller.update_timeline_size()
        self.controller.auto_save_cache()
        self.controller.sync_player_to_time(final_start)
        
    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if not isinstance(item, ClipItem): self.is_scrubbing = True; self.controller.switch_inspector("empty"); self.scrub_playhead(event.position().x())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_scrubbing: self.scrub_playhead(event.position().x())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_scrubbing = False; super().mouseReleaseEvent(event)

    def scrub_playhead(self, x_pos):
        t = max(0.0, self.mapToScene(int(x_pos), 0).x() / self.controller.zoom_factor); self.controller.sync_player_to_time(t)
        
    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y(); self.controller.zoom_factor = min(300.0, self.controller.zoom_factor * 1.2) if delta > 0 else max(10.0, self.controller.zoom_factor * 0.8); self.sync_from_controller(); self.viewport().update()
        else: super().wheelEvent(event)