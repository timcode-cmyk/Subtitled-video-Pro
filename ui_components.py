# ==========================================
# 文件名: ui_components.py (无缝融合 + 宽度拉伸 + 羽化蒙版滚动)
# ==========================================
import math
import subprocess
import os
import re
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt, QObject, Slot

from core import get_ffmpeg_cmd

FAITH_WORDS = {"god", "jesus", "amen", "lord", "christ", "holy", "bible"}

def hex_to_rgb(hex_color):
    hex_color = str(hex_color).lstrip('#')
    if len(hex_color) == 6:
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return (255, 255, 255)

def get_exact_duration(file_path):
    if not file_path or not os.path.exists(file_path): return 0.0
    try:
        cmd = [get_ffmpeg_cmd(), '-i', file_path]
        flags = 0x08000000 if os.name == 'nt' else 0
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', timeout=5, creationflags=flags)
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
        return 0.0
    except:
        return 0.0

def get_video_dimensions(file_path):
    if not file_path or not os.path.exists(file_path): return 1080, 1920
    try:
        cmd = [get_ffmpeg_cmd(), '-i', file_path]
        flags = 0x08000000 if os.name == 'nt' else 0
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', timeout=5, creationflags=flags)
        match = re.search(r"Video:.*?, (\d+)x(\d+)", result.stderr)
        if match: return int(match.group(1)), int(match.group(2))
        return 1080, 1920
    except:
        return 1080, 1920

