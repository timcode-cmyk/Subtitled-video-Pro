# ==========================================
# 文件名: room_edit.py (加入 Ctrl+Z 时光机 & AI文案智能清洗)
# ==========================================
import os
import json
import tempfile
import threading
import requests
import re
import shutil
import subprocess
import urllib.request
import zipfile
import sys
import copy

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QTextEdit, QScrollArea, QTabWidget, QComboBox, 
                             QSlider, QFileDialog, QGridLayout, QFrame, 
                             QCheckBox, QMessageBox, QColorDialog, QFontComboBox, 
                             QStackedWidget, QDoubleSpinBox, QSpinBox, QSplitter, QInputDialog, QProgressDialog, QLineEdit, QSizePolicy)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink, QVideoFrame
from PySide6.QtCore import Qt, QUrl, QTimer, Slot, Signal, QLocale, QEvent, QObject, QSize
from PySide6.QtGui import QPainter, QPixmap, QKeySequence, QShortcut, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import QRectF

from timeline_engine import TimelineHeader, AdvancedTimeline
from core import get_ffmpeg_cmd, get_app_dir
from ui_components import (hex_to_rgb, get_exact_duration, get_video_dimensions,
                           AspectRatioContainer, render_subtitle_html)
from project_io import update_room_state

CACHE_FILE = os.path.join(tempfile.gettempdir(), "sh_v8_project_cache.json")
PRESETS_FILE = os.path.join(os.getcwd(), "style_presets.json") 

def local_get_cf_accounts():
    config_path = os.path.join(os.getcwd(), "settings.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f).get("cf_accounts", [])
        except: pass
    return []
    
# ==========================================
# 👑 滚轮屏蔽组件：强制鼠标滚轮穿透，只滚动页面不改参数
# ==========================================
class NoScrollComboBox(QComboBox):
    def wheelEvent(self, event): event.ignore()

class NoScrollFontComboBox(QFontComboBox):
    def wheelEvent(self, event): event.ignore()

class NoScrollSlider(QSlider):
    def wheelEvent(self, event): event.ignore()

class ProScrubSpinBox(QSpinBox):
    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons) 
        self.lineEdit().setCursor(Qt.CursorShape.SizeHorCursor) 
        self._is_dragging = False
        self._last_x = 0
        self.lineEdit().installEventFilter(self)

    def wheelEvent(self, event): 
        event.ignore() # 👑 强制屏蔽滚轮

    def eventFilter(self, obj, event):
        if obj == self.lineEdit():
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = True; self._last_x = event.globalPosition().x()
            elif event.type() == QEvent.Type.MouseMove and self._is_dragging:
                dx = event.globalPosition().x() - self._last_x
                if abs(dx) >= 1.0:
                    self.blockSignals(True); self.setValue(self.value() + int(dx) * self.singleStep()); self.blockSignals(False)
                    self._last_x = event.globalPosition().x()
                return True 
            elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = False; self.valueChanged.emit(self.value()) 
                if hasattr(self.parent(), "push_history"): self.parent().push_history()
        return super().eventFilter(obj, event)

class ProScrubDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.lineEdit().setCursor(Qt.CursorShape.SizeHorCursor)
        self._is_dragging = False
        self._last_x = 0
        self.lineEdit().installEventFilter(self)

    def wheelEvent(self, event): 
        event.ignore() # 👑 强制屏蔽滚轮

    def eventFilter(self, obj, event):
        if obj == self.lineEdit():
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = True; self._last_x = event.globalPosition().x()
            elif event.type() == QEvent.Type.MouseMove and self._is_dragging:
                dx = event.globalPosition().x() - self._last_x
                if abs(dx) >= 1.0:
                    self.blockSignals(True); self.setValue(self.value() + dx * self.singleStep()); self.blockSignals(False)
                    self._last_x = event.globalPosition().x()
                return True
            elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = False; self.valueChanged.emit(self.value()) 
                if hasattr(self.parent(), "push_history"): self.parent().push_history()
        return super().eventFilter(obj, event)
        
class ProScrubSpinBox(QSpinBox):
    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons) 
        self.lineEdit().setCursor(Qt.CursorShape.SizeHorCursor) 
        self._is_dragging = False
        self._last_x = 0
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self.lineEdit():
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = True
                self._last_x = event.globalPosition().x()
            elif event.type() == QEvent.Type.MouseMove and self._is_dragging:
                dx = event.globalPosition().x() - self._last_x
                if abs(dx) >= 1.0:
                    self.blockSignals(True) 
                    self.setValue(self.value() + int(dx) * self.singleStep())
                    self.blockSignals(False)
                    self._last_x = event.globalPosition().x()
                return True 
            elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = False
                self.valueChanged.emit(self.value()) 
                # 发送历史记录保存信号
                if hasattr(self.parent(), "push_history"): self.parent().push_history()
        return super().eventFilter(obj, event)

class ProScrubDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.lineEdit().setCursor(Qt.CursorShape.SizeHorCursor)
        self._is_dragging = False
        self._last_x = 0
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self.lineEdit():
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = True
                self._last_x = event.globalPosition().x()
            elif event.type() == QEvent.Type.MouseMove and self._is_dragging:
                dx = event.globalPosition().x() - self._last_x
                if abs(dx) >= 1.0:
                    self.blockSignals(True) 
                    self.setValue(self.value() + dx * self.singleStep())
                    self.blockSignals(False)
                    self._last_x = event.globalPosition().x()
                return True
            elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = False
                self.valueChanged.emit(self.value()) 
                if hasattr(self.parent(), "push_history"): self.parent().push_history()
        return super().eventFilter(obj, event)
        
        
# 👑 高级丝滑折叠抽屉组件 (Accordion UI) - 纤细优化版
class CollapsibleBox(QWidget):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.toggle_button = QPushButton(f"▶  {title}")
        self.toggle_button.setStyleSheet("""
            QPushButton { 
                text-align: left; padding: 6px 12px; font-weight: bold; 
                font-size: 13px; background-color: #232634; color: #cdd6f4; 
                border: 1px solid #313244; border-radius: 6px; 
            }
            QPushButton:hover { background-color: #313244; border-color: #89b4fa; }
            QPushButton:checked { color: #a6e3a1; border-bottom-left-radius: 0px; border-bottom-right-radius: 0px; border-bottom: none;}
        """)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False) # 默认折叠状态
        
        self.content_area = QFrame()
        self.content_area.setStyleSheet("QFrame { background-color: #181825; border: 1px solid #313244; border-top: none; border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; }")
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(10, 8, 10, 10)
        self.content_layout.setSpacing(6)
        self.content_area.setVisible(False)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 2, 0, 2)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)
        
        self.toggle_button.clicked.connect(self.on_pressed)

    def on_pressed(self):
        checked = self.toggle_button.isChecked()
        title_text = self.toggle_button.text()[3:] # 去掉前面的箭头和空格
        self.toggle_button.setText(f"{'▼' if checked else '▶'}  {title_text}")
        self.content_area.setVisible(checked)

    def addLayout(self, layout):
        self.content_layout.addLayout(layout)       

class WebBridge(QObject):
    def __init__(self, parent_controller):
        super().__init__()
        self.controller = parent_controller
        
    @Slot(int, float, float)
    def update_coordinates(self, idx, x, y):
        if 0 <= idx < len(self.controller.state["subs_data"]):
            current_clip = self.controller.state["subs_data"][idx]
            scope = self.controller.style_scope_combo.currentIndex()
            if scope == 0: target_clips = self.controller.state["subs_data"]
            elif scope == 1: target_clips = [c for c in self.controller.state["subs_data"] if c.get("track") == current_clip.get("track")]
            else: target_clips = [current_clip]

            for c in target_clips:
                c["pos_x"] = x; c["pos_y"] = y
            
            if self.controller.current_selected_idx == idx:
                self.controller.pos_x_spin.blockSignals(True); self.controller.pos_x_slider.blockSignals(True)
                self.controller.pos_y_spin.blockSignals(True); self.controller.pos_y_slider.blockSignals(True)
                
                self.controller.pos_x_spin.setValue(float(x)); self.controller.pos_x_slider.setValue(int(float(x) * 100))
                self.controller.pos_y_spin.setValue(float(y)); self.controller.pos_y_slider.setValue(int(float(y) * 100))
                
                self.controller.pos_x_spin.blockSignals(False); self.controller.pos_x_slider.blockSignals(False)
                self.controller.pos_y_spin.blockSignals(False); self.controller.pos_y_slider.blockSignals(False)
            
            self.controller.update_floating_subtitle()
            self.controller.auto_save_cache() 
            self.controller.push_history()
            
    @Slot(int, float)
    def update_box_width(self, idx, width):
        if 0 <= idx < len(self.controller.state["subs_data"]):
            current_clip = self.controller.state["subs_data"][idx]
            scope = self.controller.style_scope_combo.currentIndex()
            if scope == 0: target_clips = self.controller.state["subs_data"]
            elif scope == 1: target_clips = [c for c in self.controller.state["subs_data"] if c.get("track") == current_clip.get("track")]
            else: target_clips = [current_clip]

            for c in target_clips:
                if "style" not in c: c["style"] = self.controller.default_style.copy()
                c["style"]["box_width"] = width
            
            if self.controller.current_selected_idx == idx:
                self.controller.box_width_spin.blockSignals(True); self.controller.box_width_slider.blockSignals(True)
                self.controller.box_width_spin.setValue(float(width)); self.controller.box_width_slider.setValue(int(float(width) * 100))
                self.controller.box_width_spin.blockSignals(False); self.controller.box_width_slider.blockSignals(False)
            
            self.controller.update_floating_subtitle()
            self.controller.auto_save_cache()
            self.controller.push_history()

    @Slot(int)
    def notify_selected(self, idx): 
        self.controller.current_selected_idx = idx
        self.controller.switch_inspector("sub")
        
    @Slot(int, str)
    def update_text_from_screen(self, idx, new_text):
        if 0 <= idx < len(self.controller.state["subs_data"]):
            self.controller.sync_text_edit(idx, new_text)
            self.controller.push_history()
            
    @Slot(int, int)
    def adjust_font_size(self, idx, delta):
        if 0 <= idx < len(self.controller.state["subs_data"]):
            current_clip = self.controller.state["subs_data"][idx]
            st = current_clip.get("style", current_clip)
            new_size = max(10, min(300, st.get("size", 100) + delta))
            
            scope = self.controller.style_scope_combo.currentIndex()
            if scope == 0: target_clips = self.controller.state["subs_data"]
            elif scope == 1: target_clips = [c for c in self.controller.state["subs_data"] if c.get("track") == current_clip.get("track")]
            else: target_clips = [current_clip]
            
            for c in target_clips: 
                if "style" not in c: c["style"] = {}
                c["style"]["size"] = new_size
            if self.controller.current_selected_idx == idx: 
                self.controller.size_slider.blockSignals(True); self.controller.size_spin.blockSignals(True)
                self.controller.size_slider.setValue(new_size); self.controller.size_spin.setValue(new_size)
                self.controller.size_slider.blockSignals(False); self.controller.size_spin.blockSignals(False)
            self.controller.update_floating_subtitle(); self.controller.auto_save_cache()
            self.controller.push_history()

