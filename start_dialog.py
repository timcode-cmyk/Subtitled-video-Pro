from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QPushButton, QFileDialog
)
from project_io import create_project, load_project


class StartDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("选择操作")

        self.project_data = None
        self.project_path = None

        layout = QVBoxLayout()

        btn_new_edit = QPushButton("新建工程（逐句精修）")
        btn_new_scroll = QPushButton("新建工程（滚动字幕）")
        btn_open = QPushButton("打开工程")

        btn_new_edit.clicked.connect(self.new_edit)
        btn_new_scroll.clicked.connect(self.new_scroll)
        btn_open.clicked.connect(self.open_project)

        layout.addWidget(btn_new_edit)
        layout.addWidget(btn_new_scroll)
        layout.addWidget(btn_open)

        self.setLayout(layout)

    def new_edit(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存工程", "", "Project (*.scomp)")
        if path:
            self.project_data = create_project(path, "edit_room")
            self.project_path = path
            self.accept()

    def new_scroll(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存工程", "", "Project (*.scomp)")
        if path:
            self.project_data = create_project(path, "scroll_room")
            self.project_path = path
            self.accept()

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开工程", "", "Project (*.scomp)")
        if path:
            self.project_data = load_project(path)
            self.project_path = path
            self.accept()