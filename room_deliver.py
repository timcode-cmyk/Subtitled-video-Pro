# ==========================================
# 文件名: room_deliver.py (稳定版)
# ==========================================
import os
import json
import tempfile
import re
import threading
import subprocess
import shutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QProgressBar, QTextEdit, QFileDialog, QMessageBox, QDoubleSpinBox
)
from PySide6.QtCore import QProcess, QTimer
from core import get_ffmpeg_cmd
from playwright.sync_api import sync_playwright

from ui_components import get_video_dimensions, render_subtitle_html

CACHE_FILE = os.path.join(tempfile.gettempdir(), "sh_v8_project_cache.json")


def get_browser_path():
    if os.name == 'nt':
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
    else:
        paths = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


class DeliverView(QWidget):
    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.project_state = {}
        self.render_process = None
        self.temp_dir = ""
        self.concat_path = ""
        self.out_file_path = ""
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        left_panel = QFrame()
        left_panel.setStyleSheet("background-color: #181825; border-radius: 10px;")
        left_panel.setFixedWidth(380)
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("📦 渲染交付设置 (Deliver)", styleSheet="font-size: 18px; font-weight: bold; color: #cdd6f4;"))
        left_layout.addSpacing(20)
        self.lbl_info = QLabel("等待加载工程...")
        self.lbl_info.setStyleSheet("color: #a6e3a1; font-size: 14px; line-height: 1.5;")
        left_layout.addWidget(self.lbl_info)
        left_layout.addSpacing(20)

        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("⏱️ 目标导出时长 (秒):", styleSheet="color: #f9e2af; font-weight: bold;"))
        self.spin_duration = QDoubleSpinBox()
        self.spin_duration.setRange(1.0, 36000.0)
        self.spin_duration.setStyleSheet("background: #313244; color: white; padding: 5px; font-size: 14px; border-radius: 3px;")
        dur_row.addWidget(self.spin_duration)
        left_layout.addLayout(dur_row)

        left_layout.addWidget(QLabel("✅ 多轨道时间推演 / 混音器 / 画面缩放\n底层核心已全量挂载！", styleSheet="color: #89b4fa; margin-top: 15px;"))
        left_layout.addStretch()

        self.btn_render = QPushButton("🚀 开始压制导出成片")
        self.btn_render.setFixedHeight(55)
        self.btn_render.setStyleSheet("background-color: #f38ba8; color: #11111b; font-size: 16px; font-weight: bold; border-radius: 8px;")
        self.btn_render.clicked.connect(self.start_render)
        left_layout.addWidget(self.btn_render)
        main_layout.addWidget(left_panel)

        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: #1e1e2e; border-radius: 10px;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("📋 压制日志 (Render Log)", styleSheet="font-size: 16px; font-weight: bold; color: #89b4fa;"))
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #11111b; color: #a6adc8; font-family: Consolas; font-size: 13px; border: none; padding: 10px;")
        right_layout.addWidget(self.log_console)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("QProgressBar { border: 2px solid #313244; border-radius: 5px; text-align: center; color: white; font-weight: bold; } QProgressBar::chunk { background-color: #a6e3a1; }")
        self.progress_bar.setValue(0)
        right_layout.addWidget(self.progress_bar)
        main_layout.addWidget(right_panel, stretch=1)

    def _summarize_project_state(self):
        clips = self.project_state.get("video_clips", [])
        a_path = self.project_state.get("audio_path", "")
        dur = self.project_state.get("duration", 10.0)
        sub_count = len(self.project_state.get("subs_data", []))
        v_info = f"{len(clips)} 个弹性复合片段" if clips else "未导入"
        a_name = os.path.basename(a_path) if a_path else "未导入"
        info = f"🎥 视频源: {v_info}\n🎵 音频源: {a_name}\n📝 独立字幕片段: {sub_count} 个"
        self.lbl_info.setText(info)
        self.spin_duration.setValue(max(1.0, float(dur or 10.0)))

    def load_project_data(self):
        try:
            parent = self.parent()
            project = getattr(parent, "project", None) if parent else None
            if isinstance(project, dict) and project.get("room_state", {}).get("edit_room"):
                self.project_data = project
                self.project_state = dict(project.get("room_state", {}).get("edit_room", {}))
            elif isinstance(self.project_data, dict) and self.project_data.get("room_state", {}).get("edit_room"):
                self.project_state = dict(self.project_data.get("room_state", {}).get("edit_room", {}))
            elif os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self.project_state = json.load(f)
            else:
                self.project_state = {}
            self._summarize_project_state()
        except Exception:
            self.project_state = {}
            self.lbl_info.setText("❌ 工程数据读取失败")

    def log_safe(self, msg, color="#cdd6f4"):
        QTimer.singleShot(0, lambda: self._log_msg(msg, color))

    def _log_msg(self, msg, color):
        self.log_console.append(f"<span style='color:{color}'>{msg}</span>")
        self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    def update_progress_safe(self, val):
        QTimer.singleShot(0, lambda: self.progress_bar.setValue(int(val)))

    def start_render(self):
        self.load_project_data()
        subs = self.project_state.get("subs_data", [])
        clips = self.project_state.get("video_clips", [])
        a_path = self.project_state.get("audio_path", "")

        self.log_console.clear()
        self.progress_bar.setValue(0)
        self.log_safe(f"📊 字幕数: {len(subs)}", "#89b4fa")
        self.log_safe(f"📊 视频数: {len(clips)}", "#89b4fa")
        self.log_safe(f"📊 音频路径: {a_path or '未提供'}", "#89b4fa")

        if not clips:
            return QMessageBox.warning(self, "提示", "请先在 Edit 房间导入至少一个视频片段并保存工程！")
        if not subs:
            return QMessageBox.warning(self, "提示", "当前工程没有字幕数据。请先在 Edit 房间生成字幕并点“保存工程”。")
        if not a_path:
            self.log_safe("⚠️ 未检测到独立音频，将尝试使用视频原声；若原视频也无音轨，则输出静音视频。", "#f9e2af")

        file_path, _ = QFileDialog.getSaveFileName(self, "导出最终视频", "", "MP4 Files (*.mp4)")
        if not file_path:
            return
        self.out_file_path = file_path
        self.btn_render.setEnabled(False)
        self.log_safe("🚀 [阶段 1/2] 启动全局时间推演引擎 (多轨道同频渲染)...", "#f9e2af")
        threading.Thread(target=self.generate_html_frames, daemon=True).start()

    def generate_html_frames(self):
        try:
            self.temp_dir = tempfile.mkdtemp(prefix="subtitle_render_")
            self.concat_path = os.path.join(self.temp_dir, "subs_concat.txt").replace("\\", "/")
            blank_path = os.path.join(self.temp_dir, "blank.png").replace("\\", "/")
            subs_data = self.project_state.get("subs_data", [])
            total_dur = float(self.spin_duration.value())

            clips = self.project_state.get("video_clips", [])
            proj_w, proj_h = 1080, 1920
            res_text = self.project_state.get("resolution", "自动检测")
            if "自动跟随" in res_text and clips:
                proj_w, proj_h = get_video_dimensions(clips[0]["path"])
            elif "1080x1920" in res_text:
                proj_w, proj_h = 1080, 1920
            elif "1920x1080" in res_text:
                proj_w, proj_h = 1920, 1080
            elif "1080x1080" in res_text:
                proj_w, proj_h = 1080, 1080

            with sync_playwright() as p:
                b_path = get_browser_path()
                browser = p.chromium.launch(headless=True, executable_path=b_path) if b_path else p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": proj_w, "height": proj_h}, device_scale_factor=1)
                page.set_content("<html><body style='background:transparent;'></body></html>")
                page.screenshot(path=blank_path, omit_background=True)

                with open(self.concat_path, "w", encoding="utf-8") as f_concat:
                    current_time = 0.0
                    frame_idx = 0
                    fps = 30
                    frame_step = 1.0 / fps

                    while current_time < total_dur:
                        active_subs = [s for s in subs_data if float(s.get('start', 0)) <= current_time <= float(s.get('end', 1))]
                        if not active_subs:
                            future_starts = [float(s.get('start', 0)) for s in subs_data if float(s.get('start', 0)) > current_time]
                            if future_starts:
                                next_start = min(future_starts)
                                gap = next_start - current_time
                                f_concat.write(f"file '{blank_path}'\nduration {gap:.3f}\n")
                                current_time = next_start
                            else:
                                gap = total_dur - current_time
                                if gap > 0:
                                    f_concat.write(f"file '{blank_path}'\nduration {gap:.3f}\n")
                                current_time = total_dur
                            continue

                        html_subs = ""
                        for s in active_subs:
                            px = s.get("pos_x", 0.0)
                            py = s.get("pos_y", 25.0)
                            trk = s.get("track", 1)
                            z_idx = 10 if trk == 0 else 5
                            base_css = f"position: absolute; left: calc(50% + {px}%); top: calc(50% + {py}%); transform: translate(-50%, -50%); z-index: {z_idx}; width: max-content; max-width: 92%;"
                            sub_html = render_subtitle_html(s, current_time, proj_w)
                            html_subs += f"<div style='{base_css}'>{sub_html}</div>\n"

                        html_content = f"""<!DOCTYPE html>
                        <html>
                        <head>
                            <style>
                                html, body {{ margin: 0; padding: 0; width: 100vw; height: 100vh; overflow: hidden; background: transparent; display: flex; justify-content: center; align-items: center; -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }}
                                #scale-wrapper {{ width: 100vw; height: 100vh; position: absolute; left: 0; top: 0; }}
                            </style>
                        </head>
                        <body>
                            <div id="scale-wrapper">
                                {html_subs}
                            </div>
                        </body>
                        </html>"""

                        page.set_content(html_content)
                        frame_path = os.path.join(self.temp_dir, f"f_{frame_idx}.png").replace("\\", "/")
                        page.screenshot(path=frame_path, omit_background=True)
                        f_concat.write(f"file '{frame_path}'\nduration {frame_step:.3f}\n")
                        current_time += frame_step
                        frame_idx += 1
                        self.update_progress_safe(int((current_time / total_dur) * 50))

                browser.close()
            self.log_safe("✅ 多轨道推演截图完毕！准备混音与剪辑...", "#a6e3a1")
            QTimer.singleShot(0, self.start_ffmpeg_qprocess)
        except Exception as e:
            self.log_safe(f"❌ 绘制失败: {str(e)}", "#f38ba8")
            QTimer.singleShot(0, lambda: self.btn_render.setEnabled(True))

    def start_ffmpeg_qprocess(self):
        self.log_safe("🚀 [阶段 2/2] 唤醒 FFmpeg 引擎，执行混合压制...", "#f9e2af")
        clips = self.project_state.get("video_clips", [])
        a_path = self.project_state.get("audio_path")
        target_dur = float(self.spin_duration.value())

        v_scale = self.project_state.get("v_scale", 100) / 100.0
        v_vol = self.project_state.get("v_volume", 100) / 100.0
        a_vol = self.project_state.get("a_volume", 100) / 100.0

        res_text = self.project_state.get("resolution", "自动检测")
        proj_w, proj_h = 1080, 1920
        if "1920x1080" in res_text:
            proj_w, proj_h = 1920, 1080
        elif "1080x1080" in res_text:
            proj_w, proj_h = 1080, 1080
        elif "自动跟随" in res_text and clips:
            proj_w, proj_h = get_video_dimensions(clips[0]["path"])

        video_concat_path = ""
        has_audio = False
        if clips:
            try:
                flags = 0x08000000 if os.name == 'nt' else 0
                res = subprocess.run([get_ffmpeg_cmd(), "-i", clips[0]["path"]], stderr=subprocess.PIPE, stdout=subprocess.PIPE, creationflags=flags, text=True, encoding='utf-8', errors='ignore')
                if "Audio:" in res.stderr:
                    has_audio = True
            except Exception:
                pass

            video_concat_path = os.path.join(self.temp_dir, "v_blocks.txt").replace("\\", "/")
            with open(video_concat_path, "w", encoding="utf-8") as f:
                for clip in clips:
                    clip_path = clip.get("path", "")
                    if not clip_path:
                        continue
                    c_start = float(clip.get("start", 0))
                    c_end = float(clip.get("end", 5.0))
                    c_dur = max(0.001, c_end - c_start)
                    m_dur = max(0.1, float(clip.get("dur", 5.0)))
                    t_rem = c_dur
                    while t_rem > 0:
                        p_dur = min(t_rem, m_dur)
                        safe_path = clip_path.replace("\\", "/")
                        f.write(f"file '{safe_path}'\n")
                        f.write("inpoint 0\n")
                        f.write(f"outpoint {p_dur:.3f}\n")
                        t_rem -= p_dur
            self.log_safe("🛠️ 已生成物理拼接流: 精确修剪时间点挂载完毕！", "#89b4fa")

        self.render_process = QProcess(self)
        self.render_process.readyReadStandardError.connect(self.on_render_ready_read_error)
        self.render_process.finished.connect(self.on_render_finished)

        args = ["-y"]
        if video_concat_path:
            args.extend(["-f", "concat", "-safe", "0", "-i", video_concat_path])
        args.extend(["-f", "concat", "-safe", "0", "-i", self.concat_path])
        if a_path:
            args.extend(["-i", a_path])

        sub_idx = 1 if video_concat_path else 0
        fc_parts = []
        audio_map = None

        if video_concat_path:
            vf_scale = f"scale={proj_w}*{v_scale}:{proj_h}*{v_scale}:force_original_aspect_ratio=increase"
            vf_crop = f"crop={proj_w}:{proj_h}"
            # 👑 修复：加入 shortest=1，强制跟随最短轨道，防止片尾无限拉长
            fc_parts.append(f"[0:v]{vf_scale},{vf_crop},format=yuv420p[bg];[bg][{sub_idx}:v]overlay=0:0:shortest=1,format=yuv420p[outv]")
            if a_path:
                if has_audio:
                    fc_parts.append(f"[0:a]volume={v_vol}[va]")
                else:
                    fc_parts.append("anullsrc=r=44100:cl=stereo[va]")
                fc_parts.append(f"[2:a]volume={a_vol}[aa]")
                fc_parts.append("[va][aa]amix=inputs=2:duration=longest[aout]")
                audio_map = "[aout]"
            elif has_audio:
                fc_parts.append(f"[0:a]volume={v_vol}[va]")
                audio_map = "[va]"
        elif a_path:
            fc_parts.append("[0:v]format=yuv420p[outv]")
            fc_parts.append(f"[1:a]volume={a_vol}[aout]")
            audio_map = "[aout]"

        if fc_parts:
            args.extend(["-filter_complex", ";".join(fc_parts)])

        if video_concat_path:
            args.extend(["-map", "[outv]"])
        else:
            args.extend(["-map", f"{sub_idx}:v"])

        if audio_map:
            args.extend(["-map", audio_map, "-c:a", "aac", "-b:a", "192k"])
        else:
            args.append("-an")

        # 👑 极速高压引擎：锁定 30 帧(-r 30)，画质降低冗余(-crf 24)，并开启极速预设(-preset superfast)
        args.extend(["-c:v", "libx264", "-preset", "superfast", "-crf", "24", "-r", "30", "-max_muxing_queue_size", "1024", "-t", str(target_dur), self.out_file_path])
        
        self.log_safe("🧾 FFmpeg 参数已生成，开始压制...", "#89b4fa")
        self.render_process.start(get_ffmpeg_cmd(), args)

    def on_render_ready_read_error(self):
        err_out = str(self.render_process.readAllStandardError(), encoding="utf-8", errors="ignore")
        time_match = re.search(r"time=(\d+:\d+:\d+\.\d+)", err_out)
        if time_match:
            time_str = time_match.group(1)
            h, m, s = map(float, time_str.split(":"))
            curr_sec = h * 3600 + m * 60 + s
            total_sec = max(0.1, self.spin_duration.value())
            percent = 50 + int((curr_sec / total_sec) * 50)
            self.progress_bar.setValue(min(100, percent))
        if err_out.strip():
            self.log_console.append(f"<span style='color:#6c7086'>{err_out.strip()}</span>")
            self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    def on_render_finished(self, exit_code, exit_status):
        self.btn_render.setEnabled(True)
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass
        if exit_code == 0:
            self.progress_bar.setValue(100)
            self.log_safe("🎉 渲染完美收官！视频已成功输出。", "#a6e3a1")
            QMessageBox.information(self, "出片完成", "字幕、音频、画面已按当前工程成功导出。")
        else:
            self.log_safe(f"❌ 渲染崩塌，错误代码: {exit_code}", "#f38ba8")
            QMessageBox.critical(self, "失败", "FFmpeg 渲染发生错误，请查看日志！")
