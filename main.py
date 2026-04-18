# ==========================================
# 文件名: main.py (工程房间完整版)
# ==========================================
import sys
import os
import threading

os.environ["QT_OPENGL"] = "software"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

if sys.platform == "win32":
    os.environ["QT_GL_ADAPTER_TYPE"] = "any"

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--ignore-gpu-blocklist "
    "--num-raster-threads=4 "
    "--disable-gpu "
    "--disable-gpu-compositing "
    "--disable-gpu-rasterization "
    "--disable-software-rasterizer"
)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QStackedWidget
)

from core import auto_sync_cloud_data
from project_io import load_or_create_default_project, update_room_state
from room_project import ProjectView
from room_edit import EditView
from room_scroll import ScrollView
from room_batch import BatchView
from room_deliver import DeliverView
from room_settings import SettingsView


class SubtitledvideoPro(QMainWindow):
    def __init__(self, project_data):
        super().__init__()
        self.setWindowTitle("Subtitle Video Pro - 工程房间版")
        self.resize(1600, 980)
        self.setStyleSheet("background-color: #11111b; color: #cdd6f4;")

        self.project = project_data or {}
        self.rooms = []
        self.current_room_index = 0

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack, stretch=1)

        self.create_sidebar()
        self.create_rooms()
        self.open_default_room()

    def create_sidebar(self):
        nav_widget = QWidget()
        nav_widget.setStyleSheet("background-color: #181825; border-top: 1px solid #313244;")
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(10, 10, 10, 10)
        nav_layout.setSpacing(10)

        nav_btn_style = """
            QPushButton { background-color: transparent; color: #a6adc8; font-size: 14px; font-weight: bold; border: none; padding: 10px 14px; border-radius: 8px; }
            QPushButton:hover { background-color: #313244; color: #cdd6f4; }
            QPushButton:checked { background-color: #313244; color: #a6e3a1; }
        """

        self.btn_project = QPushButton("📁 工程")
        self.btn_edit = QPushButton("🎬 精修")
        self.btn_scroll = QPushButton("🔥 滚动")
        self.btn_batch = QPushButton("📦 批量")
        self.btn_deliver = QPushButton("🚀 导出")
        self.btn_settings = QPushButton("⚙️ 设置")

        self.nav_buttons = [
            self.btn_project,
            self.btn_edit,
            self.btn_scroll,
            self.btn_batch,
            self.btn_deliver,
            self.btn_settings,
        ]

        for btn in self.nav_buttons:
            btn.setStyleSheet(nav_btn_style)
            btn.setCheckable(True)

        nav_layout.addStretch()
        for btn in self.nav_buttons:
            nav_layout.addWidget(btn)
        nav_layout.addStretch()
        self.main_layout.addWidget(nav_widget)

        self.btn_project.clicked.connect(lambda: self.switch_room(0))
        self.btn_edit.clicked.connect(lambda: self.switch_room(1))
        self.btn_scroll.clicked.connect(lambda: self.switch_room(2))
        self.btn_batch.clicked.connect(lambda: self.switch_room(3))
        self.btn_deliver.clicked.connect(lambda: self.switch_room(4))
        self.btn_settings.clicked.connect(lambda: self.switch_room(5))

    def create_rooms(self):
        self.room_project = ProjectView(self.project, self)
        self.room_edit = EditView(self.project, self)
        self.room_scroll = ScrollView(self.project, self)
        self.room_batch = BatchView(self)
        self.room_deliver = DeliverView(self.project, self)
        self.room_settings = SettingsView(self)

        self.rooms = [
            self.room_project,
            self.room_edit,
            self.room_scroll,
            self.room_batch,
            self.room_deliver,
            self.room_settings,
        ]
        for room in self.rooms:
            self.stack.addWidget(room)

    def open_default_room(self):
        self.switch_room(0, initial=True)

    def refresh_room_links(self):
        if hasattr(self, "room_project"):
            self.room_project.project_data = self.project
            self.room_project.sync_current_project_label()

        if hasattr(self.room_edit, "project_data"):
            self.room_edit.project_data = self.project

        if hasattr(self.room_scroll, "project_data"):
            self.room_scroll.project_data = self.project
        if hasattr(self.room_scroll, "load_from_project"):
            self.room_scroll.load_from_project(self.project)

        if hasattr(self.room_deliver, "project_data"):
            self.room_deliver.project_data = self.project
        if hasattr(self.room_deliver, "load_project_data"):
            self.room_deliver.load_project_data()

    def reload_rooms_from_project(self):
        if hasattr(self.room_edit, "project_data"):
            self.room_edit.project_data = self.project
        if hasattr(self.room_edit, "load_project_on_boot"):
            self.room_edit.load_project_on_boot()

        if hasattr(self.room_scroll, "project_data"):
            self.room_scroll.project_data = self.project
        if hasattr(self.room_scroll, "load_from_project"):
            self.room_scroll.load_from_project(self.project)

        if hasattr(self.room_deliver, "project_data"):
            self.room_deliver.project_data = self.project
        if hasattr(self.room_deliver, "load_project_data"):
            self.room_deliver.load_project_data()

        self.refresh_room_links()

    def switch_room(self, index, initial=False):
        if not initial and self.current_room_index == 1 and hasattr(self.room_edit, "save_to_project"):
            self.project = self.room_edit.save_to_project(silent=True)

        if not initial and self.current_room_index == 2 and hasattr(self.room_scroll, "export_state"):
            self.project = update_room_state(self.project, "scroll_room", self.room_scroll.export_state())
            self.room_scroll.project_data = self.project

        self.current_room_index = index
        self.refresh_room_links()
        self.stack.setCurrentIndex(index)

        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

        if index == 4 and hasattr(self.room_deliver, "load_project_data"):
            self.room_deliver.load_project_data()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    threading.Thread(target=auto_sync_cloud_data, daemon=True).start()

    project_data = load_or_create_default_project(os.getcwd())

    window = SubtitledvideoPro(project_data)
    window.showMaximized()
    sys.exit(app.exec())
