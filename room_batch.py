# ==========================================
# 文件名: room_batch.py (终极满血修复版 - 包含静音与完美表格解析)
# ==========================================
import os
import json
import tempfile
import threading
import subprocess
import requests
import re
import shutil
import csv
import io
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QFrame, QProgressBar, QTextEdit, QFileDialog, 
                             QMessageBox, QComboBox, QTabWidget, QScrollArea, QLineEdit, QDialog)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from playwright.sync_api import sync_playwright

from core import get_ffmpeg_cmd
# 确保导入了 get_exact_duration
from ui_components import get_exact_duration, get_video_dimensions, render_subtitle_html

PRESETS_FILE = os.path.join(os.getcwd(), "style_presets.json") 

def local_get_cf_accounts():
    config_path = os.path.join(os.getcwd(), "settings.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f).get("cf_accounts", [])
        except: pass
    return []

def get_browser_path():
    if os.name == 'nt': 
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        ]
    else: paths = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for p in paths:
        if os.path.exists(p): return p
    return None

class BatchTaskRow(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_path = ""
        self.audio_path = ""
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("QFrame { background-color: #1e1e2e; border: 1px solid #313244; border-radius: 6px; }")
        self.setFixedHeight(80)
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(10, 10, 10, 10)
        row_layout.setSpacing(10)

        self.btn_vid = QPushButton("➕ 选画面")
        self.btn_vid.setFixedSize(100, 40)
        self.btn_vid.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; border-radius: 4px; border: none;")
        self.btn_vid.clicked.connect(self.select_video)
        row_layout.addWidget(self.btn_vid)

        self.btn_aud = QPushButton("🎵 选配音")
        self.btn_aud.setFixedSize(100, 40)
        self.btn_aud.setStyleSheet("background-color: #cba6f7; color: #11111b; font-weight: bold; border-radius: 4px; border: none;")
        self.btn_aud.clicked.connect(self.select_audio)
        row_layout.addWidget(self.btn_aud)

        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("大标题 (仅房间2)")
        self.txt_title.setStyleSheet("background-color: #11111b; color: #cdd6f4; border: 1px solid #313244; padding: 5px;")
        self.txt_title.setFixedWidth(150)
        row_layout.addWidget(self.txt_title)

        self.txt_content = QTextEdit()
        self.txt_content.setPlaceholderText("详细正文文案 (支持多行/不填则调用 AI 盲听)")
        self.txt_content.setStyleSheet("background-color: #11111b; color: #a6adc8; border: 1px solid #313244; padding: 5px;")
        row_layout.addWidget(self.txt_content, stretch=1)

        self.lbl_status = QLabel("待处理")
        self.lbl_status.setFixedWidth(80)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #a6adc8; border: none;")
        row_layout.addWidget(self.lbl_status)

        self.btn_del = QPushButton("❌")
        self.btn_del.setFixedSize(40, 40)
        self.btn_del.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; border-radius: 4px; border: none;")
        self.btn_del.clicked.connect(self.deleteLater)
        row_layout.addWidget(self.btn_del)

    def select_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择画面", "", "Video Files (*.mp4 *.mov *.webm *.jpg *.png)")
        if path:
            self.video_path = path
            self.btn_vid.setText("✅ " + os.path.basename(path)[:5] + "...")
            self.btn_vid.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; border-radius: 4px;")

    def select_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择配音", "", "Audio Files (*.mp3 *.wav)")
        if path:
            self.audio_path = path
            self.btn_aud.setText("✅ " + os.path.basename(path)[:5] + "...")
            self.btn_aud.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; border-radius: 4px;")

class BatchView(QWidget):
    sig_log = Signal(str, str)
    sig_progress = Signal(int)
    sig_file_done = Signal()
    sig_all_done = Signal()
    sig_table_row_status = Signal(int, str, str) 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.input_dir = ""
        self.output_dir = ""
        self.task_queue = []
        self.current_idx = 0
        self.is_running = False
        
        self.sig_log.connect(self._append_log)
        self.sig_progress.connect(self._update_progress)
        self.sig_file_done.connect(self._on_file_done)
        self.sig_all_done.connect(self._on_all_done)
        self.sig_table_row_status.connect(self._update_table_row_status)
        
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        top_header = QHBoxLayout()
        top_header.addWidget(QLabel("📦 工业级批量生成引擎 (Matrix Pipeline)", styleSheet="font-size: 22px; font-weight: bold; color: #cdd6f4;"))
        top_header.addStretch()
        
        # 👑 音频静音控制区
        top_header.addWidget(QLabel("🎵 音频处理:", styleSheet="color: #cba6f7; font-weight: bold;"))
        self.audio_mode = QComboBox()
        self.audio_mode.addItems(["🔇 替换/静音 (仅配音)", "🔉 混合原声与配音", "🔊 保留原声 (无视配音)"])
        self.audio_mode.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 5px 10px; font-weight: bold; border-radius: 5px;")
        top_header.addWidget(self.audio_mode)
        
        top_header.addWidget(QLabel("🎨 强制应用字幕预设:", styleSheet="color: #a6e3a1; font-weight: bold; margin-left: 15px;"))
        self.preset_combo = QComboBox()
        self.preset_combo.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 5px 10px; font-weight: bold; border-radius: 5px;")
        self.preset_combo.setFixedWidth(200)
        top_header.addWidget(self.preset_combo)
        
        top_header.addWidget(QLabel("✂️ AI断句:", styleSheet="color: #89b4fa; font-weight: bold; margin-left: 15px;"))
        self.chunk_mode = QComboBox()
        self.chunk_mode.addItems(["单字轰炸 (1字/句)", "短句快闪 (3-5字)", "长句大段 (约10字)"])
        self.chunk_mode.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 5px 10px; font-weight: bold; border-radius: 5px;")
        top_header.addWidget(self.chunk_mode)
        
        self.btn_set_out_dir = QPushButton("💾 设置全局输出目录")
        self.btn_set_out_dir.setStyleSheet("background-color: #f9e2af; color: #11111b; font-weight: bold; padding: 5px 15px; border-radius: 5px; margin-left: 15px;")
        self.btn_set_out_dir.clicked.connect(self.select_output_dir)
        top_header.addWidget(self.btn_set_out_dir)

        main_layout.addLayout(top_header)
        
        self.lbl_output = QLabel("当前输出路径: 未选择 (将默认存放在原视频同目录)")
        self.lbl_output.setStyleSheet("color: #a6adc8; font-size: 12px;")
        main_layout.addWidget(self.lbl_output)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { background: #181825; color: #a6adc8; padding: 10px 20px; font-size: 15px; font-weight: bold; border-top-left-radius: 8px; border-top-right-radius: 8px; }
            QTabBar::tab:selected { background: #313244; color: #a6e3a1; }
            QTabWidget::pane { border: 2px solid #313244; border-radius: 8px; background: #181825; }
        """)
        
        self.tab_table = QWidget()
        self.init_table_tab()
        self.tabs.addTab(self.tab_table, "📑 多选排列 / 表格手工批量")

        self.tab_folder = QWidget()
        self.init_folder_tab()
        self.tabs.addTab(self.tab_folder, "📁 文件夹全自动匹配")

        main_layout.addWidget(self.tabs, stretch=1)

        bottom_layout = QHBoxLayout()
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFixedHeight(120)
        self.log_console.setStyleSheet("background-color: #11111b; color: #a6adc8; font-family: Consolas; font-size: 13px; border: 1px solid #313244; border-radius: 5px; padding: 10px;")
        bottom_layout.addWidget(self.log_console, stretch=1)
        main_layout.addLayout(bottom_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(25)
        self.progress_bar.setStyleSheet("QProgressBar { border: 2px solid #313244; border-radius: 5px; text-align: center; color: white; font-weight: bold; } QProgressBar::chunk { background-color: #a6e3a1; }")
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.refresh_presets()

    # 👑 核心魔法：复刻旧版完美的 Excel 解析逻辑
    def open_paste_dialog(self, auto_add=False):
        dialog = QDialog(self)
        dialog.setWindowTitle("📥 智能表格粘贴器")
        dialog.resize(650, 450)
        dialog.setStyleSheet("background-color: #181825;")
        layout = QVBoxLayout(dialog)
        
        lbl = QLabel("去 Excel / 飞书 / 腾讯文档 选中内容按 Ctrl+C，在这里 Ctrl+V：\n👉 完美兼容带回车换行的单元格\n👉 单列：只填正文\n👉 两列：左列大标题，右列详细正文")
        lbl.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 14px; line-height: 1.5;")
        layout.addWidget(lbl)
        
        tb = QTextEdit()
        tb.setStyleSheet("background-color: #11111b; color: #cdd6f4; font-size: 14px; border: 1px solid #313244; border-radius: 5px; padding: 10px;")
        layout.addWidget(tb)
        
        btn = QPushButton("✅ 解析并填入表格")
        btn.setFixedHeight(45)
        btn.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; font-size: 16px; border-radius: 5px;")
        
        def apply_paste():
            content = tb.toPlainText().strip()
            if not content: return
            try:
                # 完美解析包含回车符的复杂单元格
                lines = list(csv.reader(io.StringIO(content), delimiter='\t'))
            except:
                lines = [line.split('\t') for line in content.split('\n')]
                
            row_widgets = []
            for i in range(self.table_layout.count()):
                w = self.table_layout.itemAt(i).widget()
                if isinstance(w, BatchTaskRow): row_widgets.append(w)
                    
            if auto_add:
                while len(row_widgets) < len(lines):
                    self.add_table_row()
                    w = self.table_layout.itemAt(self.table_layout.count()-1).widget()
                    row_widgets.append(w)
                    
            for i, parts in enumerate(lines):
                if i >= len(row_widgets): break
                if not parts: continue
                row_obj = row_widgets[i]
                
                if len(parts) >= 2:
                    row_obj.txt_title.setText(parts[0].strip())
                    row_obj.txt_content.setPlainText(parts[1].strip())
                elif len(parts) == 1:
                    row_obj.txt_content.setPlainText(parts[0].strip())
                    
            dialog.accept()
            
        btn.clicked.connect(apply_paste)
        layout.addWidget(btn)
        dialog.exec()

    def init_table_tab(self):
        layout = QVBoxLayout(self.tab_table)
        
        toolbar = QHBoxLayout()
        btn_batch_vid = QPushButton("🎞️ 1. 批量选视频"); btn_batch_vid.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; padding: 8px; border-radius: 4px;")
        btn_batch_aud = QPushButton("🎵 2. 批量选音频"); btn_batch_aud.setStyleSheet("background-color: #cba6f7; color: #11111b; font-weight: bold; padding: 8px; border-radius: 4px;")
        btn_paste = QPushButton("📋 3. 从表格/Excel一键粘贴"); btn_paste.setStyleSheet("background-color: #b4befe; color: #11111b; font-weight: bold; padding: 8px; border-radius: 4px;")
        
        btn_paste.clicked.connect(lambda: self.open_paste_dialog(auto_add=True))
        
        btn_start_table = QPushButton("🚀 开始批量流水线")
        btn_start_table.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-size: 16px; font-weight: bold; padding: 8px 20px; border-radius: 4px;")
        btn_start_table.clicked.connect(self.start_table_batch)

        toolbar.addWidget(btn_batch_vid); toolbar.addWidget(btn_batch_aud); toolbar.addWidget(btn_paste)
        toolbar.addStretch(); toolbar.addWidget(btn_start_table)
        layout.addLayout(toolbar)

        header = QHBoxLayout()
        header.setContentsMargins(15, 5, 15, 5)
        header.addWidget(QLabel("导入画面", styleSheet="color:#a6adc8; font-weight:bold;"), stretch=1)
        header.addWidget(QLabel("导入配音", styleSheet="color:#a6adc8; font-weight:bold;"), stretch=1)
        header.addWidget(QLabel("大标题 (可选)", styleSheet="color:#a6adc8; font-weight:bold;"), stretch=1)
        header.addWidget(QLabel("详细正文文案 (支持多行/不填则盲听)", styleSheet="color:#a6adc8; font-weight:bold;"), stretch=4)
        header.addWidget(QLabel("状态", styleSheet="color:#a6adc8; font-weight:bold;"), stretch=1)
        header.addWidget(QLabel("操作", styleSheet="color:#a6adc8; font-weight:bold;"))
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.table_content = QWidget()
        self.table_layout = QVBoxLayout(self.table_content)
        self.table_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.table_layout.setSpacing(5)
        scroll.setWidget(self.table_content)
        layout.addWidget(scroll, stretch=1)

        btn_add_row = QPushButton("➕ 新增空行")
        btn_add_row.setStyleSheet("background-color: #313244; color: #cdd6f4; font-weight: bold; padding: 10px; border-radius: 5px;")
        btn_add_row.clicked.connect(self.add_table_row)
        layout.addWidget(btn_add_row)
        
        self.add_table_row()

    def add_table_row(self):
        row = BatchTaskRow()
        self.table_layout.addWidget(row)

    def init_folder_tab(self):
        layout = QVBoxLayout(self.tab_folder)
        layout.addWidget(QLabel("1. 选择一个包含视频的文件夹，系统会自动扫描并处理。"))
        layout.addWidget(QLabel("2. 如果文件夹内有同名的 .mp3 文件，系统会自动将其作为配音合成。"))
        
        self.btn_input = QPushButton("📂 选择输入文件夹")
        self.btn_input.setFixedHeight(50)
        self.btn_input.setStyleSheet("background-color: #313244; color: white; font-weight: bold; font-size: 16px; border-radius: 8px;")
        self.btn_input.clicked.connect(self.select_input_dir)
        self.lbl_input = QLabel("未选择")
        
        btn_start_folder = QPushButton("🚀 开始全自动扫盘")
        btn_start_folder.setFixedHeight(60)
        btn_start_folder.setStyleSheet("background-color: #f38ba8; color: #11111b; font-size: 18px; font-weight: bold; border-radius: 8px; margin-top: 20px;")
        btn_start_folder.clicked.connect(self.start_folder_batch)

        layout.addWidget(self.btn_input)
        layout.addWidget(self.lbl_input)
        layout.addStretch()
        layout.addWidget(btn_start_folder)

    def refresh_presets(self):
        self.preset_combo.clear()
        if os.path.exists(PRESETS_FILE):
            try:
                with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                    presets = json.load(f)
                    if presets: self.preset_combo.addItems(list(presets.keys()))
            except: pass
        if self.preset_combo.count() == 0: self.preset_combo.addItem("未找到预设，请先在 Edit 房间保存")

    def select_input_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择包含原视频的文件夹")
        if d: self.input_dir = d; self.lbl_input.setText(d)

    def select_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择成品保存文件夹")
        if d: self.output_dir = d; self.lbl_output.setText(f"当前输出路径: {d}")

    @Slot(str, str)
    def _append_log(self, msg, color):
        self.log_console.append(f"<span style='color:{color}'>{msg}</span>")
        self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    @Slot(int)
    def _update_progress(self, val):
        self.progress_bar.setValue(val)
        
    @Slot(int, str, str)
    def _update_table_row_status(self, idx, text, color):
        if self.tabs.currentIndex() == 0:
            if idx < self.table_layout.count():
                row_widget = self.table_layout.itemAt(idx).widget()
                if isinstance(row_widget, BatchTaskRow):
                    row_widget.lbl_status.setText(text)
                    row_widget.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def start_table_batch(self):
        if self.is_running: return
        self.task_queue.clear()
        
        a_mode = self.audio_mode.currentText()
        for i in range(self.table_layout.count()):
            row_widget = self.table_layout.itemAt(i).widget()
            if isinstance(row_widget, BatchTaskRow):
                if row_widget.video_path:
                    self.task_queue.append({
                        "type": "table",
                        "idx": i,
                        "video": row_widget.video_path,
                        "audio": row_widget.audio_path,
                        "text": row_widget.txt_content.toPlainText().strip(),
                        "a_mode": a_mode
                    })
                else:
                    row_widget.lbl_status.setText("略过:无画面")

        if not self.task_queue: return QMessageBox.warning(self, "提示", "表格中没有任何有效画面！")
        self._start_pipeline("📑 表格任务队列")

    def start_folder_batch(self):
        if self.is_running: return
        if not self.input_dir: return QMessageBox.warning(self, "提示", "请先选择输入文件夹！")
        
        self.task_queue.clear()
        v_files = [f for f in os.listdir(self.input_dir) if f.lower().endswith(('.mp4', '.mov', '.webm', '.jpg', '.png'))]
        a_mode = self.audio_mode.currentText()
        
        for i, vf in enumerate(v_files):
            v_path = os.path.join(self.input_dir, vf)
            base_name = os.path.splitext(vf)[0]
            a_path = ""
            for ext in ['.mp3', '.wav']:
                test_a = os.path.join(self.input_dir, base_name + ext)
                if os.path.exists(test_a): a_path = test_a; break
                
            self.task_queue.append({
                "type": "folder",
                "idx": i,
                "video": v_path,
                "audio": a_path,
                "text": "",
                "a_mode": a_mode
            })
            
        if not self.task_queue: return QMessageBox.warning(self, "提示", "文件夹中没找到视频/图片！")
        self._start_pipeline("📁 文件夹自动队列")

    def _start_pipeline(self, mode_name):
        self.preset_name = self.preset_combo.currentText()
        self.preset_style = {}
        if os.path.exists(PRESETS_FILE):
            try:
                with open(PRESETS_FILE, 'r', encoding='utf-8') as f: self.preset_style = json.load(f).get(self.preset_name, {})
            except: pass

        self.is_running = True
        self.current_idx = 0
        self.log_console.clear()
        self.sig_log.emit(f"🚀 {mode_name} 启动！共发现 {len(self.task_queue)} 个生产任务。", "#a6e3a1")
        self.process_next()

    def process_next(self):
        if self.current_idx >= len(self.task_queue):
            self.sig_all_done.emit()
            return
            
        task = self.task_queue[self.current_idx]
        v_path = task["video"]
        a_path = task["audio"]
        
        out_dir = self.output_dir if self.output_dir else os.path.dirname(v_path)
        out_name = f"Pro_{os.path.basename(v_path).rsplit('.', 1)[0]}.mp4"
        out_path = os.path.join(out_dir, out_name)
        
        c_mode = self.chunk_mode.currentText()
        
        self.sig_table_row_status.emit(task["idx"], "🔄 正在渲染", "#f9e2af")
        self.sig_progress.emit(0)
        
        threading.Thread(target=self.pipeline_worker, args=(task, out_path, c_mode), daemon=True).start()

    def pipeline_worker(self, task, out_path, c_mode):
        temp_dir = tempfile.mkdtemp()
        try:
            v_path = task["video"]
            a_path = task["audio"]
            custom_text = task["text"]
            t_idx = task["idx"]
            a_mode = task.get("a_mode", "🔇 替换/静音 (仅配音)")
            
            self.sig_log.emit(f"▶ 开始装配视频: {os.path.basename(v_path)}", "#89b4fa")
            
            subs_data = []
            
            target_path = a_path if a_path else v_path
            use_custom_text = bool(custom_text.strip())

            self.sig_log.emit(f"  [1/4] 抽取音频供 AI 识别{'并对齐手工文案' if use_custom_text else ''}...", "#cdd6f4")
            temp_audio = os.path.join(temp_dir, "temp.mp3")
            # 👑 防爆修复：加入 -t 600 强制截断最大10分钟，加入 -map a:0 强制只取一条正常音轨，防止乱码轨道无限膨胀
            subprocess.run([get_ffmpeg_cmd(), "-y", "-i", target_path, "-vn", "-map", "a:0", "-ar", "16000", "-ac", "1", "-b:a", "16k", "-t", "600", temp_audio], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000 if os.name == 'nt' else 0)
            
            # 安全检查：如果抽出来的文件大得离谱（比如大于 10MB），直接拦截报错，不浪费 API 请求
            if os.path.exists(temp_audio) and os.path.getsize(temp_audio) > 10 * 1024 * 1024:
                raise Exception(f"源文件音频轨道异常，抽离出的体积高达 {os.path.getsize(temp_audio)/1024/1024:.1f}MB，已被系统紧急拦截！")
                
            self.sig_progress.emit(10)
            self.sig_log.emit(f"  [2/4] 呼叫 Cloudflare 大模型...", "#cdd6f4")

            accounts = local_get_cf_accounts()
            if not accounts: raise Exception("未配置 Cloudflare API 凭证！")

            res_json = None; last_err = ""
            with open(temp_audio, 'rb') as f: data = f.read()
            for acc in accounts:
                if acc.get("id") and acc.get("token"):
                    try:
                        res = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{acc['id']}/ai/run/@cf/openai/whisper", headers={"Authorization": f"Bearer {acc['token']}", "Content-Type": "application/octet-stream"}, data=data, timeout=60) 
                        if res.status_code == 200 and res.json().get("success"): res_json = res.json(); break 
                    except Exception as e: last_err = str(e)
            if not res_json: raise Exception(f"AI 请求失败: {last_err}")

            clean_words = [{"word": re.sub(r'(?i)stereo_[^\s]+', '', w["word"]).strip(), "start": w["start"], "end": w["end"]} for w in res_json["result"]["words"] if re.sub(r'(?i)stereo_[^\s]+', '', w["word"]).strip()]

            if use_custom_text:
                self.sig_log.emit("  [2.5/4] 检测到手工文案，正在把文案对齐到 AI 时间轴...", "#a6e3a1")
                clean_words = self._align_user_text_to_ai_words(clean_words, custom_text)

            subs_data = self.process_words(clean_words, c_mode)
            for sub in subs_data:
                sub["style"] = self.preset_style.copy()

            self.sig_progress.emit(30)

            self.sig_log.emit(f"  [3/4] 启动 30FPS 特效物理引擎...", "#cdd6f4")
            concat_path = os.path.join(temp_dir, "subs_concat.txt").replace("\\", "/")
            blank_path = os.path.join(temp_dir, "blank.png").replace("\\", "/")
            
            try: proj_w, proj_h = get_video_dimensions(v_path)
            except: proj_w, proj_h = 1080, 1920
            
            v_dur = get_exact_duration(v_path)
            a_dur = get_exact_duration(a_path) if a_path else 0
            total_dur = max(max(v_dur, a_dur), 5.0)

            with sync_playwright() as p:
                b_path = get_browser_path()
                browser = p.chromium.launch(headless=True, executable_path=b_path) if b_path else p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": proj_w, "height": proj_h}, device_scale_factor=1)
                page.set_content("<html><body style='background:transparent;'></body></html>")
                page.screenshot(path=blank_path, omit_background=True)

                with open(concat_path, "w", encoding="utf-8") as f_concat:
                    current_time = 0.0; frame_idx = 0; frame_step = 1.0 / 30.0
                    
                    while current_time < total_dur:
                        active_subs = [s for s in subs_data if float(s.get('start', 0)) <= current_time <= float(s.get('end', 1))]
                        if not active_subs:
                            future_starts = [float(s.get('start', 0)) for s in subs_data if float(s.get('start', 0)) > current_time]
                            if future_starts:
                                next_start = min(future_starts)
                                f_concat.write(f"file '{blank_path}'\nduration {(next_start - current_time):.3f}\n")
                                current_time = next_start
                            else:
                                gap = total_dur - current_time
                                if gap > 0: f_concat.write(f"file '{blank_path}'\nduration {gap:.3f}\n")
                                current_time = total_dur
                            continue
                        
                        html_subs = ""
                        for s in active_subs:
                            px = s.get("pos_x", 0.0); py = s.get("pos_y", 25.0)
                            base_css = f"position: absolute; left: calc(50% + {px}%); top: calc(50% + {py}%); transform: translate(-50%, -50%); z-index: 10; width: max-content; max-width: 92%;"
                            sub_html = render_subtitle_html(s, current_time, proj_w)
                            html_subs += f"<div style='{base_css}'>{sub_html}</div>\n"
                        
                        html_content = f"<!DOCTYPE html><html><head><style>html, body {{ margin: 0; padding: 0; width: 100vw; height: 100vh; overflow: hidden; background: transparent; display: flex; justify-content: center; align-items: center; }} #scale-wrapper {{ width: 100vw; height: 100vh; position: absolute; left: 0; top: 0; }}</style></head><body><div id='scale-wrapper'>{html_subs}</div></body></html>"
                        page.set_content(html_content)
                        frame_path = os.path.join(temp_dir, f"f_{frame_idx}.png").replace("\\", "/")
                        page.screenshot(path=frame_path, omit_background=True)
                        f_concat.write(f"file '{frame_path}'\nduration {frame_step:.3f}\n")
                        current_time += frame_step; frame_idx += 1
                        
            self.sig_progress.emit(70)

            # 👑 步骤 3: 全新 FFmpeg 静音与混轨处理引擎
            self.sig_log.emit(f"  [4/4] 最终封装: 根据 {a_mode.split(' ')[0]} 压制中...", "#cdd6f4")
            
            v_loop_path = os.path.join(temp_dir, "v_loop.txt").replace("\\", "/")
            with open(v_loop_path, 'w', encoding='utf-8') as f:
                loop_count = int(total_dur / max(0.1, v_dur)) + 1
                for _ in range(loop_count): f.write(f"file '{v_path.replace('\\', '/')}'\n")

            has_audio_file = bool(a_path and os.path.exists(a_path))
            
            args = ["-y", "-f", "concat", "-safe", "0", "-i", v_loop_path, "-f", "concat", "-safe", "0", "-i", concat_path]
            if has_audio_file: args.extend(["-i", a_path])
            
            vf = f"[0:v]scale={proj_w}:{proj_h}:force_original_aspect_ratio=increase,crop={proj_w}:{proj_h},format=yuv420p[bg];[bg][1:v]overlay=0:0:shortest=1,format=yuv420p[outv]"
            
            if "混合" in a_mode and has_audio_file:
                # 混合模式 (仅在配音存在时有效)
                af = "[0:a][2:a]amix=inputs=2:duration=longest[outa]"
                args.extend(["-filter_complex", f"{vf};{af}", "-map", "[outv]", "-map", "[outa]", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-t", str(total_dur), out_path])
            elif "保留" in a_mode:
                # 强制只用视频原声，丢弃配音
                args.extend(["-filter_complex", vf, "-map", "[outv]", "-map", "0:a?", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-t", str(total_dur), out_path])
            else:
                # 替换/静音模式
                if has_audio_file:
                    args.extend(["-filter_complex", vf, "-map", "[outv]", "-map", "2:a:0", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-t", str(total_dur), out_path])
                else:
                    # 👑 真正的纯净静音：没有上传配音，同时要求丢掉原声
                    args.extend(["-filter_complex", vf, "-map", "[outv]", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-an", "-t", str(total_dur), out_path])
            
            proc = subprocess.run([get_ffmpeg_cmd()] + args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=0x08000000 if os.name == 'nt' else 0)
            if proc.returncode != 0: raise Exception(f"FFmpeg 渲染失败!")
            
            self.sig_log.emit(f"✅ {os.path.basename(v_path)} 交付成功！", "#a6e3a1")
            self.sig_progress.emit(100)
            self.sig_table_row_status.emit(t_idx, "✅ 完成", "#a6e3a1")

        except Exception as e:
            self.sig_log.emit(f"❌ 任务失败: {str(e)}", "#f38ba8")
            self.sig_table_row_status.emit(task["idx"], "❌ 失败", "#f38ba8")
        finally:
            try: shutil.rmtree(temp_dir)
            except: pass
            self.sig_file_done.emit()

    def _load_nlp_dict(self):
        dict_path = os.path.join(os.getcwd(), "nlp_dictionary.txt")
        default_words = [
            "a", "an", "the", "to", "in", "on", "at", "of", "for", "with", "from", "by", "about", 
            "as", "into", "like", "through", "after", "over", "between", "out", "against", "during", 
            "without", "before", "under", "around", "among", "and", "but", "or", "so", "because",
            "my", "your", "his", "her", "its", "our", "their", "this", "that", "these", "those",
            "is", "am", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", 
            "does", "did", "will", "would", "shall", "should", "can", "could", "may", "might", "must",
            "very", "too", "not"
        ]
        
        if not os.path.exists(dict_path):
            try:
                with open(dict_path, 'w', encoding='utf-8') as f:
                    for w in default_words: f.write(f"{w}\n")
            except: pass
            return set(default_words)
            
        custom_words = set()
        try:
            with open(dict_path, 'r', encoding='utf-8') as f:
                for line in f:
                    clean_line = line.split('#')[0].strip().lower() 
                    if clean_line: custom_words.add(clean_line)
            return custom_words if custom_words else set(default_words)
        except: return set(default_words)

    def _tokenize_user_text_for_alignment(self, raw_text):
        raw_text = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
        tokens = []
        for line_idx, line in enumerate(raw_text.split("\n")):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if not parts:
                continue
            if tokens and line_idx > 0:
                parts[0] = "\n" + parts[0].lstrip()
            tokens.extend(parts)
        return tokens

    def _align_user_text_to_ai_words(self, ai_words, raw_text):
        user_tokens = self._tokenize_user_text_for_alignment(raw_text)
        if not ai_words or not user_tokens:
            return ai_words

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
            if end <= start:
                end = start + 0.01
            aligned.append({"word": token, "start": start, "end": end})
        return aligned

    def process_words(self, words, mode):
        NON_END_WORDS = self._load_nlp_dict()
        subs = []; curr = {"words": []}; puncts = ['.', '!', '?', ',', '，', '。', '！', '？']
        
        for i, w in enumerate(words):
            if not curr["words"]: curr["start"] = w["start"]
            curr["words"].append({"text": w["word"], "start": w["start"], "end": w["end"]})
            curr["end"] = w["end"]
            
            clean_w = re.sub(r'[^a-zA-Z0-9\']', '', w["word"]).lower()
            has_punct = any(w["word"].endswith(p) for p in puncts)
            is_last_word = (i == len(words) - 1)
            
            if "单字" in mode: is_break = True
            elif "3-5字" in mode:
                if has_punct or len(curr["words"]) >= 4:
                    if clean_w in NON_END_WORDS and not is_last_word and len(curr["words"]) < 8: is_break = False
                    else: is_break = True
                else: is_break = False
            else: 
                if has_punct or len(curr["words"]) >= 10:
                    if clean_w in NON_END_WORDS and not is_last_word and len(curr["words"]) < 15: is_break = False
                    else: is_break = True
                else: is_break = False
                    
            if is_break: 
                curr["text"] = " ".join([x["text"] for x in curr["words"]])
                curr["pos_x"] = 0.0; curr["pos_y"] = 25.0; curr["track"] = 1
                subs.append(curr); curr = {"words": []}
                
        if curr["words"]: 
            curr["text"] = " ".join([x["text"] for x in curr["words"]])
            curr["pos_x"] = 0.0; curr["pos_y"] = 25.0; curr["track"] = 1
            subs.append(curr)
            
        return subs

    @Slot()
    def _on_file_done(self):
        self.current_idx += 1
        self.process_next()

    @Slot()
    def _on_all_done(self):
        self.is_running = False
        btn_start_table = self.findChild(QPushButton, "🚀 开始批量流水线")
        if btn_start_table: btn_start_table.setEnabled(True)
        self.log_console.append("🎉 所有矩阵任务圆满完成！")
        QMessageBox.information(self, "批量完成", "恭喜，矩阵批量生成完毕！")