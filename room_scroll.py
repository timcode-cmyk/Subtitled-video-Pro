from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QMessageBox

from project_io import update_room_state


class ScrollView(QWidget):
    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.state = {"pages": []}
        self.init_ui()
        self.load_from_project(self.project_data)

    def init_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel("🔥 滚动字幕房间")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        desc = QLabel("这个房间之前没有落地实现，导致主程序一启动就会因为缺少 room_scroll.py 直接失败。\n现在先接上基础版：支持输入滚动字幕页面并保存到工程文件。")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #a6adc8;")
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("每一行当作一页滚动字幕，后面再继续扩展样式和导出。")
        self.btn_save = QPushButton("💾 保存滚动字幕")
        self.btn_save.clicked.connect(self.manual_save)
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(self.editor, stretch=1)
        layout.addWidget(self.btn_save)

    def load_from_project(self, project_data):
        self.project_data = project_data or self.project_data or {}
        pages = []
        if isinstance(self.project_data, dict):
            pages = self.project_data.get("room_state", {}).get("scroll_room", {}).get("pages", [])
            if not pages:
                pages = self.project_data.get("scroll_pages", [])
        self.state["pages"] = list(pages or [])
        self.editor.setPlainText("\n".join(self.state["pages"]))

    def export_state(self):
        pages = [line.strip() for line in self.editor.toPlainText().splitlines() if line.strip()]
        self.state = {"pages": pages}
        return self.state

    def manual_save(self):
        parent = self.parent()
        if parent and hasattr(parent, "project"):
            parent.project = update_room_state(parent.project, "scroll_room", self.export_state())
            self.project_data = parent.project
        QMessageBox.information(self, "保存成功", "滚动字幕内容已写入工程文件。")