class AspectRatioContainer(QWidget):
    def __init__(self, child_widget, parent=None):
        super().__init__(parent)
        self.child_widget = child_widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(child_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        self.ratio = 1080 / 1920

    def set_ratio(self, w, h):
        if h == 0: return
        self.ratio = w / h
        self.updateGeometry()
        if self.parentWidget():
            self.parentWidget().update()

    def resizeEvent(self, event):
        w = event.size().width()
        h = event.size().height()
        if h > 0 and (w / h) > self.ratio:
            new_w = int(h * self.ratio)
            self.child_widget.setFixedSize(new_w, h)
        else:
            new_h = int(w / self.ratio) if self.ratio > 0 else h
            self.child_widget.setFixedSize(w, new_h)
        super().resizeEvent(event)

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

    @Slot(int)
    def notify_selected(self, idx): 
        self.controller.current_selected_idx = idx
        self.controller.switch_inspector("sub")
        
    @Slot(int, str)
    def update_text_from_screen(self, idx, new_text):
        pass
            
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




def render_subtitle_html(sub, current_time, proj_w=1080):
    def vw(val):
        return f"{float(val) * 100 / proj_w:.4f}vw"

    style = sub.get("style", sub)
    c_txt = style.get("color_txt", "#FFFFFF")
    c_hl = style.get("color_hl", "#FFFFFF")
    f_fam = style.get("font", "Arial")

    size = int(style.get("size", 100))
    bg_mode = style.get("bg_mode", "none")
    bg_col = style.get("bg_color", "#000000")
    bg_a = style.get("bg_alpha", 80) / 100.0
    rad = style.get("bg_radius", 15)
    pad = style.get("bg_padding", 20)
    pad_left = style.get("bg_pad_left", pad)
    pad_right = style.get("bg_pad_right", pad)
    pad_top = style.get("bg_pad_top", pad / 2.5)
    pad_bottom = style.get("bg_pad_bottom", pad / 2.5)

    hl_bg_col = style.get("hl_bg_color", "#FF0050")
    hl_bg_a = style.get("hl_bg_alpha", 100) / 100.0
    hl_rad = style.get("hl_bg_radius", 8)
    hl_pad = style.get("hl_bg_padding", 8)
    hl_pad_left = style.get("hl_pad_left", hl_pad)
    hl_pad_right = style.get("hl_pad_right", hl_pad)
    hl_pad_top = style.get("hl_pad_top", max(0, hl_pad / 3))
    hl_pad_bottom = style.get("hl_pad_bottom", max(0, hl_pad / 3))

    lh = style.get("line_height", 1.1)
    rot = style.get("rotation", 0)

    stroke_w = style.get("stroke_width", 4)
    stroke_c = style.get("stroke_color", "#000000")
    stroke_o_w = style.get("stroke_o_width", 0)
    stroke_o_c = style.get("stroke_o_color", "#000000")
    sh_x = style.get("shadow_x", 5)
    sh_y = style.get("shadow_y", 5)
    sh_blur = style.get("shadow_blur", 0)
    sh_c = style.get("shadow_color", "#000000")
    sh_a = style.get("shadow_alpha", 100) / 100.0

    trans = style.get("text_transform", "capitalize")
    align = style.get("text_align", "center")
    letter_spacing = style.get("letter_spacing", 0)
    word_spacing = style.get("word_spacing", 0)
    layout_mode = style.get("layout_mode", "standard")
    layout_variant = style.get("layout_variant", "auto")
    emphasis_scale = max(100, int(style.get("emphasis_scale", 145)))
    use_hl = style.get("use_hl", True)
    hl_glow = style.get("hl_glow", False)
    glow_size = int(style.get("glow_size", 20))

    anim_type = style.get("anim_type", "pop")
    pop_speed = float(style.get("pop_speed", 0.2))
    pop_bounce = max(100, int(style.get("pop_bounce", 140)))
    inactive_alpha = int(style.get("inactive_alpha", 100)) / 100.0

    box_width = float(style.get("box_width", 0))
    mask_en = style.get("mask_en", False)
    mask_top = style.get("mask_top", 20)
    mask_bot = style.get("mask_bottom", 20)

    size_vw = vw(size)
    rad_vw = vw(rad)
    pad_y = vw(pad / 2.5)
    pad_x = vw(pad)
    pad_top_vw = vw(pad_top)
    pad_right_vw = vw(pad_right)
    pad_bottom_vw = vw(pad_bottom)
    pad_left_vw = vw(pad_left)
    ls_vw = vw(letter_spacing)
    ws_vw = vw(word_spacing)

    hl_rad_vw = vw(hl_rad)
    hl_pad_y = vw(max(0, hl_pad / 3))
    hl_pad_x = vw(hl_pad)
    hl_pad_top_vw = vw(hl_pad_top)
    hl_pad_right_vw = vw(hl_pad_right)
    hl_pad_bottom_vw = vw(hl_pad_bottom)
    hl_pad_left_vw = vw(hl_pad_left)

    r, g, b = hex_to_rgb(bg_col)
    hl_r, hl_g, hl_b = hex_to_rgb(hl_bg_col)

    words = sub.get("words", [])
    if not words:
        words = [{"text": sub.get("text", ""), "start": sub.get("start", 0), "end": sub.get("end", 1)}]

    clip_start = float(sub.get("start", 0))
    clip_end = float(sub.get("end", 1))
    clip_dur = max(0.1, clip_end - clip_start)
    clip_progress = max(0.0, min(1.0, (current_time - clip_start) / clip_dur))
    whole_sub_progress = clip_progress * 100 if bg_mode == "sweep" else 0

    content_indices = [i for i, ww in enumerate(words) if ww.get("text", "").replace("\n", "").strip()]
    emphasis_idx = set()
    small_idx = set()

    def _token_score(token):
        t = re.sub(r"[^A-Za-z0-9一-鿿]", "", token or "")
        if not t:
            return -999
        stop = {
            "i", "me", "my", "you", "your", "we", "our", "to", "the", "a", "an", "and", "or",
            "but", "if", "of", "in", "on", "for", "is", "am", "are", "be", "with", "that",
            "this", "it", "he", "she", "they", "them", "him", "her", "so"
        }
        lower = t.lower()
        score = len(t) * 1.4
        if lower in stop:
            score -= 3.2
        if len(t) <= 2:
            score -= 1.6
        if t.isupper() and len(t) > 1:
            score += 1.2
        if lower in FAITH_WORDS:
            score += 1.5
        return score

    if layout_mode in ("contrast", "triple") and content_indices:
        variant = layout_variant
        if variant == "auto":
            m = len(content_indices) % 3
            variant = "small-big-small" if m == 1 else "big-small-mix" if m == 2 else "mix-big-small"

        ranked = sorted(
            content_indices,
            key=lambda i: (_token_score(words[i].get("text", "")), -abs(i - len(words) / 2)),
            reverse=True,
        )

        if layout_mode == "contrast":
            focus_count = 1 if len(content_indices) <= 4 else 2
            emphasis_idx.update(sorted(ranked[:focus_count]))
            if not emphasis_idx:
                emphasis_idx.add(content_indices[max(0, len(content_indices) // 2)])
            small_idx.update([i for i in content_indices if i not in emphasis_idx])
        else:
            if variant == "small-big-small":
                emphasis_idx.update(ranked[:1] or [content_indices[min(1, len(content_indices) - 1)]])
            elif variant == "big-small-mix":
                emphasis_idx.update(ranked[:2] if len(content_indices) > 4 else ranked[:1])
            else:
                focus = ranked[:1] or [content_indices[min(len(content_indices) // 2, len(content_indices) - 1)]]
                emphasis_idx.update(focus)
                if len(content_indices) > 5:
                    emphasis_idx.add(content_indices[0])
            small_idx.update([i for i in content_indices if i not in emphasis_idx])

    html_words_fg = []
    html_words_bg = []

    for idx, w in enumerate(words):
        raw_txt = w.get("text", "")
        has_newline = "\n" in raw_txt
        clean_txt = raw_txt.replace("\n", "").strip()

        if not clean_txt:
            if has_newline:
                html_words_fg.append("<br>")
                if bg_mode in ("tape", "block"):
                    html_words_bg.append("<br>")
            continue

        if has_newline and idx > 0:
            html_words_fg.append("<br>")
            if bg_mode in ("tape", "block"):
                html_words_bg.append("<br>")

        if trans == "uppercase":
            clean_txt = clean_txt.upper()
        elif trans == "lowercase":
            clean_txt = clean_txt.lower()
        elif trans == "capitalize":
            clean_txt = " ".join(word[0].upper() + word[1:] if word else "" for word in clean_txt.split(" "))
        else:
            sub_words = clean_txt.split(" ")
            for s_idx, sub_w in enumerate(sub_words):
                pure_w = re.sub(r"[^a-zA-Z]", "", sub_w).lower()
                if pure_w in FAITH_WORDS:
                    sub_words[s_idx] = sub_w.replace(re.sub(r"[^a-zA-Z]", "", sub_w), pure_w.capitalize())
            clean_txt = " ".join(sub_words)

        w_start = float(w.get("start", 0))
        w_end = float(w.get("end", w_start + 0.5))

        is_active = use_hl and current_time >= w_start
        is_current = use_hl and (w_start <= current_time <= w_end)

        t = current_time - w_start
        current_scale = 1.0
        current_opacity = inactive_alpha
        current_translate_em = 0.0

        if is_active:
            current_opacity = 1.0
            if anim_type == "pop" and t >= 0:
                if t <= pop_speed and pop_speed > 0:
                    p = max(0.0, min(1.0, t / pop_speed))
                    overshoot = 0.12 + max(0, pop_bounce - 100) / 100.0 * 0.10
                    damp = math.sin(p * math.pi)
                    current_scale = 1.0 + (0.25 + overshoot) * damp
            elif anim_type == "fade" and t >= 0:
                if t <= pop_speed and pop_speed > 0:
                    current_opacity = inactive_alpha + (1.0 - inactive_alpha) * (t / pop_speed)

        shadows = []
        if stroke_o_w > 0:
            total_w = stroke_w + stroke_o_w
            for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
                sx = total_w * math.cos(math.radians(angle))
                sy = total_w * math.sin(math.radians(angle))
                shadows.append(f"{vw(sx)} {vw(sy)} 0 {stroke_o_c}")
        if sh_x != 0 or sh_y != 0 or sh_blur != 0:
            sr, sg, sb = hex_to_rgb(sh_c)
            shadows.append(f"{vw(sh_x)} {vw(sh_y)} {vw(sh_blur)} rgba({sr}, {sg}, {sb}, {sh_a})")
        if is_current and hl_glow:
            shadows.extend([f"0 0 {vw(glow_size)} {c_hl}", f"0 0 {vw(glow_size*1.5)} {c_hl}", f"0 0 {vw(glow_size*2)} {c_hl}"])

        text_shadow_css = f"text-shadow: {', '.join(shadows)};" if shadows else "text-shadow: none;"
        stroke_css = f"-webkit-text-stroke: {vw(stroke_w)} {stroke_c};" if stroke_w > 0 else ""

        layout_font_scale = 1.0
        per_word_translate = 0.0
        word_margin_right = ws_vw
        if layout_mode in ("contrast", "triple"):
            if idx in emphasis_idx:
                layout_font_scale = emphasis_scale / 100.0
                per_word_translate = -0.06 if layout_mode == "contrast" else -0.04
                word_margin_right = vw(max(0, word_spacing * 0.55 + 1.4))
            elif idx in small_idx:
                layout_font_scale = 0.74 if layout_mode == "contrast" else 0.80
                per_word_translate = 0.03 if layout_mode == "contrast" else 0.02
                word_margin_right = vw(max(0, word_spacing * 0.35 + 0.6))
            else:
                word_margin_right = vw(max(0, word_spacing * 0.45 + 1.0))

        current_translate_em += per_word_translate

        word_base = (
            f"font-size: {layout_font_scale:.3f}em; "
            f"transform: translateY({current_translate_em:.3f}em) scale({current_scale:.3f}); "
            f"transform-origin: center center; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); "
            f"margin-right: {word_margin_right};"
        )

        word_css_fg = f"display: inline-block; color: {c_hl if is_current else c_txt}; opacity: {current_opacity:.3f}; {text_shadow_css} {stroke_css} {word_base}"
        word_css_bg = f"display: inline-block; color: transparent; -webkit-text-fill-color: transparent; text-shadow: none; -webkit-text-stroke: transparent; opacity: {current_opacity:.3f}; {word_base}"

        if bg_mode == "tape":
            if is_current and hl_bg_a > 0:
                hl_css = f" background-color: rgba({hl_r}, {hl_g}, {hl_b}, {hl_bg_a}); border-radius: {hl_rad_vw}; padding: {hl_pad_top_vw} {hl_pad_right_vw} {hl_pad_bottom_vw} {hl_pad_left_vw}; margin: 0 {vw(2)};"
                word_css_fg += hl_css
                word_css_bg += f" background-color: transparent; border-radius: {hl_rad_vw}; padding: {hl_pad_top_vw} {hl_pad_right_vw} {hl_pad_bottom_vw} {hl_pad_left_vw}; margin: 0 {vw(2)};"
            else:
                word_css_fg += f" padding: {hl_pad_y} {vw(1)};"
                word_css_bg += f" padding: {hl_pad_y} {vw(1)};"
        elif bg_mode == "block" and is_current and hl_bg_a > 0:
            word_css_fg += f" background-color: rgba({hl_r}, {hl_g}, {hl_b}, {hl_bg_a}); border-radius: {hl_rad_vw}; padding: {hl_pad_top_vw} {hl_pad_right_vw} {hl_pad_bottom_vw} {hl_pad_left_vw}; margin: -{hl_pad_top_vw} -{vw(hl_pad/4)};"

        html_words_fg.append(f"<span style='{word_css_fg}'>{clean_txt}</span>")
        html_words_bg.append(f"<span style='{word_css_bg}'>{clean_txt}</span>")

        if idx < len(words) - 1:
            next_raw = words[idx + 1].get("text", "")
            if "\n" not in next_raw:
                spacer = "<span style='display:inline-block; width:0.14em;'></span>" if layout_mode in ("contrast", "triple") else " "
                html_words_fg.append(spacer)
                if bg_mode in ("tape", "block"):
                    html_words_bg.append(spacer if layout_mode in ("contrast", "triple") else " ")

    inner_html_fg = "".join(html_words_fg)
    inner_html_bg = "".join(html_words_bg)

    inner_transform = ""
    if anim_type == "roll_up":
        y_offset = (1.0 - clip_progress * 2) * 50
        inner_transform = f"transform: translateY({y_offset}vh);"

    base_wrapper_css = f"""
        font-family: '{f_fam}', sans-serif;
        font-size: {size_vw};
        font-weight: bold;
        letter-spacing: {ls_vw};
        word-spacing: {('0vw' if layout_mode in ('contrast', 'triple') else ws_vw)};
        text-transform: {trans};
        box-sizing: border-box;
    """

    j_map = {"center": "center", "left": "start", "right": "end", "justify": "center"}
    align_item = j_map.get(align, "center")
    width_css = f"max-width: {vw(box_width)}; width: fit-content;" if box_width > 0 else "width: max-content; max-width: 100%;"

    mask_css = ""
    if mask_en:
        mask_css = f"-webkit-mask-image: linear-gradient(to bottom, transparent 0%, black {mask_top}%, black {100-mask_bot}%, transparent 100%); mask-image: linear-gradient(to bottom, transparent 0%, black {mask_top}%, black {100-mask_bot}%, transparent 100%);"

    outer_box_style = f"{width_css} margin: 0 auto; outline: none; text-align: {align}; position: relative; {mask_css} transform: rotate({rot}deg); overflow: visible; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);"

    if bg_mode == "tape":
        bg_layer_css = base_wrapper_css + f"""
            display: inline;
            background-color: rgb({r}, {g}, {b});
            border-radius: {rad_vw};
            padding: {pad_y} {pad_x};
            -webkit-box-decoration-break: clone;
            box-decoration-break: clone;
            line-height: {max(0.6, float(lh))};
        """
        fg_layer_css = base_wrapper_css + f"""
            display: inline;
            line-height: {max(0.6, float(lh))};
        """
        final_html = f"""
        <div class='sub-box' style='{outer_box_style}'>
            <div style="{inner_transform} width: 100%; display: grid; grid-template-columns: 1fr; grid-template-rows: 1fr; justify-items: {align_item}; align-items: center; text-align: {align};">
                <div style="grid-area: 1/1; opacity: {bg_a}; z-index: 1; width: 100%;"><span style="{bg_layer_css}">{inner_html_bg}</span></div>
                <div style="grid-area: 1/1; z-index: 2; width: 100%;"><span style="{fg_layer_css}">{inner_html_fg}</span></div>
            </div>
        </div>
        """
    elif bg_mode == "block":
        wrapper_css = base_wrapper_css + f"""
            display: inline-block;
            background-color: rgba({r}, {g}, {b}, {bg_a});
            border-radius: {rad_vw};
            padding: {pad_y} {pad_x};
            text-align: {align};
            line-height: {max(0.8, float(lh))};
            width: 100%;
        """
        final_html = f"""
        <div class='sub-box' style='{outer_box_style}'>
            <div style="{inner_transform} width: 100%;"><div style="{wrapper_css}">{inner_html_fg}</div></div>
        </div>
        """
    elif bg_mode == "full_frame":
        frame_wrap_css = base_wrapper_css + f"""
            display: inline-block;
            line-height: {max(0.8, float(lh))};
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
            background-color: rgba({r}, {g}, {b}, {bg_a});
            border-radius: {rad_vw};
            padding: {pad_top_vw} {pad_right_vw} {pad_bottom_vw} {pad_left_vw};
            text-align: {align};
            max-width: 100%;
            box-sizing: border-box;
        """
        final_html = f"""
        <div class='sub-box' style='{outer_box_style}'>
            <div style="{inner_transform} width: 100%; display:flex; justify-content:{align_item}; text-align:{align};">
                <div style="{frame_wrap_css}">{inner_html_fg}</div>
            </div>
        </div>
        """
    elif bg_mode == "sweep":
        bg_layer_css = base_wrapper_css + f"""
            display: inline;
            background-color: rgb({r}, {g}, {b});
            border-radius: {rad_vw};
            padding: {pad_y} {pad_x};
            -webkit-box-decoration-break: clone;
            box-decoration-break: clone;
            line-height: {max(0.8, float(lh))};
        """
        fg_layer_css = base_wrapper_css + f"""
            display: inline;
            background-color: transparent;
            border-radius: {rad_vw};
            padding: {pad_y} {pad_x};
            -webkit-box-decoration-break: clone;
            box-decoration-break: clone;
            line-height: {max(0.8, float(lh))};
            background: linear-gradient(to right, {hl_bg_col} {whole_sub_progress}%, {c_txt} {whole_sub_progress}%);
            -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; text-fill-color: transparent;
        """
        final_html = f"""
        <div class='sub-box' style='{outer_box_style}'>
            <div style="{inner_transform} width: 100%; display: grid; grid-template-columns: 1fr; grid-template-rows: 1fr; justify-items: {align_item}; align-items: center; text-align: {align};">
                <div style="grid-area: 1/1; opacity: {bg_a}; z-index: 1; width: 100%;"><span style="{bg_layer_css}">{inner_html_bg if inner_html_bg else inner_html_fg}</span></div>
                <div style="grid-area: 1/1; z-index: 2; width: 100%;"><span style="{fg_layer_css}">{inner_html_fg}</span></div>
            </div>
        </div>
        """
    else:
        wrapper_css = base_wrapper_css + f"""
            display: inline-block;
            text-align: {align};
            line-height: {max(0.8, float(lh))};
            width: 100%;
        """
        final_html = f"""
        <div class='sub-box' style='{outer_box_style}'>
            <div style="{inner_transform} width: 100%;"><div style="{wrapper_css}">{inner_html_fg}</div></div>
        </div>
        """

    return final_html

