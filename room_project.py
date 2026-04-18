# ==========================================
# 文件名: room_project.py (加入项目重命名与删除功能)
# ==========================================
import os
import shutil

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QMessageBox, QFrame, QScrollArea, QGridLayout, QInputDialog, QGraphicsDropShadowEffect, QSplitter
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QCursor, QFont, QIcon

from project_io import create_reel, load_project, get_project_folders, get_reels_in_folder

class ReelCard(QFrame):
    clicked = Signal(str) 
    delete_clicked = Signal(str)

    def __init__(self, project_data, parent=None):
        super().__init__(parent)
        self.project_data = project_data
        self.scomp_path = project_data.get("project_path", "")
        self.init_ui()

    def init_ui(self):
        self.setFixedSize(200, 280)
        self.setStyleSheet("""
            QFrame { background-color: #1e1e2e; border: 1px solid #313244; border-radius: 12px; }
            QFrame:hover { border: 2px solid #89b4fa; background-color: #313244; }
        """)
        shadow = QGraphicsDropShadowEffect(); shadow.setBlurRadius(15); shadow.setColor(Qt.GlobalColor.black); shadow.setOffset(0, 5)
        self.setGraphicsEffect(shadow)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        self.lbl_cover = QLabel()
        self.lbl_cover.setFixedSize(200, 210)
        self.lbl_cover.setStyleSheet("background-color: #11111b; border-top-left-radius: 12px; border-top-right-radius: 12px; border-bottom: none;")
        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        cover_rel = self.project_data.get("cover_img", "")
        p_dir = self.project_data.get("project_dir", "")
        cover_path = os.path.join(p_dir, cover_rel) if p_dir and cover_rel else ""
        
        if cover_path and os.path.exists(cover_path):
            pixmap = QPixmap(cover_path)
            self.lbl_cover.setPixmap(pixmap.scaled(200, 210, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_cover.setText("🎬\n无封面\n(在精修室保存后生成)")
            self.lbl_cover.setStyleSheet("background-color: #11111b; color: #45475a; font-size: 16px; font-weight: bold; border-top-left-radius: 12px; border-top-right-radius: 12px; border-bottom: none;")

        layout.addWidget(self.lbl_cover)

        info_frame = QFrame(); info_frame.setStyleSheet("background: transparent; border: none;")
        info_layout = QVBoxLayout(info_frame); info_layout.setContentsMargins(12, 10, 12, 10); info_layout.setSpacing(4)

        title_row = QHBoxLayout()
        p_name = self.project_data.get("project_name", "未命名Reel")
        lbl_title = QLabel(p_name)
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #cdd6f4;")
        
        btn_del = QPushButton("🗑️")
        btn_del.setFixedSize(24, 24)
        btn_del.setStyleSheet("background: transparent; border: none; color: #f38ba8; font-size: 14px;")
        btn_del.clicked.connect(self._on_del_clicked)

        title_row.addWidget(lbl_title, stretch=1); title_row.addWidget(btn_del)
        info_layout.addLayout(title_row)

        lbl_date = QLabel(self.project_data.get("updated_at", "").split(" ")[0])
        lbl_date.setStyleSheet("font-size: 12px; color: #a6adc8;")
        info_layout.addWidget(lbl_date)

        layout.addWidget(info_frame)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked.emit(self.scomp_path)
        super().mousePressEvent(event)
        
    def _on_del_clicked(self, event):
        self.delete_clicked.emit(self.scomp_path)

class ProjectView(QWidget):
    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.workspace = os.path.join(os.getcwd(), "MyWorkspace")
        if not os.path.exists(self.workspace): os.makedirs(self.workspace)
        self.current_folder = ""
        self.init_ui()
        self.refresh_folders()

    def init_ui(self):
        self.setStyleSheet("QWidget { background-color: #11111b; color: #cdd6f4; font-family: 'Segoe UI', Arial; }")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        header = QHBoxLayout()
        title = QLabel("🎬 Reels 视频工程大厅")
        title.setStyleSheet("font-size: 28px; font-weight: 900; color: #cdd6f4;")
        header.addWidget(title)
        
        self.lbl_current = QLabel("当前加载: 无")
        self.lbl_current.setStyleSheet("color: #a6e3a1; font-size: 14px; font-weight: bold; background: #1e1e2e; padding: 5px 15px; border-radius: 15px; margin-left: 20px;")
        header.addWidget(self.lbl_current)
        header.addStretch()
        main_layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #313244; width: 2px; }")
        
        # 👑 左侧：项目文件夹列表
        left_panel = QFrame()
        left_panel.setStyleSheet("background-color: #181825; border-radius: 10px;")
        left_layout = QVBoxLayout(left_panel)
        
        left_header = QHBoxLayout()
        left_header.addWidget(QLabel("📁 项目列表", styleSheet="font-size: 16px; font-weight: bold; color: #89b4fa;"))
        
        # 👑 新增：左侧操作按钮
        btn_new_folder = QPushButton("➕"); btn_new_folder.setFixedSize(30, 30)
        btn_new_folder.setStyleSheet("background-color: #313244; color: white; border-radius: 15px;")
        btn_new_folder.setToolTip("新建项目"); btn_new_folder.clicked.connect(self.create_new_folder)
        
        btn_rename_folder = QPushButton("✏️"); btn_rename_folder.setFixedSize(30, 30)
        btn_rename_folder.setStyleSheet("background-color: #313244; color: white; border-radius: 15px;")
        btn_rename_folder.setToolTip("重命名选中项目"); btn_rename_folder.clicked.connect(self.rename_current_folder)

        btn_delete_folder = QPushButton("🗑️"); btn_delete_folder.setFixedSize(30, 30)
        btn_delete_folder.setStyleSheet("background-color: #313244; color: #f38ba8; border-radius: 15px;")
        btn_delete_folder.setToolTip("删除选中项目"); btn_delete_folder.clicked.connect(self.delete_current_folder)

        left_header.addWidget(btn_new_folder)
        left_header.addWidget(btn_rename_folder)
        left_header.addWidget(btn_delete_folder)
        left_layout.addLayout(left_header)

        self.folder_list = QListWidget()
        self.folder_list.setStyleSheet("""
            QListWidget { background: transparent; border: none; outline: none; }
            QListWidget::item { padding: 12px; margin: 4px 0; border-radius: 8px; font-size: 14px; color: #a6adc8; font-weight: bold; }
            QListWidget::item:hover { background-color: #313244; }
            QListWidget::item:selected { background-color: #89b4fa; color: #11111b; }
        """)
        self.folder_list.itemClicked.connect(self.on_folder_selected)
        left_layout.addWidget(self.folder_list)
        
        # 👑 右侧：Reels 分页网格
        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: transparent;")
        right_layout = QVBoxLayout(right_panel)
        
        self.lbl_folder_title = QLabel("请在左侧选择一个项目...")
        self.lbl_folder_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #f9e2af; padding-bottom: 10px;")
        right_layout.addWidget(self.lbl_folder_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(25)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self.grid_widget)
        right_layout.addWidget(scroll, stretch=1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([300, 1000])
        main_layout.addWidget(splitter, stretch=1)

    def parent_window(self):
        p = self.parent()
        while p is not None and not hasattr(p, "switch_room"): p = p.parent()
        return p

    def sync_current_project_label(self):
        p_name = self.project_data.get("project_name", "") if isinstance(self.project_data, dict) else ""
        if p_name: self.lbl_current.setText(f"当前加载 Reel: {p_name}")
        else: self.lbl_current.setText("当前加载 Reel: 无")

    def refresh_folders(self, select_name=None):
        self.folder_list.clear()
        folders = get_project_folders(self.workspace)
        for f in folders:
            self.folder_list.addItem(f)
            
        if folders:
            # 尝试选中指定的名称
            if select_name:
                items = self.folder_list.findItems(select_name, Qt.MatchFlag.MatchExactly)
                if items:
                    self.folder_list.setCurrentItem(items[0])
                    self.on_folder_selected(items[0])
                    return
            
            # 否则默认选中第一个
            self.folder_list.setCurrentRow(0)
            self.on_folder_selected(self.folder_list.item(0))

    def create_new_folder(self):
        name, ok = QInputDialog.getText(self, "新建项目", "请输入新项目文件夹的名称：")
        if ok and name.strip():
            safe_name = "".join(c for c in name.strip() if c not in r'\/:*?"<>|')
            path = os.path.join(self.workspace, safe_name)
            if not os.path.exists(path):
                os.makedirs(path)
                self.refresh_folders(select_name=safe_name)
            else:
                QMessageBox.warning(self, "提示", "项目文件夹已存在！")

    # 👑 新增：重命名项目
    def rename_current_folder(self):
        if not self.current_folder: return
        old_name = os.path.basename(self.current_folder)
        new_name, ok = QInputDialog.getText(self, "重命名项目", "请输入新的项目名称：", text=old_name)
        if ok and new_name.strip() and new_name.strip() != old_name:
            safe_name = "".join(c for c in new_name.strip() if c not in r'\/:*?"<>|')
            new_path = os.path.join(self.workspace, safe_name)
            if os.path.exists(new_path):
                QMessageBox.warning(self, "提示", "该项目名称已存在！")
                return
            try:
                os.rename(self.current_folder, new_path)
                
                # 如果正在加载的 Reel 刚好在这个文件夹里，修复它的内部路径映射
                if self.project_data and self.project_data.get("project_dir", "") == self.current_folder:
                    old_scomp = self.project_data.get("project_path")
                    new_scomp = old_scomp.replace(self.current_folder, new_path)
                    if os.path.exists(new_scomp):
                        self.project_data = load_project(new_scomp)
                        self.sync_current_project_to_main()
                        self.sync_current_project_label()

                self.current_folder = new_path
                self.refresh_folders(select_name=safe_name)
            except Exception as e:
                QMessageBox.critical(self, "重命名失败", str(e))

    # 👑 新增：删除项目
    def delete_current_folder(self):
        if not self.current_folder: return
        folder_name = os.path.basename(self.current_folder)
        reply = QMessageBox.warning(self, '⚠️ 警告', f'确认彻底删除项目【{folder_name}】及其所有内容吗？\n此操作不可逆！', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                shutil.rmtree(self.current_folder)
                
                # 如果正在加载的 Reel 被删了，清理大盘数据
                if self.project_data and self.project_data.get("project_dir", "") == self.current_folder:
                    self.project_data = {}
                    self.sync_current_project_label()
                    self.sync_current_project_to_main()
                
                self.current_folder = ""
                self.lbl_folder_title.setText("请在左侧选择一个项目...")
                self.refresh_folders()
            except Exception as e:
                QMessageBox.critical(self, "删除失败", str(e))

    def on_folder_selected(self, item):
        if not item: return
        self.current_folder = os.path.join(self.workspace, item.text())
        self.lbl_folder_title.setText(f"📁 {item.text()} 下的 Reels")
        self.refresh_reels_grid()

    def refresh_reels_grid(self):
        for i in reversed(range(self.grid_layout.count())): 
            widget = self.grid_layout.itemAt(i).widget()
            if widget: widget.deleteLater()

        if not self.current_folder or not os.path.exists(self.current_folder): 
            return
        
        reels_paths = get_reels_in_folder(self.current_folder)
        col_count = 5; row, col = 0, 0

        # 新建 Reel 卡片
        new_card = QFrame()
        new_card.setFixedSize(200, 280)
        new_card.setStyleSheet("QFrame { background-color: transparent; border: 2px dashed #45475a; border-radius: 12px; } QFrame:hover { border-color: #a6e3a1; background-color: #1e1e2e; }")
        new_card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        new_layout = QVBoxLayout(new_card)
        new_lbl = QLabel("➕\n新建 Reel")
        new_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        new_lbl.setStyleSheet("color: #a6e3a1; font-size: 20px; font-weight: bold; border: none;")
        new_layout.addWidget(new_lbl)
        new_card.mousePressEvent = lambda e: self.create_new_reel() if e.button() == Qt.MouseButton.LeftButton else None
        
        self.grid_layout.addWidget(new_card, row, col)
        col += 1

        for path in reels_paths:
            try:
                p_data = load_project(path)
                card = ReelCard(p_data)
                card.clicked.connect(self.load_and_enter_project)
                card.delete_clicked.connect(self.delete_reel)
                
                self.grid_layout.addWidget(card, row, col)
                col += 1
                if col >= col_count: col = 0; row += 1
            except Exception: pass

    def create_new_reel(self):
        if not self.current_folder: return
        name, ok = QInputDialog.getText(self, "新建 Reel", "给你的新 Reel 起个名字：")
        if ok and name.strip():
            try:
                self.project_data = create_reel(self.current_folder, name.strip(), "edit_room")
                self.sync_current_project_to_main()
                self.refresh_reels_grid()
                self.sync_current_project_label()
                parent = self.parent_window()
                if parent: parent.switch_room(1)
            except Exception as e:
                QMessageBox.critical(self, "创建失败", str(e))

    def load_and_enter_project(self, path):
        try:
            self.project_data = load_project(path)
            self.sync_current_project_to_main()
            self.sync_current_project_label()
            parent = self.parent_window()
            if parent: parent.switch_room(1) 
        except Exception as e:
            QMessageBox.critical(self, "载入失败", str(e))

    def delete_reel(self, path):
        reply = QMessageBox.warning(self, '⚠️ 警告', '确认删除该 Reel 吗？', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                os.remove(path)
                cover_path = path.replace(".scomp", "_cover.jpg")
                if os.path.exists(cover_path): os.remove(cover_path)
                self.refresh_reels_grid()
                
                # 如果删除的刚好是当前加载的，则清空引用
                if self.project_data.get("project_path") == path:
                    self.project_data = {}
                    self.sync_current_project_label()
                    self.sync_current_project_to_main()
            except Exception as e:
                QMessageBox.critical(self, "删除失败", str(e))

    def sync_current_project_to_main(self):
        parent = self.parent_window()
        if not parent: return
        parent.project = self.project_data
        if hasattr(parent, "reload_rooms_from_project"):
            parent.reload_rooms_from_project()