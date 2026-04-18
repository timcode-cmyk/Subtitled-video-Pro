# ==========================================
# 文件名: room_settings.py (账号池与负载均衡全开版)
# ==========================================
import os
import json
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, 
                             QTextEdit, QPushButton, QMessageBox, QFrame)

CONFIG_FILE = os.path.join(os.getcwd(), "settings.json")

class SettingsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_config()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 👑 顶部标题
        title = QLabel("⚙️ 全局设置与引擎管控 (Global Settings)")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        # 👑 账号池大框架
        pool_frame = QFrame()
        pool_frame.setStyleSheet("background-color: #181825; border-radius: 10px; border: 1px solid #313244;")
        pool_layout = QVBoxLayout(pool_frame)
        pool_layout.setContentsMargins(25, 25, 25, 25)
        pool_layout.setSpacing(15)

        # 提示信息
        lbl_pool_title = QLabel("🤖 Cloudflare Whisper AI 账号池 (支持自动负载均衡与故障轮询)")
        lbl_pool_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa; border: none;")
        pool_layout.addWidget(lbl_pool_title)

        lbl_desc = QLabel("为了突破单账号免费额度与并发限制，请在下方【批量填入】您的云端账号矩阵。\n"
                          "👉 格式要求：每行填写一个账号，Account ID 和 API Token 之间用【英文逗号】或【空格】隔开。\n"
                          "👉 底层引擎在打轴时，遇到请求上限或报错会瞬间无缝切换下一个账号！完全不卡顿！")
        lbl_desc.setStyleSheet("color: #a6adc8; line-height: 1.5; font-size: 13px; border: none;")
        pool_layout.addWidget(lbl_desc)

        # 多行输入文本框
        self.txt_accounts = QTextEdit()
        self.txt_accounts.setPlaceholderText("粘贴您的账号阵列，例如:\nf48b2db71fc565c2abfc..., abcdefg1234567890...\n1234567890abcdef..., xyz0987654321...")
        self.txt_accounts.setStyleSheet("""
            QTextEdit {
                background-color: #11111b; 
                color: #a6e3a1; 
                font-family: Consolas; 
                font-size: 14px; 
                border: 1px solid #45475a; 
                border-radius: 6px; 
                padding: 10px;
            }
        """)
        pool_layout.addWidget(self.txt_accounts, stretch=1)

        # 保存按钮
        btn_save = QPushButton("💾 保存全局账号阵列")
        btn_save.setFixedHeight(45)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b; 
                color: #11111b; 
                font-size: 16px; 
                font-weight: bold; 
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #d97706;
            }
        """)
        btn_save.clicked.connect(self.save_config)
        pool_layout.addWidget(btn_save)

        layout.addWidget(pool_frame, stretch=1)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    accounts = config.get("cf_accounts", [])
                    if accounts:
                        # 将 JSON 里的账号还原为多行文本展示
                        lines = [f"{acc.get('id', '')},{acc.get('token', '')}" for acc in accounts]
                        self.txt_accounts.setPlainText("\n".join(lines))
            except: pass

    def save_config(self):
        raw_text = self.txt_accounts.toPlainText().strip()
        lines = raw_text.split('\n')
        
        valid_accounts = []
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # 智能兼容：把中文逗号替换成英文逗号
            line = line.replace('，', ',')
            
            # 智能拆分：逗号或空格隔开的都能识别
            if ',' in line:
                parts = line.split(',', 1)
            else:
                parts = line.split(maxsplit=1)
                
            if len(parts) == 2:
                acc_id = parts[0].strip()
                acc_token = parts[1].strip()
                if acc_id and acc_token:
                    valid_accounts.append({"id": acc_id, "token": acc_token})

        if not valid_accounts and raw_text:
            QMessageBox.warning(self, "格式错误", "没有解析到有效的账号！\n请确保 Account ID 和 Token 之间有逗号或空格分隔。")
            return

        config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except: pass
                
        # 写入 cf_accounts 数组，完美对接房间 1 和 2 的负载均衡
        config["cf_accounts"] = valid_accounts
        
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "保存成功", f"✅ 成功入库 {len(valid_accounts)} 个 AI 账号！\n底层引擎现已火力全开，无缝负载均衡机制已激活！")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存配置文件：\n{str(e)}")