class EditView(QWidget):
    sig_ai_progress = Signal(str)
    sig_ai_success = Signal()
    sig_ai_error = Signal(str)
    sig_ai_finish = Signal()

    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        
        # 👑 时光机历史栈初始化
        self.history = []
        self.history_ptr = -1
        
        self.default_style = {
            "size": 100, "font": "Segoe UI", "color_txt": "#FFFFFF", "color_hl": "#FFFFFF",
            "bg_mode": "none", "bg_color": "#000000", "bg_alpha": 80, "bg_radius": 15, "bg_padding": 20,
            "hl_bg_color": "#FF0050", "hl_bg_alpha": 100, "hl_bg_radius": 8, "hl_bg_padding": 8, 
            "stroke_width": 4, "stroke_color": "#000000", "stroke_o_width": 0, "stroke_o_color": "#000000", 
            "shadow_x": 5, "shadow_y": 5, "shadow_blur": 0, "shadow_color": "#000000", "shadow_alpha": 100,
            "line_height": 1.1, "text_dir": "ltr", "use_hl": True, "hl_glow": False, "glow_size": 20,
            "anim_type": "pop", "pop_speed": 0.2, "inactive_alpha": 100, 
            "text_transform": "capitalize", "text_align": "center", "letter_spacing": 0, "word_spacing": 0,
            "layout_mode": "standard", "layout_variant": "auto", "emphasis_scale": 145,
            "box_width": 0.0, "mask_en": False, "mask_top": 20, "mask_bottom": 20,
            "merge_bridge_enable": False, "merge_bridge_width": 160, "merge_bridge_height": 16, "merge_bridge_alpha": 100,
            "bg_pad_left": 20, "bg_pad_right": 20, "bg_pad_top": 8, "bg_pad_bottom": 8,
            "hl_pad_left": 8, "hl_pad_right": 8, "hl_pad_top": 2, "hl_pad_bottom": 2
        }
        self.state = {
            "video_clips": [], "audio_path": "", "subs_data": [], "a_trim": [0.0, 10.0], "duration": 10.0,
            "resolution": "原画检测 (自动跟随)", "v_scale": 100, "v_volume": 100, "a_volume": 100,
            "chunk_mode": "双行大段 (约10字，智能折行)",
            "custom_text": "", # 👑 新增：用于保存用户文案到工程
            "default_pos_x": 0.0,
            "default_pos_y": 25.0,
            "default_style": self.default_style.copy()
        }
        self.current_selected_idx = -1; self.current_v_idx = 0; self.current_play_time = 0.0     
        self.is_playing = False; self.ui_entries = []; self.selected_track = "empty" 
        self.zoom_factor = 50.0; self.active_subs_cache = set(); self.last_render_hash = None
        self.v_wave_pixmap = None; self.a_wave_pixmap = None; self.video_thumbs = [] 
        self.proj_width = 1080; self.proj_height = 1920
        
        self.sig_ai_progress.connect(self._on_ai_progress); self.sig_ai_success.connect(self._on_ai_success)
        self.sig_ai_error.connect(self._on_ai_error); self.sig_ai_finish.connect(self._on_ai_finish)
        
        self.eng_locale = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        main_v_splitter = QSplitter(Qt.Orientation.Vertical)
        top_h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setStyleSheet("QSplitter::handle { background-color: #313244; margin: 2px; }")
        
        # 👑 注入 Ctrl+Z 快捷键
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.shortcut_undo.activated.connect(self.undo)
        self.shortcut_redo = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.shortcut_redo.activated.connect(self.redo)
        self.shortcut_redo_mac = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.shortcut_redo_mac.activated.connect(self.redo)

        # ================= 1. 左侧面板 =================
        left_panel = QFrame(); left_panel.setStyleSheet("background-color: #181825; border-radius: 8px;"); left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(8)

        top_btn_row = QHBoxLayout()
        self.btn_reset = QPushButton("🔄 清空"); self.btn_reset.setFixedHeight(35); self.btn_reset.setStyleSheet("background-color: #313244; border-radius: 5px; color: white;"); self.btn_reset.clicked.connect(self.reset_project)
        self.btn_undo = QPushButton("↩️ 撤销"); self.btn_undo.setFixedHeight(35); self.btn_undo.setStyleSheet("background-color: #313244; border-radius: 5px; color: white;"); self.btn_undo.clicked.connect(self.undo)
        self.btn_save = QPushButton("💾 保存"); self.btn_save.setFixedHeight(35); self.btn_save.setStyleSheet("background-color: #a6e3a1; font-weight: bold; border-radius: 5px; color: #11111b;"); self.btn_save.clicked.connect(self.manual_save)
        top_btn_row.addWidget(self.btn_reset); top_btn_row.addWidget(self.btn_undo); top_btn_row.addWidget(self.btn_save); left_layout.addLayout(top_btn_row)
        
        left_layout.addWidget(QLabel("🎥 V1 画面轨道控制:", styleSheet="color: #89b4fa; font-weight: bold; margin-top: 5px;"))
        self.btn_v = QPushButton("➕ 导入第一段画面 (MP4)"); self.btn_v.setFixedHeight(35); self.btn_v.setStyleSheet("background-color: #313244; color: white;"); self.btn_v.clicked.connect(self.load_video)
        self.btn_v_autofill = QPushButton("🚀 一键弹拉对齐配音"); self.btn_v_autofill.setFixedHeight(35); self.btn_v_autofill.setStyleSheet("background-color: #f9e2af; color: #11111b; font-weight: bold;"); self.btn_v_autofill.clicked.connect(self.auto_fill_video)
        self.btn_v_del = QPushButton("🗑️ 删除片段"); self.btn_v_del.setFixedHeight(35); self.btn_v_del.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold;"); self.btn_v_del.clicked.connect(self.remove_last_video_clip)
        vid_ctrl_layout = QHBoxLayout(); vid_ctrl_layout.addWidget(self.btn_v_autofill); vid_ctrl_layout.addWidget(self.btn_v_del)
        left_layout.addWidget(self.btn_v); left_layout.addLayout(vid_ctrl_layout)

        left_layout.addWidget(QLabel("🎵 A1 配音轨道:", styleSheet="color: #a6e3a1; font-weight: bold; margin-top: 5px;"))
        aud_ctrl_layout = QHBoxLayout()
        self.btn_a = QPushButton("🎵 导入独立配音 (可选)"); self.btn_a.setFixedHeight(35); self.btn_a.setStyleSheet("background-color: #313244; font-size: 13px; border-radius: 5px; color: white;"); self.btn_a.clicked.connect(self.load_audio)
        self.btn_a_del = QPushButton("🗑️ 删除"); self.btn_a_del.setFixedWidth(80); self.btn_a_del.setFixedHeight(35); self.btn_a_del.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; border-radius: 5px;"); self.btn_a_del.clicked.connect(self.remove_audio)
        aud_ctrl_layout.addWidget(self.btn_a); aud_ctrl_layout.addWidget(self.btn_a_del); left_layout.addLayout(aud_ctrl_layout)
        
        # 👑 改造剪贴板 UI：加入一键排版按钮
        text_header_layout = QHBoxLayout()
        text_header_layout.addWidget(QLabel("📝 剪贴板参考文案:", styleSheet="margin-top: 5px; font-weight: bold; color: #a6adc8;"))
        text_header_layout.addStretch()
        self.btn_clean_text = QPushButton("🧹 一键规范化清洗")
        self.btn_clean_text.setStyleSheet("background-color: #313244; color: #a6e3a1; font-weight: bold; border-radius: 4px; padding: 2px 8px; margin-top: 5px;")
        self.btn_clean_text.clicked.connect(self.format_custom_text_manually)
        text_header_layout.addWidget(self.btn_clean_text)
        left_layout.addLayout(text_header_layout)

        self.text_editor = QTextEdit()
        self.text_editor.setStyleSheet("background-color: #1e1e2e; border: 1px solid #313244; border-radius: 5px;")
        self.text_editor.textChanged.connect(self._on_custom_text_changed) # 绑定输入事件，实时保存
        left_layout.addWidget(self.text_editor, stretch=1)
        
        chunk_row = QHBoxLayout()
        chunk_row.addWidget(QLabel("✂️ 断句模式:", styleSheet="color: #89b4fa; font-weight: bold;"))
        self.chunk_mode = QComboBox()
        self.chunk_mode.addItems(["短句快速 (1-3字)", "双行大段 (约10字，智能折行)", "单字轰炸 (1字/句)"])
        self.chunk_mode.setStyleSheet("background-color: #313244; color: white; padding: 5px; border-radius: 4px;")
        chunk_row.addWidget(self.chunk_mode, stretch=1)
        self.chunk_mode.currentTextChanged.connect(self._on_chunk_mode_change)
        left_layout.addLayout(chunk_row)

        self.btn_extract = QPushButton("🤖 AI 听译打轴"); self.btn_extract.setStyleSheet("background-color: #f59e0b; color: #11111b; font-weight: bold; padding: 10px; border-radius: 5px;"); self.btn_extract.clicked.connect(self.start_extract); left_layout.addWidget(self.btn_extract)
        self.status_lbl = QLabel("✅ 引擎就绪"); self.status_lbl.setStyleSheet("color: #a6e3a1; font-weight: bold;"); left_layout.addWidget(self.status_lbl)

        # ================= 2. 中间面板 =================
        center_panel = QFrame(); center_panel.setStyleSheet("background-color: #11111b; border-radius: 8px;"); center_layout = QVBoxLayout(center_panel)
        stack_widget = QWidget(); stack_widget.setStyleSheet("background-color: #000;"); grid = QGridLayout(stack_widget); grid.setContentsMargins(0, 0, 0, 0)
        self.video_label = QLabel(); self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.player = QMediaPlayer(); self.audio_output = QAudioOutput(); self.player.setAudioOutput(self.audio_output); self.video_sink = QVideoSink()
        self.player.setVideoOutput(self.video_sink); self.video_sink.videoFrameChanged.connect(self.on_video_frame)
        self.audio_player = QMediaPlayer(); self.audio_track_output = QAudioOutput(); self.audio_player.setAudioOutput(self.audio_track_output)
        
        self.browser = QWebEngineView(); self.browser.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.browser.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); self.browser.page().setBackgroundColor(Qt.GlobalColor.transparent)
        
        self.bridge = WebBridge(self); self.channel = QWebChannel(); self.channel.registerObject("backend", self.bridge); self.browser.page().setWebChannel(self.channel)
        
        grid.addWidget(self.video_label, 0, 0); grid.addWidget(self.browser, 0, 0); self.browser.raise_()
        self.aspect_container = AspectRatioContainer(stack_widget); center_layout.addWidget(self.aspect_container, stretch=1)
        
        ctrl_row = QHBoxLayout(); self.btn_play = QPushButton("▶️ 播放"); self.btn_play.setFixedSize(80, 30); self.btn_play.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; border-radius: 5px;"); self.btn_play.clicked.connect(self.toggle_play); ctrl_row.addWidget(self.btn_play)
        self.btn_add_text = QPushButton("➕ 在当前时间加文字"); self.btn_add_text.setFixedSize(160, 30); self.btn_add_text.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; border-radius: 5px;"); self.btn_add_text.clicked.connect(self.add_manual_text)
        self.chk_safe_area = QCheckBox("显示安全框"); self.chk_safe_area.setChecked(True); self.chk_safe_area.setStyleSheet("color: #a6e3a1; font-weight: bold; margin-left: 15px;"); self.chk_safe_area.stateChanged.connect(self.toggle_safe_area)
        ctrl_row.addWidget(self.btn_add_text); ctrl_row.addWidget(self.chk_safe_area)
        self.lbl_time = QLabel("00:00.0 / 00:00.0"); self.lbl_time.setStyleSheet("font-family: Consolas; color: #f9e2af; margin-left: 15px;"); ctrl_row.addWidget(self.lbl_time); ctrl_row.addStretch(); center_layout.addLayout(ctrl_row)

        # ================= 3. 右侧面板 =================
        right_panel = QFrame(); right_panel.setStyleSheet("background-color: #181825; border-radius: 8px;"); right_layout = QVBoxLayout(right_panel)
        self.tabs = QTabWidget(); self.tabs.setStyleSheet("QTabBar::tab:selected { background: #313244; color: #cdd6f4; font-weight: bold;}")
        tab_subs = QWidget(); subs_layout = QVBoxLayout(tab_subs); subs_scroll = QScrollArea(); subs_scroll.setWidgetResizable(True); subs_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        self.scroll_content = QWidget(); self.scroll_layout = QVBoxLayout(self.scroll_content); self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_layout.setSpacing(10); self.scroll_layout.setContentsMargins(5, 5, 5, 5)
        subs_scroll.setWidget(self.scroll_content); subs_layout.addWidget(subs_scroll)
        self.insp_stack = QStackedWidget()
        
        def create_slider_spinbox(layout, label, min_v, max_v, default_v, callback, is_float=False):
            row = QHBoxLayout(); row.addWidget(QLabel(label)); slider = NoScrollSlider(Qt.Orientation.Horizontal)
            if is_float:
                slider.setRange(int(min_v*100), int(max_v*100)); spinbox = ProScrubDoubleSpinBox(); spinbox.setRange(min_v, max_v); spinbox.setSingleStep(0.05); spinbox.setLocale(self.eng_locale)
                spinbox.setValue(float(default_v)); slider.setValue(int(default_v*100))
                slider.valueChanged.connect(lambda v: spinbox.setValue(float(v)/100.0)); spinbox.valueChanged.connect(lambda v: slider.setValue(int(v*100)))
            else:
                slider.setRange(min_v, max_v); spinbox = ProScrubSpinBox(); spinbox.setRange(min_v, max_v)
                spinbox.setValue(int(default_v)); slider.setValue(int(default_v))
                slider.valueChanged.connect(spinbox.setValue); spinbox.valueChanged.connect(slider.setValue)
            spinbox.setStyleSheet("background: #25262b; border: 1px solid #313244; color: white; padding: 2px 5px; border-radius: 3px;"); spinbox.setFixedWidth(80); row.setSpacing(15); spinbox.valueChanged.connect(lambda v: callback())
            row.addWidget(slider); row.addWidget(spinbox); layout.addLayout(row)
            return slider, spinbox

        def create_section_frame(title, accent="#a6e3a1"):
            frame = QFrame()
            frame.setObjectName("inspectorSection")
            frame.setStyleSheet(
                f"QFrame#inspectorSection {{ background-color: #1b1d31; border: 1px solid #313244; border-radius: 10px; }}"
                f"QLabel[role='section_title'] {{ color: {accent}; font-weight: 700; font-size: 13px; padding: 2px 0; }}"
            )
            outer = QVBoxLayout(frame)
            outer.setContentsMargins(12, 10, 12, 10)
            outer.setSpacing(8)
            title_label = QLabel(title)
            title_label.setProperty("role", "section_title")
            outer.addWidget(title_label)
            return frame, outer

        page_empty = QWidget(); QVBoxLayout(page_empty).addWidget(QLabel("没有选中任何片段\n\n请在时间线上点击以查看属性\n\n提示: 右侧已改成侧边分类，不用一直往下滑", alignment=Qt.AlignmentFlag.AlignCenter, styleSheet="color: gray;"))
        insp_scroll = QScrollArea(); insp_scroll.setWidgetResizable(True); insp_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }"); page_sub = QWidget(); sub_layout = QVBoxLayout(page_sub)
        sub_layout.setSpacing(10)

        def create_nav_btn(text, idx):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setMinimumHeight(34)
            btn.setStyleSheet("QPushButton {background-color:#232634; color:#cdd6f4; border:1px solid #313244; border-radius:8px; padding:6px 10px; text-align:left;} QPushButton:checked {background-color:#313244; color:#a6e3a1; border-color:#89b4fa; font-weight:bold;}")
            btn.clicked.connect(lambda: self._switch_sub_page(idx))
            return btn

        top_ctrl_row = QHBoxLayout()
        self.style_scope_combo = QComboBox(); self.style_scope_combo.addItems(["🔗 样式应用到: 全部轨道", "📏 仅应用到: 当前同轨道", "🎯 仅应用到: 独立片段"]); self.style_scope_combo.setStyleSheet("background-color: #313244; color: #a6e3a1; font-weight: bold; padding: 5px;")
        self.btn_del_clip = QPushButton("🗑️ 删除"); self.btn_del_clip.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; border-radius: 6px; padding: 6px 10px;"); self.btn_del_clip.clicked.connect(self.delete_current_clip)
        top_ctrl_row.addWidget(self.style_scope_combo, stretch=1); top_ctrl_row.addSpacing(8); top_ctrl_row.addWidget(self.btn_del_clip); sub_layout.addLayout(top_ctrl_row)

        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox(); self.preset_combo.setStyleSheet("background-color: #11111b; color: #cdd6f4; font-weight: bold; border: 1px solid #313244; border-radius: 6px; padding: 6px;")
        self.btn_apply_preset = QPushButton("✨ 应用"); self.btn_apply_preset.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; border-radius: 6px; padding: 6px 10px;")
        self.btn_save_preset = QPushButton("💾 存预设"); self.btn_save_preset.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; border-radius: 6px; padding: 6px 10px;")
        self.btn_del_preset = QPushButton("❌"); self.btn_del_preset.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; border-radius: 6px; padding: 6px 10px; width: 30px;")
        preset_row.addWidget(QLabel("🎨 预设库:")); preset_row.addWidget(self.preset_combo, stretch=1); preset_row.addWidget(self.btn_apply_preset); preset_row.addWidget(self.btn_save_preset); preset_row.addWidget(self.btn_del_preset)
        sub_layout.addLayout(preset_row)
        self.btn_apply_preset.clicked.connect(self.apply_style_preset); self.btn_save_preset.clicked.connect(self.save_style_preset); self.btn_del_preset.clicked.connect(self.delete_style_preset)

        self.preset_preview_label = QLabel("Text")
        self.preset_preview_label.setMinimumHeight(72)
        self.preset_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preset_preview_label.setWordWrap(True)
        self.preset_preview_label.setStyleSheet("background-color:#11111b; border:1px dashed #45475a; border-radius:10px; color:#ffffff; padding:10px;")
        sub_layout.addWidget(self.preset_preview_label)
        self.preset_combo.currentIndexChanged.connect(self._update_preset_preview)

        body_row = QHBoxLayout(); body_row.setSpacing(10)
        nav_col = QVBoxLayout(); nav_col.setSpacing(6)
        self.sub_page_buttons = []
        for idx, text_btn in enumerate(["⏱️ 时间", "🔤 字体排版", "🎬 动画效果", "🎨 颜色描边", "🔲 底框阴影"]):
            btn = create_nav_btn(text_btn, idx)
            self.sub_page_buttons.append(btn)
            nav_col.addWidget(btn)
        nav_col.addStretch(); body_row.addLayout(nav_col)

        self.sub_pages = QStackedWidget(); self.sub_pages.setStyleSheet("QStackedWidget { background: transparent; }")
        body_row.addWidget(self.sub_pages, stretch=1)
        sub_layout.addLayout(body_row)

        page_timing = QWidget(); page_timing_layout = QVBoxLayout(page_timing); page_timing_layout.setSpacing(10)
        sec_duration, duration_layout = create_section_frame("⏱️ 长度控制 (Duration)", "#f9e2af")
        s_time_row = QHBoxLayout()
        s_time_row.addWidget(QLabel("起点 (s):")); self.sub_start_spin = ProScrubDoubleSpinBox(); self.sub_start_spin.setRange(0, 36000); self.sub_start_spin.setSingleStep(0.1); self.sub_start_spin.setLocale(self.eng_locale); self.sub_start_spin.setStyleSheet("background: #25262b; border: 1px solid #313244; color: white; padding: 2px 5px; border-radius: 3px;"); self.sub_start_spin.valueChanged.connect(self._on_sub_time_change); s_time_row.addWidget(self.sub_start_spin)
        s_time_row.addWidget(QLabel("终点 (s):")); self.sub_end_spin = ProScrubDoubleSpinBox(); self.sub_end_spin.setRange(0, 36000); self.sub_end_spin.setSingleStep(0.1); self.sub_end_spin.setLocale(self.eng_locale); self.sub_end_spin.setStyleSheet("background: #25262b; border: 1px solid #313244; color: white; padding: 2px 5px; border-radius: 3px;"); self.sub_end_spin.valueChanged.connect(self._on_sub_time_change); s_time_row.addWidget(self.sub_end_spin)
        duration_layout.addLayout(s_time_row)
        page_timing_layout.addWidget(sec_duration)
        sec_transform, transform_layout = create_section_frame("📍 变换与排版 (Transform)", "#89b4fa")
        self.pos_x_slider, self.pos_x_spin = create_slider_spinbox(transform_layout, "X 偏移 (%):", -100, 100, 0, self._on_style_change, is_float=True)
        self.pos_y_slider, self.pos_y_spin = create_slider_spinbox(transform_layout, "Y 偏移 (%):", -100, 100, 25, self._on_style_change, is_float=True)
        self.rot_slider, self.rot_spin = create_slider_spinbox(transform_layout, "旋转角度:", -180, 180, 0, self._on_style_change)
        self.box_width_slider, self.box_width_spin = create_slider_spinbox(transform_layout, "容器宽% (0=自适应):", 0, 100, 0, self._on_style_change, is_float=True)
        page_timing_layout.addWidget(sec_transform)
        sec_mask, mask_layout = create_section_frame("🌫️ 蒙版与遮罩 (Masking)", "#81c8be")
        self.chk_mask_en = QCheckBox("🌟 启用上下羽化遮罩"); self.chk_mask_en.setChecked(False); self.chk_mask_en.stateChanged.connect(self._on_style_change); mask_layout.addWidget(self.chk_mask_en)
        self.mask_top_slider, self.mask_top_spin = create_slider_spinbox(mask_layout, "顶部羽化 %:", 0, 50, 20, self._on_style_change)
        self.mask_bot_slider, self.mask_bot_spin = create_slider_spinbox(mask_layout, "底部羽化 %:", 0, 50, 20, self._on_style_change)
        page_timing_layout.addWidget(sec_mask)
        page_timing_layout.addStretch(); self.sub_pages.addWidget(page_timing)

        page_typo = QWidget(); page_typo_layout = QVBoxLayout(page_typo); page_typo_layout.setSpacing(10)
        sec_typo, typo_layout = create_section_frame("🔤 字体样式与高级排版 (Typography)", "#a6e3a1")
        self.font_category_combo = QComboBox(); self.font_category_combo.addItems(["全部字体", "中文优先", "拉丁/英文字体", "等宽字体"]); self.font_category_combo.setStyleSheet("background-color: #313244; padding: 5px;"); self.font_category_combo.currentTextChanged.connect(self._set_font_filter); typo_layout.addWidget(self.font_category_combo)
        self.font_var = QFontComboBox(); self.font_var.setStyleSheet("background-color: #313244; color: white; padding: 6px; border-radius: 5px;"); self.font_var.currentFontChanged.connect(self._on_style_change); self.font_var.currentFontChanged.connect(self._update_font_preview)
        typo_layout.addWidget(self.font_var)
        self.font_preview_input = QLineEdit("Text")
        self.font_preview_input.setPlaceholderText("输入要预览的字，比如 Text")
        self.font_preview_input.setStyleSheet("background-color: #11111b; color: #cdd6f4; border: 1px solid #313244; border-radius: 6px; padding: 6px 8px;")
        self.font_preview_input.textChanged.connect(self._update_font_preview)
        typo_layout.addWidget(self.font_preview_input)
        self.font_preview_label = QLabel("Text")
        self.font_preview_label.setMinimumHeight(88)
        self.font_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.font_preview_label.setWordWrap(True)
        self.font_preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.font_preview_label.setStyleSheet("background-color: #11111b; border: 1px dashed #45475a; border-radius: 8px; color: #ffffff; padding: 12px;")
        typo_layout.addWidget(self.font_preview_label)
        self.layout_mode_combo = QComboBox(); self.layout_mode_combo.addItems(["标准排版", "大小对比排版", "三层模板排版"]); self.layout_mode_combo.setStyleSheet("background-color: #313244; padding: 5px; font-weight: bold;"); self.layout_mode_combo.currentTextChanged.connect(self._on_style_change); typo_layout.addWidget(self.layout_mode_combo)
        self.layout_variant_combo = QComboBox(); self.layout_variant_combo.addItems(["自动变化", "小-大-小", "大-小-混排", "混排-大-小"]); self.layout_variant_combo.setStyleSheet("background-color: #313244; padding: 5px;"); self.layout_variant_combo.currentTextChanged.connect(self._on_style_change); typo_layout.addWidget(self.layout_variant_combo)
        self.size_slider, self.size_spin = create_slider_spinbox(typo_layout, "字体大小:", 10, 300, 100, self._on_style_change)
        self.spacing_slider, self.spacing_spin = create_slider_spinbox(typo_layout, "字距缩放:", -20, 100, 0, self._on_style_change)
        self.word_spacing_slider, self.word_spacing_spin = create_slider_spinbox(typo_layout, "词距:", 0, 80, 0, self._on_style_change)
        self.emphasis_slider, self.emphasis_spin = create_slider_spinbox(typo_layout, "大小对比 %:", 100, 220, 145, self._on_style_change)
        self.align_combo = QComboBox(); self.align_combo.addItems(["居中对齐 (Center)", "左对齐 (Left)", "右对齐 (Right)", "两端对齐 (Justify)"]); self.align_combo.setStyleSheet("background-color: #313244; padding: 5px;"); self.align_combo.currentTextChanged.connect(self._on_style_change); typo_layout.addWidget(self.align_combo)
        self.lineh_slider, self.lineh_spin = create_slider_spinbox(typo_layout, "行距缩放:", 10, 300, 110, self._on_style_change)
        self.transform_combo = QComboBox(); self.transform_combo.addItems(["首字母大写 (Capitalize)", "全部大写 (UPPERCASE)", "全部小写 (lowercase)", "正常 (Normal)"]); self.transform_combo.setStyleSheet("background-color: #313244; padding: 5px;"); self.transform_combo.currentTextChanged.connect(self._on_style_change); typo_layout.addWidget(self.transform_combo)
        page_typo_layout.addWidget(sec_typo); page_typo_layout.addStretch(); self.sub_pages.addWidget(page_typo)

        page_anim = QWidget(); page_anim_layout = QVBoxLayout(page_anim); page_anim_layout.setSpacing(10)
        sec_anim, anim_layout = create_section_frame("🎬 动态特效 (Animation)", "#f9e2af")
        self.anim_combo = QComboBox(); self.anim_combo.addItems(["🎉 逐字弹跳 (Pop-in)", "☁️ 柔和淡入 (Fade)", "⬆️ 电影级向上滚动 (Roll Up)", "🚫 无动画 (None)"]); self.anim_combo.setStyleSheet("background-color: #313244; padding: 5px;"); self.anim_combo.currentTextChanged.connect(self._on_style_change); anim_layout.addWidget(self.anim_combo)
        self.pop_speed_slider, self.pop_speed_spin = create_slider_spinbox(anim_layout, "动画速度(秒):", 0.05, 2.0, 0.2, self._on_style_change, is_float=True)
        self.pop_bounce_slider, self.pop_bounce_spin = create_slider_spinbox(anim_layout, "弹跳弹性 %:", 100, 220, 140, self._on_style_change)
        self.inactive_alpha_slider, self.inactive_alpha_spin = create_slider_spinbox(anim_layout, "未读文字透明:", 0, 100, 100, self._on_style_change)
        page_anim_layout.addWidget(sec_anim); page_anim_layout.addStretch(); self.sub_pages.addWidget(page_anim)

        page_fx = QWidget(); page_fx_layout = QVBoxLayout(page_fx); page_fx_layout.setSpacing(10)
        sec_fx, fx_layout = create_section_frame("🎨 颜色与特效 (Effects)", "#f5c2e7")
        hl_row = QHBoxLayout()
        self.chk_use_hl = QCheckBox("🌟 启用高亮"); self.chk_use_hl.setChecked(True); self.chk_use_hl.stateChanged.connect(self._on_style_change); hl_row.addWidget(self.chk_use_hl)
        self.chk_hl_glow = QCheckBox("✨ 加光特效"); self.chk_hl_glow.setChecked(False); self.chk_hl_glow.stateChanged.connect(self._on_style_change); hl_row.addWidget(self.chk_hl_glow); fx_layout.addLayout(hl_row)
        self.glow_size_slider, self.glow_size_spin = create_slider_spinbox(fx_layout, "发光强度:", 0, 100, 20, self._on_style_change)
        color_row = QHBoxLayout(); self.btn_color_txt = QPushButton("🤍 正文色"); self.btn_color_txt.setStyleSheet("background-color: #313244; padding: 5px;"); self.btn_color_txt.clicked.connect(lambda: self._pick_color("txt")); self.btn_color_hl = QPushButton("💛 高亮文字色"); self.btn_color_hl.setStyleSheet("background-color: #313244; padding: 5px;"); self.btn_color_hl.clicked.connect(lambda: self._pick_color("hl")); color_row.addWidget(self.btn_color_txt); color_row.addWidget(self.btn_color_hl); fx_layout.addLayout(color_row)
        page_fx_layout.addWidget(sec_fx)
        sec_stroke, stroke_layout = create_section_frame("🖍️ 描边 (Stroke)", "#a6e3a1")
        self.btn_color_stroke = QPushButton("⬛ 内描边色"); self.btn_color_stroke.setStyleSheet("background-color: #313244; padding: 5px;"); self.btn_color_stroke.clicked.connect(lambda: self._pick_color("stroke")); self.btn_color_stroke_o = QPushButton("⬜ 外描边色"); self.btn_color_stroke_o.setStyleSheet("background-color: #313244; padding: 5px;"); self.btn_color_stroke_o.clicked.connect(lambda: self._pick_color("stroke_o"))
        stroke_row = QHBoxLayout(); stroke_row.addWidget(self.btn_color_stroke); stroke_row.addWidget(self.btn_color_stroke_o); stroke_layout.addLayout(stroke_row)
        self.stroke_slider, self.stroke_spin = create_slider_spinbox(stroke_layout, "内描边粗细:", 0, 50, 4, self._on_style_change)
        self.stroke_o_slider, self.stroke_o_spin = create_slider_spinbox(stroke_layout, "外描边粗细:", 0, 50, 0, self._on_style_change)
        page_fx_layout.addWidget(sec_stroke); page_fx_layout.addStretch(); self.sub_pages.addWidget(page_fx)

        page_bg = QWidget(); page_bg_layout = QVBoxLayout(page_bg); page_bg_layout.setSpacing(10)
        sec_shadow, shadow_layout = create_section_frame("🕳️ 硬阴影 (Drop Shadow)", "#cba6f7")
        self.btn_color_sh = QPushButton("⬛ 阴影颜色"); self.btn_color_sh.setStyleSheet("background-color: #313244; padding: 5px;"); self.btn_color_sh.clicked.connect(lambda: self._pick_color("sh")); shadow_layout.addWidget(self.btn_color_sh)
        self.sh_x_slider, self.sh_x_spin = create_slider_spinbox(shadow_layout, "X 偏移:", -50, 50, 5, self._on_style_change)
        self.sh_y_slider, self.sh_y_spin = create_slider_spinbox(shadow_layout, "Y 偏移:", -50, 50, 5, self._on_style_change)
        self.sh_blur_slider, self.sh_blur_spin = create_slider_spinbox(shadow_layout, "模糊度:", 0, 50, 0, self._on_style_change)
        self.sh_a_slider, self.sh_a_spin = create_slider_spinbox(shadow_layout, "不透明度 %:", 0, 100, 100, self._on_style_change)
        page_bg_layout.addWidget(sec_shadow)
        sec_bg, bg_layout = create_section_frame("🔲 底框与贴纸 (Background)", "#f9e2af")
        self.bg_mode_combo = QComboBox()
        self.bg_mode_combo.addItems(["🚫 无底框 (纯白字默认)", "🟥 逐字单点底盒 (Tape)", "🌊 KTV渐变底盒 (Sweep)", "🔲 全局大底框 (Block)", "🧱 全部框架 (Full Frame)"])
        self.bg_mode_combo.setStyleSheet("background-color: #313244; padding: 5px; font-weight: bold;")
        self.bg_mode_combo.currentTextChanged.connect(self._on_style_change)
        bg_layout.addWidget(self.bg_mode_combo)
        bg_color_row = QHBoxLayout(); self.btn_color_bg = QPushButton("⬛ 底层胶带色"); self.btn_color_bg.setStyleSheet("background-color: #313244; padding: 5px;"); self.btn_color_bg.clicked.connect(lambda: self._pick_color("bg")); self.btn_color_hl_bg = QPushButton("🟥 单词高亮底盒色"); self.btn_color_hl_bg.setStyleSheet("background-color: #313244; padding: 5px;"); self.btn_color_hl_bg.clicked.connect(lambda: self._pick_color("hl_bg")); bg_color_row.addWidget(self.btn_color_bg); bg_color_row.addWidget(self.btn_color_hl_bg); bg_layout.addLayout(bg_color_row)
        self.alpha_slider, self.alpha_spin = create_slider_spinbox(bg_layout, "透明度 %:", 0, 100, 80, self._on_style_change)
        self.radius_slider, self.radius_spin = create_slider_spinbox(bg_layout, "圆角:", 0, 100, 15, self._on_style_change)
        self.padding_slider, self.padding_spin = create_slider_spinbox(bg_layout, "扩展边缘:", 0, 100, 20, self._on_style_change)
        self.bg_pad_left_slider, self.bg_pad_left_spin = create_slider_spinbox(bg_layout, "左扩展:", 0, 120, 20, self._on_style_change)
        self.bg_pad_right_slider, self.bg_pad_right_spin = create_slider_spinbox(bg_layout, "右扩展:", 0, 120, 20, self._on_style_change)
        self.bg_pad_top_slider, self.bg_pad_top_spin = create_slider_spinbox(bg_layout, "上扩展:", 0, 80, 8, self._on_style_change)
        self.bg_pad_bottom_slider, self.bg_pad_bottom_spin = create_slider_spinbox(bg_layout, "下扩展:", 0, 80, 8, self._on_style_change)
        self.hl_alpha_slider, self.hl_alpha_spin = create_slider_spinbox(bg_layout, "高亮透明度 %:", 0, 100, 100, self._on_style_change)
        self.hl_radius_slider, self.hl_radius_spin = create_slider_spinbox(bg_layout, "高亮圆角:", 0, 100, 8, self._on_style_change)
        self.hl_padding_slider, self.hl_padding_spin = create_slider_spinbox(bg_layout, "高亮扩展边缘:", 0, 100, 8, self._on_style_change)
        self.hl_pad_left_slider, self.hl_pad_left_spin = create_slider_spinbox(bg_layout, "高亮左扩展:", 0, 80, 8, self._on_style_change)
        self.hl_pad_right_slider, self.hl_pad_right_spin = create_slider_spinbox(bg_layout, "高亮右扩展:", 0, 80, 8, self._on_style_change)
        self.hl_pad_top_slider, self.hl_pad_top_spin = create_slider_spinbox(bg_layout, "高亮上扩展:", 0, 40, 2, self._on_style_change)
        self.hl_pad_bottom_slider, self.hl_pad_bottom_spin = create_slider_spinbox(bg_layout, "高亮下扩展:", 0, 40, 2, self._on_style_change)
        self.chk_merge_bridge = QCheckBox("🔗 启用中间桥接黑层"); self.chk_merge_bridge.setChecked(False); self.chk_merge_bridge.stateChanged.connect(self._on_style_change); bg_layout.addWidget(self.chk_merge_bridge)
        self.merge_bridge_width_slider, self.merge_bridge_width_spin = create_slider_spinbox(bg_layout, "桥接层宽度:", 20, 400, 160, self._on_style_change)
        self.merge_bridge_height_slider, self.merge_bridge_height_spin = create_slider_spinbox(bg_layout, "桥接层厚度:", 4, 80, 16, self._on_style_change)
        self.merge_bridge_alpha_slider, self.merge_bridge_alpha_spin = create_slider_spinbox(bg_layout, "桥接层透明度 %:", 0, 100, 100, self._on_style_change)
        page_bg_layout.addWidget(sec_bg); page_bg_layout.addStretch(); self.sub_pages.addWidget(page_bg)

        sub_layout.addStretch(); insp_scroll.setWidget(page_sub)

        page_vid = QWidget(); vid_layout = QVBoxLayout(page_vid)
        vid_layout.addWidget(QLabel("⏱️ 复合片段长度控制:", styleSheet="color: #89b4fa; font-weight: bold; margin-top: 10px;"))
        v_time_row = QHBoxLayout()
        v_time_row.addWidget(QLabel("起点 (s):")); self.v_start_spin = ProScrubDoubleSpinBox(); self.v_start_spin.setRange(0, 36000); self.v_start_spin.setLocale(self.eng_locale); self.v_start_spin.setStyleSheet("background: #25262b; border: 1px solid #313244; color: white; padding: 2px 5px; border-radius: 3px;"); self.v_start_spin.valueChanged.connect(self._on_v_time_change); v_time_row.addWidget(self.v_start_spin)
        v_time_row.addWidget(QLabel("终点 (s):")); self.v_end_spin = ProScrubDoubleSpinBox(); self.v_end_spin.setRange(0, 36000); self.v_end_spin.setLocale(self.eng_locale); self.v_end_spin.setStyleSheet("background: #25262b; border: 1px solid #313244; color: white; padding: 2px 5px; border-radius: 3px;"); self.v_end_spin.valueChanged.connect(self._on_v_time_change); v_time_row.addWidget(self.v_end_spin)
        vid_layout.addLayout(v_time_row)
        
        self.res_combo = QComboBox(); self.res_combo.addItems(["自动检测 (自动跟随)", "竖屏 1080x1920", "横屏 1920x1080", "正方 1080x1080"]); self.res_combo.setStyleSheet("background-color: #313244; padding: 5px; color: #f9e2af; margin-top: 10px;"); self.res_combo.currentTextChanged.connect(self.on_resolution_changed); vid_layout.addWidget(QLabel("📐 全局比例:")); vid_layout.addWidget(self.res_combo)
        vid_layout.addWidget(QLabel("🎞️ 画面设置", alignment=Qt.AlignmentFlag.AlignCenter)); self.v_scale_slider, self.v_scale_spin = create_slider_spinbox(vid_layout, "画面缩放 %:", 10, 300, 100, self._on_vid_prop_change); self.v_vol_slider, self.v_vol_spin = create_slider_spinbox(vid_layout, "原声音量 %:", 0, 100, 100, self._on_vid_prop_change)
        vid_layout.addStretch()

        page_aud = QWidget(); aud_layout = QVBoxLayout(page_aud); aud_layout.addWidget(QLabel("🎵 配音音量设置", alignment=Qt.AlignmentFlag.AlignCenter)); self.a_vol_slider, self.a_vol_spin = create_slider_spinbox(aud_layout, "配音音量 %:", 0, 100, 100, self._on_aud_prop_change); aud_layout.addStretch()

        self.insp_stack.addWidget(page_empty); self.insp_stack.addWidget(insp_scroll); self.insp_stack.addWidget(page_vid); self.insp_stack.addWidget(page_aud)
        self.tabs.addTab(tab_subs, "📝 精修"); self.tabs.addTab(self.insp_stack, "🎛️ 检查器"); right_layout.addWidget(self.tabs)

        timeline_outer = QFrame(); timeline_outer.setStyleSheet("background-color: #1e1e2e; border-radius: 8px;"); tl_outer_layout = QHBoxLayout(timeline_outer); tl_outer_layout.setContentsMargins(0,0,0,0); tl_outer_layout.setSpacing(0)
        self.tl_header = TimelineHeader(controller=self); tl_outer_layout.addWidget(self.tl_header)
        self.timeline_widget = AdvancedTimeline(controller=self); tl_outer_layout.addWidget(self.timeline_widget, stretch=1)
        
        top_h_splitter.addWidget(left_panel)
        top_h_splitter.addWidget(center_panel)
        top_h_splitter.addWidget(right_panel)
        top_h_splitter.setSizes([280, 780, 500]) 

        main_v_splitter.addWidget(top_h_splitter) 
        main_v_splitter.addWidget(timeline_outer) 
        main_v_splitter.setSizes([700, 250])      
        
        main_layout.addWidget(main_v_splitter)

        self.load_project_on_boot(); self.init_web_engine_once(); self._switch_sub_page(1); self._update_font_preview(); self._update_preset_preview(); self.switch_inspector("empty")
        self.refresh_preset_combo()

        QTimer.singleShot(1000, self.check_and_download_ffmpeg)

    # 👑 时光机核心引擎
    def push_history(self):
        if not hasattr(self, "history"):
            self.history = []
            self.history_ptr = -1
        
        if self.history_ptr < len(self.history) - 1:
            self.history = self.history[:self.history_ptr + 1]
            
        current_state = copy.deepcopy(self.state["subs_data"])
        
        if self.history and self.history[-1] == current_state:
            return
            
        self.history.append(current_state)
        self.history_ptr += 1
        
        if len(self.history) > 50:
            self.history.pop(0)
            self.history_ptr -= 1

    def undo(self):
        if getattr(self, "history_ptr", -1) > 0:
            self.history_ptr -= 1
            self.state["subs_data"] = copy.deepcopy(self.history[self.history_ptr])
            self.render_ui_list()
            self.update_timeline_size()
            self.update_floating_subtitle()
            self.auto_save_cache()
            self.status_lbl.setText("↩️ 已撤销操作")

    def redo(self):
        if hasattr(self, "history") and self.history_ptr < len(self.history) - 1:
            self.history_ptr += 1
            self.state["subs_data"] = copy.deepcopy(self.history[self.history_ptr])
            self.render_ui_list()
            self.update_timeline_size()
            self.update_floating_subtitle()
            self.auto_save_cache()
            self.status_lbl.setText("↪️ 已重做操作")

    def check_and_download_ffmpeg(self):
        cmd = get_ffmpeg_cmd()
        try:
            flags = 0x08000000 if os.name == 'nt' else 0
            subprocess.run([cmd, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            return  
        except:
            pass  

        reply = QMessageBox.question(self, '检测到核心引擎缺失', '首次运行或未打包环境。\n为了正常进行“AI 听译”和“音视频处理”，是否立即自动从云端节点下载部署引擎？（文件约130MB，请保持网络畅通）', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.download_ffmpeg()
        else:
            self.status_lbl.setText("❌ 缺少 FFmpeg，听译将不可用")

    def download_ffmpeg(self):
        self.progress = QProgressDialog("正在从云端安全节点极速拉取引擎...", "取消", 0, 100, self)
        self.progress.setWindowTitle("自动部署引擎环境")
        self.progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress.setAutoClose(True)
        self.progress.show()
        self.dl_thread = threading.Thread(target=self._dl_ffmpeg_task, daemon=True)
        self.dl_thread.start()

    def _dl_ffmpeg_task(self):
        url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        zip_path = os.path.join(tempfile.gettempdir(), "sh_ffmpeg_temp.zip")
        try:
            def report(block_num, block_size, total_size):
                if total_size > 0:
                    percent = int(block_num * block_size * 100 / total_size)
                    if not self.progress.wasCanceled():
                        QTimer.singleShot(0, lambda: self.progress.setValue(min(percent, 99)))

            urllib.request.urlretrieve(url, zip_path, reporthook=report)
            if self.progress.wasCanceled(): raise Exception("用户取消了下载。")

            QTimer.singleShot(0, lambda: self.progress.setLabelText("正在进行静默解压组装..."))

            app_dir = get_app_dir()
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    if file_info.filename.endswith('ffmpeg.exe'):
                        file_info.filename = 'ffmpeg.exe'
                        zip_ref.extract(file_info, app_dir)
                    elif file_info.filename.endswith('ffprobe.exe'):
                        file_info.filename = 'ffprobe.exe'
                        zip_ref.extract(file_info, app_dir)

            QTimer.singleShot(0, lambda: self.progress.setValue(100))
            QTimer.singleShot(0, lambda: QMessageBox.information(self, "部署成功", "🎉 引擎已组装完毕！\n现在软件已经是“终极满血完全体”了，所有功能无缝可用！"))
            QTimer.singleShot(0, lambda: self.status_lbl.setText("✅ 引擎就绪"))
            
        except Exception as e:
            QTimer.singleShot(0, lambda: self.progress.cancel())
            if "取消" not in str(e):
                QTimer.singleShot(0, lambda: QMessageBox.critical(self, "部署受挫", f"自动下载似乎遇到了点麻烦：\n{str(e)}\n\n您可以检查下网络，或者自己去弄个 ffmpeg.exe 扔进本软件目录里。"))
        finally:
            if os.path.exists(zip_path):
                try: os.remove(zip_path)
                except: pass

    def _on_chunk_mode_change(self, text):
        self.state["chunk_mode"] = text
        self.auto_save_cache()

    def init_web_engine_once(self):
        html_content = r"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                html, body { margin: 0; padding: 0; background: transparent; overflow: hidden; width: 100vw; height: 100vh; display: flex; justify-content: center; align-items: center; -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }
                #scale-wrapper { width: 100vw; height: 100vh; position: absolute; left: 0; top: 0; transition: transform 0.15s ease-out; }
                
                .drag-container { position: absolute; transform: translate(-50%, -50%); width: max-content; max-width: 92%; }
                .sub-box { outline: none; }
                
                #safe-area { position: absolute; top: 15%; bottom: 20%; left: 10%; right: 10%; border: 2px dashed rgba(255, 255, 255, 0.4); pointer-events: none; z-index: 999; }
                
                /* 👑 冰蓝呼吸灯高光边框 */
                .selected-box { 
                    border: 2px solid rgba(137, 180, 250, 1) !important; 
                    box-shadow: 0 0 15px 4px rgba(137, 180, 250, 0.5) !important;
                    border-radius: 8px;
                    z-index: 9999 !important;
                }
                .sub-box:hover { border: 2px dashed rgba(255,255,255,0.7); cursor: move; }
                
                .width-handle { 
                    position: absolute; width: 6px; height: 24px; background: white; 
                    border: 2px solid rgba(137, 180, 250, 1); border-radius: 4px; 
                    display: none; z-index: 20; top: 50%; transform: translateY(-50%); 
                    cursor: ew-resize; box-shadow: 0 0 5px rgba(0,0,0,0.5);
                }
                .selected-box .width-handle { display: block; }
                .ml { left: -10px; }
                .mr { right: -10px; }
            </style>
        </head>
        <body id="canvas">
            <div id="scale-wrapper">
                <div id="safe-area"></div>
            </div>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <script>
                var backend;
                new QWebChannel(qt.webChannelTransport, function (channel) { backend = channel.objects.backend; });
                
                let PROJ_W = 1080;
                let PROJ_H = 1920;
                
                function setResolution(w, h) {
                    PROJ_W = w; PROJ_H = h;
                }

                // 👑 Ctrl + 滚轮缩放监听
                let currentZoom = 1.0;
                window.addEventListener('wheel', (e) => {
                    if (e.ctrlKey) {
                        e.preventDefault();
                        if (e.deltaY < 0) currentZoom += 0.1;
                        else currentZoom -= 0.1;
                        currentZoom = Math.min(Math.max(0.2, currentZoom), 3.0);
                        document.getElementById('scale-wrapper').style.transform = `scale(${currentZoom})`;
                        document.getElementById('scale-wrapper').style.transformOrigin = 'center center';
                    }
                }, {passive: false});

                function syncSubs(subsJson) {
                    const subs = JSON.parse(subsJson);
                    const canvas = document.getElementById('scale-wrapper');
                    const currentIds = new Set(subs.map(s => s.idx));
                    Array.from(canvas.children).forEach(el => {
                        if(el.classList.contains('drag-container') && !currentIds.has(parseInt(el.dataset.idx))) el.remove();
                    });
                    
                    subs.forEach(sub => {
                        let el = document.getElementById('drag-' + sub.idx);
                        if(!el) {
                            el = document.createElement('div');
                            el.id = 'drag-' + sub.idx;
                            el.className = 'drag-container';
                            el.dataset.idx = sub.idx;
                            canvas.appendChild(el);
                            
                            let observer = new MutationObserver(() => {
                                let box = el.querySelector('.sub-box');
                                if(box && !box.hasAttribute('data-handles')) {
                                    box.setAttribute('data-handles', 'true');
                                    ['ml', 'mr'].forEach(pos => {
                                        let c = document.createElement('div'); c.className = `width-handle ${pos}`; box.appendChild(c);
                                    });
                                    makeDraggable(el);
                                    makeResizable(box, sub.idx);
                                }
                            });
                            observer.observe(el, { childList: true });
                        }
                        
                        if(sub.htmlText.trim() === "") {
                            el.style.display = 'none';
                        } else {
                            el.style.display = 'block'; 
                            if (el.innerHTML !== sub.htmlText) {
                                el.innerHTML = sub.htmlText;
                            }
                        }
                        
                        let box = el.querySelector('.sub-box');
                        if(box) {
                            if(sub.isSelected) { box.classList.add('selected-box'); } 
                            else { box.classList.remove('selected-box'); }
                        }
                        
                        if (sub.box_width > 0) {
                            el.style.width = sub.box_width + 'vw';
                        } else {
                            el.style.width = 'max-content';
                        }
                        
                        el.dataset.pos_x = sub.pos_x;
                        el.dataset.pos_y = sub.pos_y;
                        el.style.left = `calc(50% + ${sub.pos_x}%)`;
                        el.style.top = `calc(50% + ${sub.pos_y}%)`;
                        el.style.zIndex = sub.track === 0 ? "10" : "5";
                    });
                }
                
                function makeDraggable(el) {
                    let isDragging = false, startX, startY;
                    el.addEventListener('mousedown', e => {
                        let box = el.querySelector('.sub-box');
                        if ((box && box.isContentEditable) || e.target.classList.contains('width-handle')) return; 
                        isDragging = true; startX = e.clientX; startY = e.clientY;
                        el.dataset.ox = parseFloat(el.dataset.pos_x) || 0;
                        el.dataset.oy = parseFloat(el.dataset.pos_y) || 0;
                        if(backend) backend.notify_selected(parseInt(el.dataset.idx));
                    });
                    window.addEventListener('mousemove', e => {
                        if (!isDragging) return;
                        let wrapper = document.getElementById('scale-wrapper');
                        let rect = wrapper.getBoundingClientRect();
                        
                        // 修正缩放后的拖拽比例
                        let dx_pct = (e.clientX - startX) / (rect.width / currentZoom) * 100;
                        let dy_pct = (e.clientY - startY) / (rect.height / currentZoom) * 100;
                        
                        let cx = parseFloat(el.dataset.ox) + dx_pct;
                        let cy = parseFloat(el.dataset.oy) + dy_pct;
                        
                        el.style.left = `calc(50% + ${cx}%)`;
                        el.style.top = `calc(50% + ${cy}%)`;
                        el.dataset.vx = cx; el.dataset.vy = cy;
                    });
                    window.addEventListener('mouseup', e => {
                        if (isDragging) {
                            isDragging = false;
                            if(backend && el.dataset.vx) backend.update_coordinates(parseInt(el.dataset.idx), parseFloat(el.dataset.vx), parseFloat(el.dataset.vy));
                        }
                    });
                    el.addEventListener('dblclick', () => {
                        let box = el.querySelector('.sub-box');
                        if(box) { 
                            box.classList.add('editing'); 
                            box.contentEditable = true; 
                            box.focus(); 
                        }
                    });
                    el.addEventListener('blur', (e) => {
                        let box = el.querySelector('.sub-box');
                        if(box) { 
                            box.classList.remove('editing'); 
                            box.contentEditable = false; 
                            if(backend) backend.update_text_from_screen(parseInt(el.dataset.idx), box.innerText); 
                        }
                    }, true);
                    el.addEventListener('wheel', (e) => {
                        let box = el.querySelector('.sub-box');
                        if (box && box.isContentEditable) return;
                        // 不再拦截非 Ctrl 的滚轮（修复冲突）
                        if(!e.ctrlKey) {
                            e.preventDefault();
                            if(backend) backend.adjust_font_size(parseInt(el.dataset.idx), e.deltaY < 0 ? 2 : -2);
                        }
                    });
                }

                function makeResizable(box, idx) {
                    const handles = box.querySelectorAll('.width-handle');
                    let isResizingWidth = false;
                    let dragContainer = box.closest('.drag-container');

                    handles.forEach(c => {
                        c.addEventListener('mousedown', e => {
                            e.stopPropagation(); 
                            isResizingWidth = true;
                        });
                    });

                    window.addEventListener('mousemove', e => {
                        if (isResizingWidth) {
                            let wrapper = document.getElementById('scale-wrapper');
                            let rect = wrapper.getBoundingClientRect();
                            let boxRect = dragContainer.getBoundingClientRect();
                            let boxCx = boxRect.left + boxRect.width/2;
                            
                            // 修正缩放比例
                            let newHalfWidth = Math.abs(e.clientX - boxCx) / currentZoom;
                            let newWidthPx = Math.max(newHalfWidth * 2, 100); 
                            let newWidthVw = (newWidthPx / (rect.width / currentZoom)) * 100;
                            dragContainer.style.width = newWidthVw + 'vw';
                            dragContainer.dataset.newWidth = newWidthVw;
                        }
                    });
                    
                    window.addEventListener('mouseup', () => { 
                        if (isResizingWidth) {
                            isResizingWidth = false;
                            if (backend && dragContainer.dataset.newWidth) {
                                backend.update_box_width(idx, parseFloat(dragContainer.dataset.newWidth));
                                dragContainer.dataset.newWidth = ""; 
                            }
                        }
                    });
                }
            </script>
        </body>
        </html>
        """
        self.browser.setHtml(html_content)
    # 👑 新增：实时将文案同步到内存，按 Ctrl+S 时就会一起写入工程文件
    def _on_custom_text_changed(self):
        self.state["custom_text"] = self.text_editor.toPlainText()
        self.auto_save_cache()

    # 👑 新增：手动触发 NLP 清洗文案并展示出来
    def format_custom_text_manually(self):
        raw_text = self.text_editor.toPlainText().strip()
        if not raw_text:
            return QMessageBox.information(self, "提示", "剪贴板是空的，无需清洗哦！")
        
        cleaned_text = self._clean_and_format_user_text(raw_text)
        
        self.text_editor.blockSignals(True)
        self.text_editor.setPlainText(cleaned_text)
        self.text_editor.blockSignals(False)
        
        self.state["custom_text"] = cleaned_text
        self.auto_save_cache()
        self.status_lbl.setText("🧹 文案清洗完毕！空格与大小写已修正。")    

    def load_style_presets(self):
        if os.path.exists(PRESETS_FILE):
            try:
                with open(PRESETS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
            except: pass
        return {}

    def save_style_presets(self, data):
        try:
            with open(PRESETS_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

    # 👑 视觉预设下拉框核心引擎：调用 QPainter 纯手工绘制所见即所得
    def refresh_preset_combo(self):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        
        # 放大下拉框的图标尺寸，以容纳视觉预览图
        self.preset_combo.setIconSize(QSize(220, 40))
        self.preset_combo.setStyleSheet("""
            QComboBox { background-color: #11111b; border: 1px solid #313244; border-radius: 6px; padding: 5px; }
            QComboBox::drop-down { border: none; width: 30px; }
            QComboBox QAbstractItemView { background-color: #1e1e2e; selection-background-color: #313244; outline: none; border-radius: 6px; border: 1px solid #313244; }
            QComboBox QAbstractItemView::item { min-height: 50px; padding: 4px; }
        """)
        
        presets = self.load_style_presets()
        if presets:
            for name, st in presets.items():
                # 👑 开启 2D 硬件加速画笔，直接在内存中绘制图标
                pixmap = QPixmap(220, 40)
                pixmap.fill(Qt.GlobalColor.transparent) # 透明底色
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

                # 1. 提取并绘制背景 (支持胶带和全局底框)
                bg_mode = st.get("bg_mode", "none")
                if bg_mode != "none":
                    try:
                        bg_col = st.get("bg_color", "#000000").lstrip('#')
                        r, g, b = tuple(int(bg_col[i:i+2], 16) for i in (0, 2, 4))
                        alpha = int(st.get("bg_alpha", 80) * 2.55) # 转换 0-100 为 0-255
                        radius = 6 # 预览图固定小圆角
                        
                        painter.setBrush(QColor(r, g, b, alpha))
                        painter.setPen(Qt.PenStyle.NoPen)
                        # 在中间画一个完美的底框
                        painter.drawRoundedRect(QRectF(10, 4, 200, 32), radius, radius)
                    except: pass

                # 2. 提取字体并设置字号
                family = st.get("font", "Segoe UI")
                # 限制字号在 12-16 之间，防止撑爆预览框
                size = max(11, min(15, int(st.get("size", 100) * 0.10)))
                font = QFont(family, size)
                font.setBold(True)
                painter.setFont(font)

                # 3. 提取文字颜色
                txt_col = st.get("color_txt", "#FFFFFF").lstrip('#')
                try:
                    tr, tg, tb = tuple(int(txt_col[i:i+2], 16) for i in (0, 2, 4))
                    color_obj = QColor(tr, tg, tb)
                except:
                    color_obj = QColor(Qt.GlobalColor.white)

                # 4. 绘制硬阴影或描边 (稍微偏移画一层深色，增加立体感)
                if st.get("shadow_alpha", 100) > 0 or st.get("stroke_width", 0) > 0:
                    painter.setPen(QColor(0, 0, 0, 180)) # 黑色半透明阴影
                    painter.drawText(QRectF(11, 5, 200, 32), Qt.AlignmentFlag.AlignCenter, name)

                # 5. 绘制主文字
                painter.setPen(color_obj)
                painter.drawText(QRectF(10, 4, 200, 32), Qt.AlignmentFlag.AlignCenter, name)
                
                painter.end() # 结束绘制
                
                # 将绘制好的绝美画卷，作为图标塞进下拉框！
                self.preset_combo.addItem(QIcon(pixmap), "", userData=name)
        else:
            self.preset_combo.addItem("暂无自定义预设", userData="none")
            
        self.preset_combo.blockSignals(False)

    # 👑 2. 适配视觉预设的读取逻辑
    def save_style_preset(self):
        if self.current_selected_idx == -1: return QMessageBox.warning(self, "提示", "请先在时间线上选中一个调好的字幕片段！")
        name, ok = QInputDialog.getText(self, "💾 存为预设", "给这个酷炫的样式起个名字吧\n(例如: 爆款红底白字):")
        if ok and name.strip():
            clip = self.state["subs_data"][self.current_selected_idx]
            style_data = clip.get("style", self.default_style).copy()
            presets = self.load_style_presets()
            presets[name.strip()] = style_data
            self.save_style_presets(presets)
            self.refresh_preset_combo()
            
            # 👑 修复：根据隐藏的 userData 找到刚保存的预设并选中它
            idx = self.preset_combo.findData(name.strip(), Qt.ItemDataRole.UserRole)
            if idx >= 0: self.preset_combo.setCurrentIndex(idx)
            
            self._update_preset_preview()
            QMessageBox.information(self, "成功", f"预设 '{name.strip()}' 已保存入库！")

    def delete_style_preset(self):
        # 👑 修复：读取隐藏的 userData
        name = self.preset_combo.currentData(Qt.ItemDataRole.UserRole)
        if not name or name == "none": return
        presets = self.load_style_presets()
        if name in presets:
            reply = QMessageBox.question(self, '删除预设', f'确定要删除预设 "{name}" 吗？', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                del presets[name]
                self.save_style_presets(presets)
                self.refresh_preset_combo()
                self._update_preset_preview()

    def apply_style_preset(self):
        if self.current_selected_idx == -1: return QMessageBox.warning(self, "提示", "请先在时间线上选中要应用的字幕！")
        # 👑 修复：读取隐藏的 userData
        name = self.preset_combo.currentData(Qt.ItemDataRole.UserRole)
        if not name or name == "none": return
        presets = self.load_style_presets()
        
        if name in presets:
            preset_style = presets[name]
            targets = self._get_target_clips()
            for c in targets:
                if "style" not in c: c["style"] = {}
                c["style"].update(preset_style)
            
            self.default_style.update(preset_style)
            self.sync_inspector_to_clip()
            self._update_preset_preview()
            self.update_floating_subtitle()
            self.auto_save_cache()
            self.push_history()
            self.status_lbl.setText(f"✅ 预设 '{name}' 已完美应用！")

    def _update_preset_preview(self, *args):
        if not hasattr(self, "preset_preview_label"): return
        preview_text = self.font_preview_input.text().strip() if hasattr(self, "font_preview_input") else "Text"
        preview_text = preview_text or "Text"
        
        # 👑 修复：读取隐藏的 userData 获取真实名字
        name = self.preset_combo.currentData(Qt.ItemDataRole.UserRole)
        presets = self.load_style_presets() if hasattr(self, "load_style_presets") else {}
        st = presets.get(name) if name else None
        
        if st is None and self.current_selected_idx != -1 and self.current_selected_idx < len(self.state.get("subs_data", [])):
            st = self.state["subs_data"][self.current_selected_idx].get("style", self.default_style)
        st = st or self.default_style
        
        family = st.get("font", "Segoe UI")
        size = max(18, min(54, int(st.get("size", 100) * 0.35)))
        color = st.get("color_txt", "#FFFFFF")
        bg = st.get("bg_color", "#000000")
        
        self.preset_preview_label.setText(preview_text)
        self.preset_preview_label.setStyleSheet(f"background-color:{bg}; border:1px dashed #45475a; border-radius:10px; color:{color}; padding:10px; font-family:'{family}'; font-size:{size}px; font-weight:bold;")


    def toggle_safe_area(self):
        show = 'block' if self.chk_safe_area.isChecked() else 'none'
        self.browser.page().runJavaScript(f"document.getElementById('safe-area').style.display = '{show}';")

    def select_entire_track(self, track_type, track_idx):
        if track_type == "sub":
            for i, s in enumerate(self.state["subs_data"]):
                if s.get("track") == track_idx:
                    self.current_selected_idx = i; self.style_scope_combo.setCurrentIndex(1); self.switch_inspector("sub"); return
            QMessageBox.information(self, "提示", f"该轨道目前没有字幕片段。")

    def manual_save(self):
        self.save_to_project(silent=True)
        self.generate_cover_async()
        self.status_lbl.setText("✅ 工程已安全保存，并更新封面！")
        QMessageBox.information(self, "保存成功", "所有轨道排版数据已保存，封面图已在后台更新。")

    def save_to_project(self, silent=False):
        self.auto_save_cache()
        parent = self.parent()
        project_data = getattr(parent, "project", None) or self.project_data or {"project_type": "edit_room"}
        project_data = update_room_state(project_data, "edit_room", self.state)
        self.project_data = project_data
        if parent and hasattr(parent, "project"):
            parent.project = project_data
        return project_data

    def generate_cover_async(self):
        def task():
            try:
                v_clips = self.state.get("video_clips", [])
                if not v_clips: return
                v_path = v_clips[0]["path"]
                if not os.path.exists(v_path): return
                
                p_dir = self.project_data.get("project_dir", "")
                p_name = self.project_data.get("project_name", "untitled")
                if not p_dir: return
                
                cover_filename = f"{p_name}_cover.jpg"
                cover_path = os.path.join(p_dir, cover_filename)
                
                cmd = [get_ffmpeg_cmd(), "-y", "-ss", "00:00:01", "-i", v_path, "-vframes", "1", "-q:v", "2", cover_path]
                flags = 0x08000000 if os.name == 'nt' else 0
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
                
                self.project_data["cover_img"] = cover_filename
                from project_io import save_project
                save_project(self.project_data["project_path"], self.project_data)
            except Exception as e:
                pass
                
        threading.Thread(target=task, daemon=True).start()

    def reset_project(self):
        reply = QMessageBox.warning(self, '⚠️ 清空确认', '确定要清空所有轨道数据吗？', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.player.stop(); self.audio_player.stop()
            self.state["video_clips"] = []; self.state["audio_path"] = ""; self.state["subs_data"] = []; self.state["duration"] = 10.0
            self.current_selected_idx = -1; self.current_v_idx = 0; self.current_play_time = 0.0
            self.v_wave_pixmap = None; self.a_wave_pixmap = None; self.video_thumbs = [] 
            self.active_subs_cache.clear(); self.last_render_hash = None
            self.browser.page().runJavaScript("if(typeof syncSubs === 'function') syncSubs('[]');")
            self.btn_v.setText("➕ 导入第一段画面 (MP4)"); self.btn_a.setText("🎵 导入独立配音 (可选)")
            self.text_editor.clear(); self.render_ui_list(); self.switch_inspector("empty")
            self.update_timeline_size(); self.update_floating_subtitle()
            if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
            self.push_history()
            self.status_lbl.setText("✅ 工程已清空")

    def delete_current_clip(self):
        if self.current_selected_idx != -1:
            del self.state["subs_data"][self.current_selected_idx]; self.current_selected_idx = -1; self.switch_inspector("empty"); self.render_ui_list()
            self.update_timeline_size(); self.update_floating_subtitle(); self.auto_save_cache()
            self.push_history()
            self.status_lbl.setText("🗑️ 字幕已删除")

    def add_manual_text(self):
        t = self.current_play_time
        new_sub = {"start": t, "end": t + 3.0, "text": "新建文本", "track": 0, "words": [{"text": "新建文本", "start": t, "end": t + 3.0}]}
        new_sub = self.sanitize_subs_data([new_sub])[0] 
        self.state["subs_data"].append(new_sub); self.state["subs_data"] = sorted(self.state["subs_data"], key=lambda x: x['start']); self.state["duration"] = max(self.state["duration"], t + 3.0)
        self.current_selected_idx = self.state["subs_data"].index(new_sub); self.switch_inspector("sub"); self.render_ui_list(); self.update_timeline_size(); self.sync_player_to_time(t); self.auto_save_cache()
        self.push_history()

    def update_timeline_size(self):
        self.timeline_widget.sync_from_controller()

    def switch_inspector(self, track_type):
        self.selected_track = track_type
        if track_type == "video": self.insp_stack.setCurrentIndex(2); self.sync_inspector_to_video() 
        elif track_type == "audio": self.insp_stack.setCurrentIndex(3)
        elif track_type == "sub" and self.current_selected_idx != -1: self.insp_stack.setCurrentIndex(1); self.sync_inspector_to_clip()
        else: self.insp_stack.setCurrentIndex(0); self.current_selected_idx = -1
        self.tabs.setCurrentIndex(1); self.timeline_widget.sync_from_controller()

    def sync_inspector_to_video(self):
        if not self.state.get("video_clips") or self.current_v_idx < 0 or self.current_v_idx >= len(self.state["video_clips"]): return
        clip = self.state["video_clips"][self.current_v_idx]
        self.v_start_spin.blockSignals(True); self.v_end_spin.blockSignals(True)
        self.v_start_spin.setValue(float(clip.get("start", 0))); self.v_end_spin.setValue(float(clip.get("end", 5)))
        self.v_start_spin.blockSignals(False); self.v_end_spin.blockSignals(False)

    def _on_v_time_change(self):
        if not self.state.get("video_clips") or self.current_v_idx < 0 or self.current_v_idx >= len(self.state["video_clips"]): return
        self.state["video_clips"][self.current_v_idx]["start"] = self.v_start_spin.value()
        self.state["video_clips"][self.current_v_idx]["end"] = self.v_end_spin.value()
        self.update_timeline_size(); self.auto_save_cache()

    def sync_time_from_list(self, idx, new_start, new_end):
        clip = self.state["subs_data"][idx]
        old_start = float(clip.get("start", 0))
        old_end = float(clip.get("end", 1))
        old_dur = max(0.001, old_end - old_start)

        n_start = new_start if new_start is not None else old_start
        n_end = new_end if new_end is not None else old_end

        if n_end <= n_start: return 

        new_dur = max(0.001, n_end - n_start)

        words = clip.get("words", [])
        for w in words:
            rel_s = (float(w.get("start", 0)) - old_start) / old_dur
            rel_e = (float(w.get("end", 1)) - old_start) / old_dur
            w["start"] = n_start + rel_s * new_dur
            w["end"] = n_start + rel_e * new_dur

        clip["start"] = n_start
        clip["end"] = n_end

        self.update_timeline_size()
        self.auto_save_cache()
        if new_start is not None: self.sync_player_to_time(n_start)
        
        if getattr(self, 'current_selected_idx', -1) == idx and getattr(self, 'selected_track', '') == 'sub':
            self.sub_start_spin.blockSignals(True)
            self.sub_end_spin.blockSignals(True)
            self.sub_start_spin.setValue(n_start)
            self.sub_end_spin.setValue(n_end)
            self.sub_start_spin.blockSignals(False)
            self.sub_end_spin.blockSignals(False)

    def _on_sub_time_change(self):
        if self.current_selected_idx == -1 or not self.state["subs_data"]: return
        idx = self.current_selected_idx
        clip = self.state["subs_data"][idx]
        
        old_start = float(clip.get("start", 0))
        old_end = float(clip.get("end", 1))
        old_dur = max(0.001, old_end - old_start)
        
        new_start = self.sub_start_spin.value()
        new_end = self.sub_end_spin.value()
        if new_end <= new_start: return 
        new_dur = max(0.001, new_end - new_start)
        
        words = clip.get("words", [])
        for w in words:
            rel_s = (float(w.get("start", 0)) - old_start) / old_dur
            rel_e = (float(w.get("end", 1)) - old_start) / old_dur
            w["start"] = new_start + rel_s * new_dur
            w["end"] = new_start + rel_e * new_dur
            
        clip["start"] = new_start
        clip["end"] = new_end
        
        if hasattr(self, 'ui_entries') and 0 <= idx < len(self.ui_entries):
            if "start_spin" in self.ui_entries[idx]:
                self.ui_entries[idx]["start_spin"].blockSignals(True)
                self.ui_entries[idx]["start_spin"].setValue(new_start)
                self.ui_entries[idx]["start_spin"].blockSignals(False)
            if "end_spin" in self.ui_entries[idx]:
                self.ui_entries[idx]["end_spin"].blockSignals(True)
                self.ui_entries[idx]["end_spin"].setValue(new_end)
                self.ui_entries[idx]["end_spin"].blockSignals(False)
                
        self.update_timeline_size()
        self.auto_save_cache()

    def sync_text_edit(self, idx, text): 
        self.state["subs_data"][idx]["text"] = text
        clean_text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\u2029', '\n')
        words_split = []
        for i, line in enumerate(clean_text.split('\n')):
            parts = line.split()
            if not parts: 
                if i > 0 and words_split: words_split[-1] += '\n'
                continue
            if i > 0: parts[0] = '\n' + parts[0]
            words_split.extend(parts)

        num_words = len(words_split)
        if num_words > 0:
            st = float(self.state["subs_data"][idx]["start"]); en = float(self.state["subs_data"][idx]["end"]); step = (en - st) / num_words
            self.state["subs_data"][idx]["words"] = [{"text": w, "start": st + i * step, "end": st + (i + 1) * step} for i, w in enumerate(words_split)]
        if float(self.state["subs_data"][idx]["start"]) <= self.current_play_time <= float(self.state["subs_data"][idx]["end"]): self.update_floating_subtitle()
        self.auto_save_cache()

    def _switch_sub_page(self, idx):
        if not hasattr(self, "sub_pages"):
            return
        self.sub_pages.setCurrentIndex(idx)
        for i, btn in enumerate(getattr(self, "sub_page_buttons", [])):
            btn.blockSignals(True)
            btn.setChecked(i == idx)
            btn.blockSignals(False)

    def _set_font_filter(self, text):
        if not hasattr(self, "font_var"):
            return
        if "中文" in text:
            self.font_var.setWritingSystem(QFontComboBox.WritingSystem.SimplifiedChinese)
            self.font_var.setFontFilters(QFontComboBox.FontFilter.AllFonts)
        elif "拉丁" in text:
            self.font_var.setWritingSystem(QFontComboBox.WritingSystem.Latin)
            self.font_var.setFontFilters(QFontComboBox.FontFilter.AllFonts)
        elif "等宽" in text:
            self.font_var.setWritingSystem(QFontComboBox.WritingSystem.Any)
            self.font_var.setFontFilters(QFontComboBox.FontFilter.MonospacedFonts)
        else:
            self.font_var.setWritingSystem(QFontComboBox.WritingSystem.Any)
            self.font_var.setFontFilters(QFontComboBox.FontFilter.AllFonts)

    def _update_preset_preview(self, *args):
        if not hasattr(self, "preset_preview_label"):
            return
        preview_text = self.font_preview_input.text().strip() if hasattr(self, "font_preview_input") else "Text"
        preview_text = preview_text or "Text"
        presets = self.load_style_presets() if hasattr(self, "load_style_presets") else {}
        st = presets.get(self.preset_combo.currentText()) if hasattr(self, "preset_combo") else None
        if st is None and self.current_selected_idx != -1 and self.current_selected_idx < len(self.state.get("subs_data", [])):
            st = self.state["subs_data"][self.current_selected_idx].get("style", self.default_style)
        st = st or self.default_style
        family = st.get("font", "Segoe UI")
        size = max(18, min(54, int(st.get("size", 100) * 0.35)))
        color = st.get("color_txt", "#FFFFFF")
        bg = st.get("bg_color", "#000000")
        self.preset_preview_label.setText(preview_text)
        self.preset_preview_label.setStyleSheet(f"background-color:{bg}; border:1px dashed #45475a; border-radius:10px; color:{color}; padding:10px; font-family:'{family}'; font-size:{size}px; font-weight:bold;")

    def _update_font_preview(self, *args):
        if not hasattr(self, "font_preview_label"):
            return
        preview_text = "Text"
        if hasattr(self, "font_preview_input"):
            preview_text = self.font_preview_input.text().strip() or "Text"
        font_family = self.font_var.currentFont().family() if hasattr(self, "font_var") else "Segoe UI"
        font_size = self.size_spin.value() if hasattr(self, "size_spin") else 72
        line_height_pct = self.lineh_spin.value() if hasattr(self, "lineh_spin") else 110
        letter_spacing = self.spacing_spin.value() if hasattr(self, "spacing_spin") else 0
        word_spacing = self.word_spacing_spin.value() if hasattr(self, "word_spacing_spin") else 0
        self.font_preview_label.setText(preview_text)
        self.font_preview_label.setStyleSheet(
            f"background-color: #11111b; border: 1px dashed #45475a; border-radius: 8px; color: #ffffff;"
            f"padding: 12px; font-family: '{font_family}'; font-size: {max(16, min(font_size, 72))}px;"
            f"letter-spacing: {letter_spacing}px; word-spacing: {word_spacing}px; line-height: {max(90, min(line_height_pct, 180))}%;"
        )

    def sync_inspector_to_clip(self):
        if self.current_selected_idx == -1 or not self.state["subs_data"]: return
        clip = self.state["subs_data"][self.current_selected_idx]
        st = clip.get("style", clip) 
        
        controls = [self.sub_start_spin, self.sub_end_spin, self.pos_x_spin, self.pos_x_slider, self.pos_y_spin, self.pos_y_slider, self.size_slider, self.size_spin, self.box_width_slider, self.box_width_spin, self.alpha_slider, self.alpha_spin, self.radius_slider, self.radius_spin, self.padding_slider, self.padding_spin, self.bg_pad_left_slider, self.bg_pad_left_spin, self.bg_pad_right_slider, self.bg_pad_right_spin, self.bg_pad_top_slider, self.bg_pad_top_spin, self.bg_pad_bottom_slider, self.bg_pad_bottom_spin, self.hl_alpha_slider, self.hl_alpha_spin, self.hl_radius_slider, self.hl_radius_spin, self.hl_padding_slider, self.hl_padding_spin, self.hl_pad_left_slider, self.hl_pad_left_spin, self.hl_pad_right_slider, self.hl_pad_right_spin, self.hl_pad_top_slider, self.hl_pad_top_spin, self.hl_pad_bottom_slider, self.hl_pad_bottom_spin, self.spacing_slider, self.spacing_spin, self.lineh_slider, self.lineh_spin, self.stroke_slider, self.stroke_spin, self.stroke_o_slider, self.stroke_o_spin, self.rot_slider, self.rot_spin, self.glow_size_slider, self.glow_size_spin, self.sh_x_slider, self.sh_x_spin, self.sh_y_slider, self.sh_y_spin, self.sh_blur_slider, self.sh_blur_spin, self.sh_a_slider, self.sh_a_spin, self.pop_speed_slider, self.pop_speed_spin, self.pop_bounce_slider, self.pop_bounce_spin, self.inactive_alpha_slider, self.inactive_alpha_spin, self.mask_top_slider, self.mask_top_spin, self.mask_bot_slider, self.mask_bot_spin, self.merge_bridge_width_slider, self.merge_bridge_width_spin, self.merge_bridge_height_slider, self.merge_bridge_height_spin, self.merge_bridge_alpha_slider, self.merge_bridge_alpha_spin, self.transform_combo, self.align_combo, self.anim_combo, self.bg_mode_combo, self.layout_mode_combo, self.layout_variant_combo, self.emphasis_slider, self.emphasis_spin]
        for c in controls: c.blockSignals(True)
        
        self.sub_start_spin.setValue(float(clip.get("start", 0)))
        self.sub_end_spin.setValue(float(clip.get("end", 1)))
        
        vx = float(clip.get("pos_x", 0.0))
        vy = float(clip.get("pos_y", 25.0))
        self.pos_x_spin.setValue(vx); self.pos_x_slider.setValue(int(vx * 100))
        self.pos_y_spin.setValue(vy); self.pos_y_slider.setValue(int(vy * 100))
        
        self.size_spin.setValue(int(st.get("size", 100))); self.size_slider.setValue(int(st.get("size", 100)))
        self.box_width_spin.setValue(float(st.get("box_width", 0))); self.box_width_slider.setValue(int(st.get("box_width", 0) * 100))
        self.spacing_spin.setValue(int(st.get("letter_spacing", 0))); self.spacing_slider.setValue(int(st.get("letter_spacing", 0)))
        self.lineh_spin.setValue(int(st.get("line_height", 1.1)*100)); self.lineh_slider.setValue(int(st.get("line_height", 1.1)*100))
        self.word_spacing_spin.setValue(int(st.get("word_spacing", 0))); self.word_spacing_slider.setValue(int(st.get("word_spacing", 0)))
        self.emphasis_spin.setValue(int(st.get("emphasis_scale", 145))); self.emphasis_slider.setValue(int(st.get("emphasis_scale", 145)))
        self.stroke_spin.setValue(int(st.get("stroke_width", 4))); self.stroke_slider.setValue(int(st.get("stroke_width", 4)))
        self.stroke_o_spin.setValue(int(st.get("stroke_o_width", 0))); self.stroke_o_slider.setValue(int(st.get("stroke_o_width", 0)))
        self.rot_spin.setValue(int(st.get("rotation", 0))); self.rot_slider.setValue(int(st.get("rotation", 0)))
        self.glow_size_spin.setValue(int(st.get("glow_size", 20))); self.glow_size_slider.setValue(int(st.get("glow_size", 20)))
        
        self.sh_x_spin.setValue(int(st.get("shadow_x", 5))); self.sh_x_slider.setValue(int(st.get("shadow_x", 5)))
        self.sh_y_spin.setValue(int(st.get("shadow_y", 5))); self.sh_y_slider.setValue(int(st.get("shadow_y", 5)))
        self.sh_blur_spin.setValue(int(st.get("shadow_blur", 0))); self.sh_blur_slider.setValue(int(st.get("shadow_blur", 0)))
        self.sh_a_spin.setValue(int(st.get("shadow_alpha", 100))); self.sh_a_slider.setValue(int(st.get("shadow_alpha", 100)))
        
        self.pop_speed_spin.setValue(float(st.get("pop_speed", 0.2))); self.pop_speed_slider.setValue(int(st.get("pop_speed", 0.2)*100))
        self.pop_bounce_spin.setValue(int(st.get("pop_bounce", 140))); self.pop_bounce_slider.setValue(int(st.get("pop_bounce", 140)))
        self.inactive_alpha_spin.setValue(int(st.get("inactive_alpha", 100))); self.inactive_alpha_slider.setValue(int(st.get("inactive_alpha", 100)))
        
        self.alpha_spin.setValue(int(st.get("bg_alpha", 80))); self.alpha_slider.setValue(int(st.get("bg_alpha", 80)))
        self.radius_spin.setValue(int(st.get("bg_radius", 15))); self.radius_slider.setValue(int(st.get("bg_radius", 15)))
        self.padding_spin.setValue(int(st.get("bg_padding", 20))); self.padding_slider.setValue(int(st.get("bg_padding", 20)))
        self.bg_pad_left_spin.setValue(int(st.get("bg_pad_left", st.get("bg_padding", 20)))); self.bg_pad_left_slider.setValue(int(st.get("bg_pad_left", st.get("bg_padding", 20))))
        self.bg_pad_right_spin.setValue(int(st.get("bg_pad_right", st.get("bg_padding", 20)))); self.bg_pad_right_slider.setValue(int(st.get("bg_pad_right", st.get("bg_padding", 20))))
        self.bg_pad_top_spin.setValue(int(st.get("bg_pad_top", st.get("bg_padding", 20) / 2.5))); self.bg_pad_top_slider.setValue(int(st.get("bg_pad_top", st.get("bg_padding", 20) / 2.5)))
        self.bg_pad_bottom_spin.setValue(int(st.get("bg_pad_bottom", st.get("bg_padding", 20) / 2.5))); self.bg_pad_bottom_slider.setValue(int(st.get("bg_pad_bottom", st.get("bg_padding", 20) / 2.5)))
        
        self.hl_alpha_spin.setValue(int(st.get("hl_bg_alpha", 100))); self.hl_alpha_slider.setValue(int(st.get("hl_bg_alpha", 100)))
        self.hl_radius_spin.setValue(int(st.get("hl_bg_radius", 8))); self.hl_radius_slider.setValue(int(st.get("hl_bg_radius", 8)))
        self.hl_padding_spin.setValue(int(st.get("hl_bg_padding", 8))); self.hl_padding_slider.setValue(int(st.get("hl_bg_padding", 8)))
        self.hl_pad_left_spin.setValue(int(st.get("hl_pad_left", st.get("hl_bg_padding", 8)))); self.hl_pad_left_slider.setValue(int(st.get("hl_pad_left", st.get("hl_bg_padding", 8))))
        self.hl_pad_right_spin.setValue(int(st.get("hl_pad_right", st.get("hl_bg_padding", 8)))); self.hl_pad_right_slider.setValue(int(st.get("hl_pad_right", st.get("hl_bg_padding", 8))))
        self.hl_pad_top_spin.setValue(int(st.get("hl_pad_top", max(0, st.get("hl_bg_padding", 8) / 3)))); self.hl_pad_top_slider.setValue(int(st.get("hl_pad_top", max(0, st.get("hl_bg_padding", 8) / 3))))
        self.hl_pad_bottom_spin.setValue(int(st.get("hl_pad_bottom", max(0, st.get("hl_bg_padding", 8) / 3)))); self.hl_pad_bottom_slider.setValue(int(st.get("hl_pad_bottom", max(0, st.get("hl_bg_padding", 8) / 3))))
        
        self.mask_top_spin.setValue(int(st.get("mask_top", 20))); self.mask_top_slider.setValue(int(st.get("mask_top", 20)))
        self.mask_bot_spin.setValue(int(st.get("mask_bottom", 20))); self.mask_bot_slider.setValue(int(st.get("mask_bottom", 20)))
        self.merge_bridge_width_spin.setValue(int(st.get("merge_bridge_width", 160))); self.merge_bridge_width_slider.setValue(int(st.get("merge_bridge_width", 160)))
        self.merge_bridge_height_spin.setValue(int(st.get("merge_bridge_height", 16))); self.merge_bridge_height_slider.setValue(int(st.get("merge_bridge_height", 16)))
        self.merge_bridge_alpha_spin.setValue(int(st.get("merge_bridge_alpha", 100))); self.merge_bridge_alpha_slider.setValue(int(st.get("merge_bridge_alpha", 100)))

        self.chk_use_hl.blockSignals(True); self.chk_hl_glow.blockSignals(True); self.chk_mask_en.blockSignals(True); self.chk_merge_bridge.blockSignals(True)
        self.chk_use_hl.setChecked(st.get("use_hl", True)); self.chk_hl_glow.setChecked(st.get("hl_glow", False)); self.chk_mask_en.setChecked(st.get("mask_en", False)); self.chk_merge_bridge.setChecked(st.get("merge_bridge_enable", False))
        self.chk_use_hl.blockSignals(False); self.chk_hl_glow.blockSignals(False); self.chk_mask_en.blockSignals(False); self.chk_merge_bridge.blockSignals(False)
        
        t_map = {"uppercase": "全部大写 (UPPERCASE)", "lowercase": "全部小写 (lowercase)", "capitalize": "首字母大写 (Capitalize)", "none": "正常 (Normal)"}
        self.transform_combo.setCurrentText(t_map.get(st.get("text_transform", "capitalize")))
        a_map = {"center": "居中对齐 (Center)", "left": "左对齐 (Left)", "right": "右对齐 (Right)", "justify": "两端对齐 (Justify)"}
        self.align_combo.setCurrentText(a_map.get(st.get("text_align", "center")))
        lm_map = {"standard": "标准排版", "contrast": "大小对比排版", "triple": "三层模板排版"}
        self.layout_mode_combo.setCurrentText(lm_map.get(st.get("layout_mode", "standard"), "标准排版"))
        lv_map = {"auto": "自动变化", "small-big-small": "小-大-小", "big-small-mix": "大-小-混排", "mix-big-small": "混排-大-小"}
        self.layout_variant_combo.setCurrentText(lv_map.get(st.get("layout_variant", "auto"), "自动变化"))
        anim_map = {"pop": "🎉 逐字弹跳 (Pop-in)", "fade": "☁️ 柔和淡入 (Fade)", "roll_up": "⬆️ 电影级向上滚动 (Roll Up)", "none": "🚫 无动画 (None)"}
        self.anim_combo.setCurrentText(anim_map.get(st.get("anim_type", "pop")))
        
        try:
            self.font_var.setCurrentFont(st.get("font", self.default_style.get("font", "Segoe UI")))
        except Exception:
            pass

        bm = st.get("bg_mode", "none")
        if bm == "none":
            b_idx = 0
        elif bm == "tape":
            b_idx = 1
        elif bm == "sweep":
            b_idx = 2
        elif bm == "full_frame":
            b_idx = 4
        else:
            b_idx = 3
        self.bg_mode_combo.setCurrentIndex(b_idx)

        for c in controls: c.blockSignals(False)
        self._update_font_preview()
        
        self.btn_color_txt.setStyleSheet(f"background-color: {st.get('color_txt', '#FFFFFF')}; color: black; padding: 5px;")
        self.btn_color_stroke.setStyleSheet(f"background-color: {st.get('stroke_color', '#000000')}; color: white; padding: 5px;")
        self.btn_color_stroke_o.setStyleSheet(f"background-color: {st.get('stroke_o_color', '#000000')}; color: white; padding: 5px;")
        self.btn_color_sh.setStyleSheet(f"background-color: {st.get('shadow_color', '#000000')}; color: white; padding: 5px;")
        self.btn_color_bg.setStyleSheet(f"background-color: {st.get('bg_color', '#000000')}; color: white; padding: 5px;")
        self.btn_color_hl_bg.setStyleSheet(f"background-color: {st.get('hl_bg_color', '#FF0050')}; color: white; padding: 5px;")
        
        if st.get("use_hl", True): self.btn_color_hl.setEnabled(True); self.btn_color_hl.setStyleSheet(f"background-color: {st.get('color_hl', '#FFFFFF')}; color: black; padding: 5px;")
        else: self.btn_color_hl.setEnabled(False); self.btn_color_hl.setStyleSheet("background-color: #313244; color: gray; padding: 5px;")

    def _apply_styles_to_targets(self, target_type, hex_col=None):
        if self.current_selected_idx == -1: return
        current_clip = self.state["subs_data"][self.current_selected_idx]
        scope = self.style_scope_combo.currentIndex()
        if scope == 0: target_clips = self.state["subs_data"]
        elif scope == 1: target_clips = [c for c in self.state["subs_data"] if c.get("track") == current_clip.get("track")]
        else: target_clips = [current_clip]

        for c in target_clips:
            if "style" not in c: c["style"] = {}
            if target_type == "txt_col": c["style"]["color_txt"] = hex_col
            elif target_type == "stroke_col": c["style"]["stroke_color"] = hex_col
            elif target_type == "stroke_o_col": c["style"]["stroke_o_color"] = hex_col
            elif target_type == "hl_col": c["style"]["color_hl"] = hex_col
            elif target_type == "sh_col": c["style"]["shadow_color"] = hex_col
            elif target_type == "bg_col": c["style"]["bg_color"] = hex_col
            elif target_type == "hl_bg_col": c["style"]["hl_bg_color"] = hex_col
            elif target_type == "params":
                c["pos_x"] = float(self.pos_x_spin.value()); c["pos_y"] = float(self.pos_y_spin.value())
                c["style"]["rotation"] = self.rot_slider.value(); c["style"]["font"] = self.font_var.currentFont().family()
                c["style"]["size"] = self.size_slider.value(); c["style"]["letter_spacing"] = self.spacing_slider.value(); c["style"]["word_spacing"] = self.word_spacing_slider.value()
                c["style"]["box_width"] = self.box_width_spin.value()
                c["style"]["line_height"] = self.lineh_slider.value() / 100.0
                c["style"]["stroke_width"] = self.stroke_slider.value(); c["style"]["stroke_o_width"] = self.stroke_o_slider.value()
                c["style"]["use_hl"] = self.chk_use_hl.isChecked(); c["style"]["hl_glow"] = self.chk_hl_glow.isChecked(); c["style"]["glow_size"] = self.glow_size_slider.value()
                
                c["style"]["shadow_x"] = self.sh_x_slider.value(); c["style"]["shadow_y"] = self.sh_y_slider.value()
                c["style"]["shadow_blur"] = self.sh_blur_slider.value(); c["style"]["shadow_alpha"] = self.sh_a_slider.value()
                c["style"]["pop_speed"] = self.pop_speed_spin.value(); 
                c["style"]["pop_bounce"] = self.pop_bounce_slider.value()
                c["style"]["inactive_alpha"] = self.inactive_alpha_slider.value()
                
                c["style"]["bg_alpha"] = self.alpha_slider.value()
                c["style"]["bg_radius"] = self.radius_slider.value()
                c["style"]["bg_padding"] = self.padding_slider.value()
                c["style"]["bg_pad_left"] = self.bg_pad_left_slider.value()
                c["style"]["bg_pad_right"] = self.bg_pad_right_slider.value()
                c["style"]["bg_pad_top"] = self.bg_pad_top_slider.value()
                c["style"]["bg_pad_bottom"] = self.bg_pad_bottom_slider.value()
                
                c["style"]["hl_bg_alpha"] = self.hl_alpha_slider.value()
                c["style"]["hl_bg_radius"] = self.hl_radius_slider.value()
                c["style"]["hl_bg_padding"] = self.hl_padding_slider.value()
                c["style"]["hl_pad_left"] = self.hl_pad_left_slider.value()
                c["style"]["hl_pad_right"] = self.hl_pad_right_slider.value()
                c["style"]["hl_pad_top"] = self.hl_pad_top_slider.value()
                c["style"]["hl_pad_bottom"] = self.hl_pad_bottom_slider.value()
                
                c["style"]["mask_en"] = self.chk_mask_en.isChecked()
                c["style"]["mask_top"] = self.mask_top_slider.value()
                c["style"]["mask_bottom"] = self.mask_bot_slider.value()
                c["style"]["merge_bridge_enable"] = self.chk_merge_bridge.isChecked()
                c["style"]["merge_bridge_width"] = self.merge_bridge_width_slider.value()
                c["style"]["merge_bridge_height"] = self.merge_bridge_height_slider.value()
                c["style"]["merge_bridge_alpha"] = self.merge_bridge_alpha_slider.value()
                mode_txt = self.layout_mode_combo.currentText()
                c["style"]["layout_mode"] = "contrast" if "大小对比" in mode_txt else "triple" if "三层模板" in mode_txt else "standard"
                variant_txt = self.layout_variant_combo.currentText()
                c["style"]["layout_variant"] = "small-big-small" if "小-大-小" in variant_txt else "big-small-mix" if "大-小-混排" in variant_txt else "mix-big-small" if "混排-大-小" in variant_txt else "auto"
                c["style"]["emphasis_scale"] = self.emphasis_slider.value()
                
                tc = self.transform_combo.currentText()
                c["style"]["text_transform"] = "uppercase" if "UPPERCASE" in tc else "lowercase" if "lowercase" in tc else "capitalize" if "Capitalize" in tc else "none"
                ac = self.align_combo.currentText()
                c["style"]["text_align"] = "left" if "Left" in ac else "right" if "Right" in ac else "justify" if "Justify" in ac else "center"
                anc = self.anim_combo.currentText()
                c["style"]["anim_type"] = "pop" if "Pop" in anc else "fade" if "Fade" in anc else "roll_up" if "Roll Up" in anc else "none"
                
                b_txt = self.bg_mode_combo.currentText()
                if "无底框" in b_txt:
                    c["style"]["bg_mode"] = "none"
                elif "单点" in b_txt:
                    c["style"]["bg_mode"] = "tape"
                elif "渐变" in b_txt:
                    c["style"]["bg_mode"] = "sweep"
                elif "全部框架" in b_txt:
                    c["style"]["bg_mode"] = "full_frame"
                else:
                    c["style"]["bg_mode"] = "block"

        for k in self.default_style.keys():
            if "style" in current_clip and k in current_clip["style"]: 
                self.default_style[k] = current_clip["style"][k]

        self.btn_color_hl.setEnabled(self.chk_use_hl.isChecked()); self.sync_inspector_to_clip(); self.update_floating_subtitle(); self.auto_save_cache()

    def _pick_color(self, target):
        color = QColorDialog.getColor()
        if color.isValid(): 
            self._apply_styles_to_targets(f"{target}_col", color.name())
            self.push_history()

    def _on_style_change(self, *args): 
        self._apply_styles_to_targets("params"); 
        self._update_font_preview()
        
    def _on_vid_prop_change(self): self.state["v_scale"] = self.v_scale_slider.value(); self.state["v_volume"] = self.v_vol_slider.value(); self.audio_output.setVolume(self.state["v_volume"] / 100.0); self.sync_player_to_time(self.current_play_time); self.auto_save_cache()
    def _on_aud_prop_change(self): self.state["a_volume"] = self.a_vol_slider.value(); self.audio_track_output.setVolume(self.state["a_volume"] / 100.0); self.auto_save_cache()

    def generate_waveform(self, path, attr_name):
        if not path or not os.path.exists(path): return
        def _task():
            try:
                out = os.path.join(tempfile.gettempdir(), f"sh_wave_{attr_name}.png")
                cmd = [get_ffmpeg_cmd(), "-y", "-i", path, "-map", "0:a:0?", "-filter_complex", "showwavespic=s=2000x60:colors=#a6e3a1", "-frames:v", "1", out]
                flags = 0x08000000 if os.name == 'nt' else 0
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, timeout=10)
                if os.path.exists(out): QTimer.singleShot(0, lambda: self._apply_waveform(out, attr_name))
            except: pass
        threading.Thread(target=_task, daemon=True).start()

    def _apply_waveform(self, img_path, attr_name): 
        setattr(self, attr_name, QPixmap(img_path)); self.timeline_widget.sync_from_controller()

    def load_audio(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择音频", "", "Audio Files (*.mp3 *.wav)")
        if file_path:
            self.state["audio_path"] = file_path; self.btn_a.setText("✅ " + os.path.basename(file_path)[:15]); self.audio_player.setSource(QUrl.fromLocalFile(file_path))
            a_dur = get_exact_duration(file_path)
            if a_dur > 0: self.state["a_trim"] = [0.0, a_dur]
            self._recalc_duration(); self.generate_waveform(file_path, "a_wave_pixmap"); self.update_timeline_size(); self.auto_save_cache()
            
    def load_video(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择视频", "", "Video Files (*.mp4 *.mov *.webm)")
        if file_path:
            dur = get_exact_duration(file_path)
            if dur <= 0: dur = 5.0
            clips = self.state.get("video_clips", [])
            start_t = clips[-1]["end"] if clips else 0.0
            clips.append({"path": file_path, "start": start_t, "end": start_t + dur, "dur": dur})
            self.state["video_clips"] = clips; self.btn_v.setText("✅ 已导原素材")
            if len(clips) == 1: 
                self.player.setSource(QUrl.fromLocalFile(file_path))
                self.player.setLoops(QMediaPlayer.Loops.Infinite) 
                self.on_resolution_changed(self.res_combo.currentText())
                self.generate_waveform(file_path, "v_wave_pixmap")
                threading.Thread(target=self._gen_thumbs_cache, daemon=True).start()
            self._recalc_duration(); self.auto_save_cache()

    def auto_fill_video(self):
        clips = self.state.get("video_clips", [])
        if not clips: return QMessageBox.warning(self, "提示", "请先导入一段视频作为底料！")
        a_path = self.state.get("audio_path", "")
        if not a_path: return QMessageBox.warning(self, "提示", "请先导入配音才能进行一键对齐！")
        a_dur = get_exact_duration(a_path)
        if a_dur <= 0: return
        compound_clip = clips[0]; compound_clip["start"] = 0.0; compound_clip["end"] = a_dur
        self.state["video_clips"] = [compound_clip]; self._recalc_duration(); self.auto_save_cache(); self.timeline_widget.sync_from_controller()
        QMessageBox.information(self, "铺满成功", f"🚀 已将视频转换为复合片段！\n内部自动循环并紧密匹配音频时长 ({a_dur:.1f}s)。")
            
    def remove_last_video_clip(self):
        clips = self.state.get("video_clips", [])
        if clips:
            clips.pop(); self.state["video_clips"] = clips
            if not clips: self.btn_v.setText("➕ 导入第一段画面 (MP4)"); self.player.stop(); self.v_wave_pixmap = None
            self._recalc_duration(); self.auto_save_cache()
            
    def remove_audio(self):
        if self.state.get("audio_path"):
            self.state["audio_path"] = ""
            self.btn_a.setText("🎵 导入独立配音 (可选)")
            self.audio_player.stop()
            self.a_wave_pixmap = None
            self._recalc_duration()
            self.update_timeline_size()
            self.auto_save_cache()
            self.status_lbl.setText("🗑️ 配音已清除")
            
    def _recalc_duration(self):
        clips = self.state.get("video_clips", [])
        dur1 = max([c["end"] for c in clips]) if clips else 0.0
        dur2 = get_exact_duration(self.state.get("audio_path")) if self.state.get("audio_path") else 0
        self.state["duration"] = max(dur1, dur2); self.update_timeline_size()

    @Slot(QVideoFrame)
    def on_video_frame(self, frame):
        if frame.isValid() and not frame.toImage().isNull():
            img = frame.toImage(); w, h = self.video_label.width(), self.video_label.height()
            if w > 0 and h > 0:
                scaled_pix = QPixmap.fromImage(img).scaled(int(w * self.state["v_scale"] / 100.0), int(h * self.state["v_scale"] / 100.0), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                result_pix = QPixmap(w, h); result_pix.fill(Qt.GlobalColor.black); painter = QPainter(result_pix); painter.drawPixmap((w - scaled_pix.width()) // 2, (h - scaled_pix.height()) // 2, scaled_pix); painter.end(); self.video_label.setPixmap(result_pix)
    
    def toggle_play(self):
        self.is_playing = not self.is_playing; self.btn_play.setText("⏸️ 暂停" if self.is_playing else "▶️ 播放")
        if self.is_playing: 
            self.player.play(); self.audio_player.play() if self.state.get("audio_path") else None
            self.play_timer = QTimer(self); self.play_timer.timeout.connect(self.play_tick); self.play_timer.start(30)
        else: 
            self.player.pause(); self.audio_player.pause() if self.state.get("audio_path") else None
            if hasattr(self, 'play_timer'): self.play_timer.stop()
            
    def play_tick(self):
        if self.timeline_widget.is_scrubbing: return 
        real_time = self.audio_player.position() / 1000.0 if self.state.get("audio_path") else self.player.position() / 1000.0
        self.current_play_time = real_time; self.lbl_time.setText(f"{self.current_play_time:.1f}s / {self.state['duration']:.1f}s")
        self.timeline_widget.update_playhead(real_time); self.update_floating_subtitle()
        
    def sync_player_to_time(self, time_sec): 
        self.current_play_time = time_sec
        clips = self.state.get("video_clips", [])
        if clips and clips[0].get("dur", 0) > 0:
            local_time = time_sec % max(0.1, clips[0]["dur"]); self.player.setPosition(int(local_time * 1000))
        else: self.player.setPosition(int(time_sec * 1000))
        if self.state.get("audio_path"): self.audio_player.setPosition(int(time_sec * 1000))
        self.lbl_time.setText(f"{self.current_play_time:.1f}s / {self.state['duration']:.1f}s")
        self.timeline_widget.update_playhead(time_sec); self.update_floating_subtitle()

    def update_floating_subtitle(self):
        active_subs = []
        for i, s in enumerate(self.state["subs_data"]):
            if float(s.get('start', 0)) <= self.current_play_time <= float(s.get('end', 1)):
                htmlText = render_subtitle_html(s, self.current_play_time, self.proj_width)
                active_subs.append({
                    "idx": i, "htmlText": htmlText, "isNew": (i not in self.active_subs_cache), 
                    "pos_x": s.get("pos_x", 0.0), "pos_y": s.get("pos_y", 25.0), 
                    "box_width": s.get("style", {}).get("box_width", 0), 
                    "track": s.get("track", 1), "isSelected": (i == self.current_selected_idx)
                })
        current_hash = hash(json.dumps(active_subs, sort_keys=True))
        if current_hash != getattr(self, 'last_render_hash', None): 
            json_str = json.dumps(active_subs)
            safe_json = json_str.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
            self.browser.page().runJavaScript(f"if(typeof syncSubs === 'function') syncSubs(`{safe_json}`);")
            self.last_render_hash = current_hash; self.active_subs_cache = set([sub["idx"] for sub in active_subs])

    def sanitize_subs_data(self, data):
        def_x = self.state.get("default_pos_x", 0.0)
        def_y = self.state.get("default_pos_y", 25.0)
        def_style = self.state.get("default_style", self.default_style)

        for s in data: 
            s["track"] = s.get("track", 1)
            if "pos_x" not in s: s["pos_x"] = def_x
            else: s["pos_x"] = float(s["pos_x"])
            if "pos_y" not in s: s["pos_y"] = def_y
            else: s["pos_y"] = float(s["pos_y"])

            if "style" not in s: s["style"] = {}

            for k, v in def_style.items():
                if k in s and k not in ["track", "pos_x", "pos_y", "words", "text", "start", "end", "style"]:
                    s["style"][k] = s.pop(k)
                elif k not in s["style"]:
                    s["style"][k] = v
            s.setdefault("words", [{"text": s.get('text', ''), "start": s.get('start', 0.0), "end": s.get('end', 1.0)}])
        return data
        
    @Slot(str)
    def _on_ai_progress(self, msg): self.status_lbl.setText(msg)

    @Slot()
    def _on_ai_success(self):
        self.update_timeline_size(); self.render_ui_list(); self.status_lbl.setText("✅ 打轴完毕！"); self.auto_save_cache()
        self.push_history()
        QMessageBox.information(self, "🎉 成功", "AI 听译打轴完美完成！\n已自动为您生成所有字幕片段！")

    @Slot(str)
    def _on_ai_error(self, msg):
        self.status_lbl.setText("❌ 打轴失败"); QMessageBox.critical(self, "AI 听译失败", f"提取失败！原因如下：\n\n{msg}")

    @Slot()
    def _on_ai_finish(self): 
        self.btn_extract.setEnabled(True)

    # 👑 NLP 文本清洗引擎强化版：彻底解决标点符号与空格粘连
    # 👑 NLP 文本清洗引擎强化版：彻底解决标点符号与空格粘连
    def _clean_and_format_user_text(self, raw_text):
        text = raw_text
        # 1. 拆开被粘连的驼峰词 (ThankYou -> Thank You)
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        
        # 2. 去掉标点前面的多余空格
        text = re.sub(r'\s+([.,!?;:])', r'\1', text)
        
        # 3. 👑 核心修复：在标点后面强制加空格（完美兼容带着双引号的标点，如 come."Some -> come." Some）
        text = re.sub(r'([.,!?;:]["”\']?)([A-Za-z0-9])', r'\1 \2', text)
        
        # 4. 清理连续的多余空格
        text = re.sub(r'[ \t]+', ' ', text)
        
        # 5. 智能首字母大写规则
        sentences = re.split(r'([.!?]["”\']?\s+)', text)
        cleaned_sentences = []
        for s in sentences:
            if len(s) > 0 and s[0].islower():
                cleaned_sentences.append(s[0].upper() + s[1:])
            else:
                cleaned_sentences.append(s)
        return "".join(cleaned_sentences).strip()

    def _tokenize_user_text_for_alignment(self, raw_text):
        raw_text = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
        tokens = []
        for line_idx, line in enumerate(raw_text.split("\n")):
            line = line.strip()
            if not line: continue
            parts = line.split()
            if not parts: continue
            if tokens and line_idx > 0:
                parts[0] = "\n" + parts[0].lstrip()
            tokens.extend(parts)
        return tokens

    # 👑 智能对齐引擎：将 AI 时间戳与手工文案强行绑定
    def _align_user_text_to_ai_words(self, ai_words, raw_text):
        user_tokens = self._tokenize_user_text_for_alignment(raw_text)
        if not ai_words or not user_tokens: return ai_words

        aligned = []
        total_ai = len(ai_words)
        total_user = len(user_tokens)

        if total_user == 1:
            start = ai_words[0].get("start", 0.0)
            end = ai_words[-1].get("end", start + 1.0)
            return [{"word": user_tokens[0], "start": start, "end": end}]

        for i, token in enumerate(user_tokens):
            start_idx = min(total_ai - 1, int(i * total_ai / total_user))
            end_idx = min(total_ai - 1, max(start_idx, int(((i + 1) * total_ai) / total_user) - 1))
            start = ai_words[start_idx].get("start", 0.0)
            end = ai_words[end_idx].get("end", start)
            if end <= start: end = start + 0.01
            aligned.append({"word": token, "start": start, "end": end})
        return aligned

    def start_extract(self):
        try:
            cmd = get_ffmpeg_cmd()
            try:
                flags = 0x08000000 if os.name == 'nt' else 0
                subprocess.run([cmd, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            except Exception:
                QMessageBox.warning(self, "引擎缺失", "尚未检测到核心引擎 (FFmpeg)！\n可能是下载被拦截或未完成。\n\n系统将再次尝试呼叫云端部署。您也可以手动将 ffmpeg.exe 放入软件目录。")
                self.check_and_download_ffmpeg()
                return

            v_clips = self.state.get("video_clips", [])
            a_path = self.state.get("audio_path", "")
            target_path = a_path if a_path else (v_clips[0]["path"] if v_clips else "")
            if not target_path: return QMessageBox.warning(self, "提示", "请先导入画面或者配音！")
            
            c_mode = self.chunk_mode.currentText()
            # 读取用户输入的手工文案
            custom_text = self.text_editor.toPlainText().strip()
            
            self.btn_extract.setEnabled(False)
            self.status_lbl.setText("⏳ 准备听译环境...")
            threading.Thread(target=self.extract_task, args=(target_path, c_mode, custom_text), daemon=True).start()
        except Exception as e: QMessageBox.critical(self, "错误", f"启动提取失败: {str(e)}")

    def extract_task(self, target_path, c_mode, custom_text):
        temp_audio = None
        try:
            accounts = local_get_cf_accounts()
            if not accounts: raise Exception("未配置 API 密钥，请在底部导航栏【全局设置】中填写！")
            
            # 👑 终极修复：不再自作聪明判断大小，强制把所有素材压制成“极限微缩版 mp3”！
            self.sig_ai_progress.emit("⏳ 正在提取云端专用微缩音频...")
            temp_audio = os.path.join(tempfile.gettempdir(), "sh_ai_temp.mp3")
            
            # 强制 16kHz 采样率、单声道、极低码率 (16k)。保证 1 小时音频也才几 MB，永不触发 413 报错！
            cmd = [get_ffmpeg_cmd(), "-y", "-i", target_path, "-vn", "-map", "a:0?", "-ar", "16000", "-ac", "1", "-b:a", "16k", temp_audio]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000 if os.name == 'nt' else 0)
            
            if os.path.exists(temp_audio) and os.path.getsize(temp_audio) > 100: 
                target_path = temp_audio
            else: 
                raise Exception("音频抽取失败！可能素材无声音或格式不支持。")

            # 读取极限压缩后的文件，此时 30秒的音频绝对只有不到 100KB！
            with open(target_path, 'rb') as f: data = f.read()
            
            res_json = None; last_err = ""
            self.sig_ai_progress.emit("⏳ 上传并呼叫云端大模型...")
            # ...下面的代码保持原样不要动...
            for acc in accounts:
                if acc.get("id") and acc.get("token"):
                    try:
                        res = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{acc['id']}/ai/run/@cf/openai/whisper", headers={"Authorization": f"Bearer {acc['token']}", "Content-Type": "application/octet-stream"}, data=data, timeout=60, verify=False) 
                        if res.status_code == 200 and res.json().get("success"): res_json = res.json(); break 
                        else: last_err = f"HTTP {res.status_code}: {res.text[:100]}"
                    except Exception as net_e: last_err = str(net_e)
            if not res_json: raise Exception(f"所有账号请求失败！\n云端报错:\n{last_err}")
            
            clean_words = [{"word": re.sub(r'(?i)stereo_[^\s]+', '', w["word"]).replace(".mp3", "").replace(".wav", "").strip(), "start": w["start"], "end": w["end"]} for w in res_json["result"]["words"] if re.sub(r'(?i)stereo_[^\s]+', '', w["word"]).strip()]
            
            # 👑 如果用户输入了手工文案，触发清洗和强行对齐
            if custom_text:
                self.sig_ai_progress.emit("⏳ 正在用 NLP 算法清洗并对齐您的手工文案...")
                cleaned_text = self._clean_and_format_user_text(custom_text)
                clean_words = self._align_user_text_to_ai_words(clean_words, cleaned_text)
            
            self.state["subs_data"] = self.sanitize_subs_data(self.process_words(clean_words, c_mode))
            
            if self.state["subs_data"]: self.state["duration"] = max(self.state["duration"], self.state["subs_data"][-1]["end"])
            self.sig_ai_success.emit()
            
        except Exception as e: self.sig_ai_error.emit(str(e))
        finally:
            if temp_audio and os.path.exists(temp_audio):
                try: os.remove(temp_audio)
                except: pass
            self.sig_ai_finish.emit()

    # 👑 商业级字幕断句引擎：引入【语义保护胶水】与【静音停顿检测】
    def process_words(self, words, mode):
        subs = []
        curr = {"words": []}
        # ⚠️ 关键修改：去掉了冒号 ':'，防止 31:25 被错误切断！
        puncts = ['.', '!', '?', ',', '，', '。', '！', '？', ';']
        
        for i, w in enumerate(words):
            if not curr["words"]: 
                curr["start"] = w["start"]
            
            curr["words"].append({"text": w["word"], "start": w["start"], "end": w["end"]})
            curr["end"] = w["end"]
            
            has_punct = any(w["word"].endswith(p) for p in puncts)
            w_len = len(curr["words"])
            curr_dur = curr["end"] - curr["start"]
            
            next_word = words[i+1]["word"] if i + 1 < len(words) else ""
            next_start = words[i+1]["start"] if i + 1 < len(words) else 9999.0
            
            # 🔇 停顿检测：如果说话停顿超过 0.8 秒，强制断开
            silence_gap = next_start - curr["end"]
            force_break = silence_gap > 0.8
            
            is_break = False
            
            if "单字" in mode:
                is_break = True
            elif "双行" in mode:
                if force_break: is_break = True
                elif has_punct and curr_dur > 1.2: is_break = True
                elif w_len >= 12: is_break = True
                elif w_len >= 8 and curr_dur > 2.5: is_break = True
            else: # 短句模式
                if force_break: is_break = True
                elif has_punct and curr_dur > 0.8: is_break = True
                elif w_len >= 6: is_break = True
                elif w_len >= 3 and curr_dur > 1.5: is_break = True

            # 👑 【核心新增】：语义强力保护胶水 (Semantic Glue)
            if next_word:
                # 规则 1：如果下一个词是纯数字或冒号开头 (如 "25", ":25", "31")，绝不断开！
                if re.match(r'^[:\d]', next_word):
                    is_break = False
                
                # 规则 2：如果当前词是经文书卷名，后面通常跟数字，绝不断开！
                curr_clean = re.sub(r'[^a-zA-Z]', '', w["word"]).lower()
                bible_books = {"proverbs", "psalm", "psalms", "matthew", "mark", "luke", "john", "genesis", "exodus", "romans", "corinthians", "chapter", "verse"}
                if curr_clean in bible_books:
                    is_break = False
                
                # 规则 3：如果当前词本身以冒号结尾 (例如 "31:")，绝不断开！
                if w["word"].endswith(":"):
                    is_break = False
                    
            if is_break:
                if "双行" in mode and w_len >= 6:
                    mid = w_len // 2
                    curr["words"][mid]["text"] = "\n" + curr["words"][mid]["text"].lstrip()
                    
                raw_text = " ".join([x["text"] for x in curr["words"]])
                curr["text"] = raw_text.replace(" \n", "\n").replace("\n ", "\n")
                
                subs.append(curr)
                curr = {"words": [], "track": 1}
                
        if curr["words"]:
            raw_text = " ".join([x["text"] for x in curr["words"]])
            curr["text"] = raw_text.replace(" \n", "\n").replace("\n ", "\n")
            subs.append(curr)
            
        return subs

    def render_ui_list(self):
        for i in reversed(range(self.scroll_layout.count())): 
            item = self.scroll_layout.itemAt(i); item.widget().deleteLater() if item.widget() else None
        self.ui_entries.clear()
        
        self.scroll_layout.setSpacing(10)
        self.scroll_layout.setContentsMargins(5, 5, 5, 5)
        
        for i, s in enumerate(self.state["subs_data"]): 
            start_t = float(s['start'])
            end_t = float(s['end'])
            
            card = QFrame()
            card.setStyleSheet("QFrame { background-color: #1e1e2e; border: 1px solid #313244; border-radius: 6px; }")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)
            card_layout.setSpacing(6)
            
            top_row = QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            
            btn = QPushButton(f"▶ {start_t:.1f}s")
            btn.setFixedWidth(65)
            btn.setStyleSheet("QPushButton { background-color: #313244; color: #a6e3a1; font-weight: bold; border-radius: 3px; padding: 4px; border: none; } QPushButton:hover { background-color: #45475a; }")
            btn.clicked.connect(lambda _, idx=i: self.sync_player_to_time(float(self.state["subs_data"][idx]["start"])))
            
            lbl_start = QLabel("起:")
            lbl_start.setStyleSheet("color: #a6adc8; border: none; background: transparent;")
            start_spin = ProScrubDoubleSpinBox()
            start_spin.setRange(0, 36000); start_spin.setSingleStep(0.1); start_spin.setDecimals(1); start_spin.setLocale(self.eng_locale)
            start_spin.setValue(start_t)
            start_spin.setStyleSheet("QDoubleSpinBox { background: #11111b; color: #a6e3a1; font-weight: bold; border: 1px solid #313244; border-radius: 3px; padding: 2px 4px; }")
            start_spin.setFixedWidth(65)
            
            lbl_end = QLabel("终:")
            lbl_end.setStyleSheet("color: #a6adc8; border: none; background: transparent;")
            end_spin = ProScrubDoubleSpinBox()
            end_spin.setRange(0, 36000); end_spin.setSingleStep(0.1); end_spin.setDecimals(1); end_spin.setLocale(self.eng_locale)
            end_spin.setValue(end_t)
            end_spin.setStyleSheet("QDoubleSpinBox { background: #11111b; color: #f38ba8; font-weight: bold; border: 1px solid #313244; border-radius: 3px; padding: 2px 4px; }")
            end_spin.setFixedWidth(65)
            
            top_row.addWidget(btn)
            top_row.addSpacing(10)
            top_row.addWidget(lbl_start)
            top_row.addWidget(start_spin)
            top_row.addSpacing(5)
            top_row.addWidget(lbl_end)
            top_row.addWidget(end_spin)
            top_row.addStretch()
            
            entry = QTextEdit(s["text"])
            entry.setFixedHeight(48) 
            entry.setStyleSheet("QTextEdit { background-color: #11111b; color: #cdd6f4; border: 1px solid #313244; border-radius: 4px; font-size: 13px; padding: 4px; }")
            
            start_spin.valueChanged.connect(lambda val, idx=i: self.sync_time_from_list(idx, val, None))
            end_spin.valueChanged.connect(lambda val, idx=i: self.sync_time_from_list(idx, None, val))
            entry.textChanged.connect(lambda idx=i, w=entry: self.sync_text_edit(idx, w.toPlainText()))            
            card_layout.addLayout(top_row)
            card_layout.addWidget(entry)
            
            self.scroll_layout.addWidget(card)
            self.ui_entries.append({"ui": entry, "start_spin": start_spin, "end_spin": end_spin, "btn": btn})
            
    def auto_save_cache(self):
        try: 
            if getattr(self, 'current_selected_idx', -1) != -1 and self.state.get("subs_data"):
                try:
                    curr_clip = self.state["subs_data"][self.current_selected_idx]
                    self.state["default_pos_x"] = curr_clip.get("pos_x", 0.0)
                    self.state["default_pos_y"] = curr_clip.get("pos_y", 25.0)
                    self.state["default_style"] = curr_clip.get("style", self.default_style).copy()
                except IndexError:
                    pass
            json.dump(self.state, open(CACHE_FILE, 'w', encoding='utf-8'), ensure_ascii=False)
        except Exception as e: 
            pass
    
    def load_project_on_boot(self):
        room_state = {}
        if isinstance(self.project_data, dict):
            room_state = self.project_data.get("room_state", {}).get("edit_room", {})
        if room_state:
            try:
                room_state = dict(room_state)
                room_state["subs_data"] = self.sanitize_subs_data(room_state.get("subs_data", []))
                self.state.update(room_state)
                self.v_scale_spin.setValue(self.state.get("v_scale", 100))
                self.v_vol_spin.setValue(self.state.get("v_volume", 100))
                self.a_vol_spin.setValue(self.state.get("a_volume", 100))
                self.chunk_mode.blockSignals(True)
                self.chunk_mode.setCurrentText(self.state.get("chunk_mode", "双行大段 (约10字，智能折行)"))
                self.chunk_mode.blockSignals(False)
                self.text_editor.blockSignals(True)
                self.text_editor.setPlainText(self.state.get("custom_text", ""))
                self.text_editor.blockSignals(False)
                clips = self.state.get("video_clips", [])
                if clips:
                    self.btn_v.setText("✅ 已导原素材")
                    self.player.setSource(QUrl.fromLocalFile(clips[0]["path"]))
                    self.player.setLoops(QMediaPlayer.Loops.Infinite)
                    self.on_resolution_changed(self.state.get("resolution", "原画检测 (自动跟随)"))
                    self.generate_waveform(clips[0]["path"], "v_wave_pixmap")
                    threading.Thread(target=self._gen_thumbs_cache, daemon=True).start()
                if self.state.get("audio_path") and os.path.exists(self.state.get("audio_path")):
                    self.btn_a.setText("✅ " + os.path.basename(self.state.get("audio_path"))[:15])
                    self.audio_player.setSource(QUrl.fromLocalFile(self.state.get("audio_path")))
                    self.generate_waveform(self.state.get("audio_path"), "a_wave_pixmap")
                self.render_ui_list()
                self.switch_inspector("empty")
                self.push_history() # 初始化历史栈
                QTimer.singleShot(500, self._sync_duration_after_cache)
                return
            except Exception:
                pass
        self.load_cache_on_boot()

    def load_cache_on_boot(self):
        if not os.path.exists(CACHE_FILE): return
        try:
            cached = json.load(open(CACHE_FILE, 'r', encoding='utf-8')); cached["subs_data"] = self.sanitize_subs_data(cached.get("subs_data", [])); self.state.update(cached); self.v_scale_spin.setValue(self.state.get("v_scale", 100)); self.v_vol_spin.setValue(self.state.get("v_volume", 100)); self.a_vol_spin.setValue(self.state.get("a_volume", 100))
            self.chunk_mode.blockSignals(True)
            self.chunk_mode.setCurrentText(self.state.get("chunk_mode", "双行大段 (约10字，智能折行)"))
            self.chunk_mode.blockSignals(False)
            self.text_editor.blockSignals(True)
            self.text_editor.setPlainText(self.state.get("custom_text", ""))
            self.text_editor.blockSignals(False)
            clips = self.state.get("video_clips", [])
            if clips: 
                self.btn_v.setText("✅ 已导原素材"); self.player.setSource(QUrl.fromLocalFile(clips[0]["path"])); self.player.setLoops(QMediaPlayer.Loops.Infinite); self.on_resolution_changed(self.state.get("resolution", "原画检测 (自动跟随)")); self.generate_waveform(clips[0]["path"], "v_wave_pixmap"); threading.Thread(target=self._gen_thumbs_cache, daemon=True).start()
            if self.state.get("audio_path") and os.path.exists(self.state.get("audio_path")): 
                self.btn_a.setText("✅ " + os.path.basename(self.state.get("audio_path"))[:15]); self.audio_player.setSource(QUrl.fromLocalFile(self.state.get("audio_path"))); self.generate_waveform(self.state.get("audio_path"), "a_wave_pixmap")
            self.render_ui_list(); self.switch_inspector("empty"); 
            self.push_history() # 初始化历史栈
            QTimer.singleShot(500, self._sync_duration_after_cache)
        except: pass
    
    def on_resolution_changed(self, text): 
        clips = self.state.get("video_clips", [])
        self.proj_width, self.proj_height = get_video_dimensions(clips[0]["path"]) if "自动跟随" in text and clips else [1080, 1920] if "1080x1920" in text else [1920, 1080] if "1920x1080" in text else [1080, 1080]
        self.aspect_container.set_ratio(self.proj_width, self.proj_height); self.state["resolution"] = text
        self.browser.page().runJavaScript(f"if(typeof setResolution === 'function') setResolution({self.proj_width}, {self.proj_height});")
        self.auto_save_cache()
    
    def _gen_thumbs_cache(self):
        clips = self.state.get("video_clips", [])
        if not clips: return
        try:
            tdir = os.path.join(tempfile.gettempdir(), "sh_v8_thumbs")
            if not os.path.exists(tdir) or len(os.listdir(tdir)) == 0:
                if os.path.exists(tdir): shutil.rmtree(tdir)
                os.makedirs(tdir); subprocess.run([get_ffmpeg_cmd(), "-y", "-i", clips[0]["path"], "-vf", "fps=1", "-s", "80x45", os.path.join(tdir, "t_%04d.jpg")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000 if os.name == 'nt' else 0)
            files = sorted([os.path.join(tdir, f) for f in os.listdir(tdir) if f.endswith('.jpg')]); QTimer.singleShot(0, lambda: self._load_thumbs_ui(files))
        except: pass

    def _load_thumbs_ui(self, files): 
        self.video_thumbs = [QPixmap(f) for f in files]; self.timeline_widget.sync_from_controller()
    
    def _sync_duration_after_cache(self):
        self.audio_output.setVolume(self.state.get("v_volume", 100) / 100.0); self.audio_track_output.setVolume(self.state.get("a_volume", 100) / 100.0)
        self._recalc_duration(); self.sync_player_to_time(0.1) 
        
    def _get_target_clips(self):
        if self.current_selected_idx == -1: return []
        current_clip = self.state["subs_data"][self.current_selected_idx]
        scope = self.style_scope_combo.currentIndex()
        if scope == 0: return self.state["subs_data"]
        elif scope == 1: return [c for c in self.state["subs_data"] if c.get("track") == current_clip.get("track")]
        else: return [current_clip]