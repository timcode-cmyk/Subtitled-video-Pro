# ==========================================
# 文件名: room2_viral.py (功能预约占位版)
# ==========================================
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt

class ViralQuotesView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        # 使用深色背景，保持视觉统一
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 提示卡片
        card = QFrame()
        card.setFixedSize(600, 400)
        card.setStyleSheet("""
            QFrame {
                background-color: #181825;
                border: 2px solid #313244;
                border-radius: 20px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(20)

        # 炫酷的图标或占位字
        icon_label = QLabel("🚀")
        icon_label.setStyleSheet("font-size: 80px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        title_label = QLabel("滚动视差引擎 - 正在闭门打磨中")
        title_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #f59e0b;")
        
        desc_label = QLabel(
            "为了提供更极致的体验，我们正在将「滚动字幕」与「逐字精修」进行底层合并。\n\n"
            "✨ 下个版本您将获得：\n"
            "1. 标题与正文双轨分层编辑\n"
            "2. 动画关键帧与滚动速度自定义控制\n"
            "3. 工业级多层渐变蒙版与遮罩透明层\n\n"
            "版本进化中，敬请期待..."
        )
        desc_label.setStyleSheet("font-size: 16px; color: #a6adc8; line-height: 1.6;")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card_layout.addStretch()
        card_layout.addWidget(icon_label)
        card_layout.addWidget(title_label)
        card_layout.addWidget(desc_label)
        card_layout.addStretch()

        main_layout.addWidget(card)

    # 预留空方法防止 main.py 调用时报错
    def refresh_presets(self): pass