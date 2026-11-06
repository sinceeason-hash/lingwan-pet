"""桌宠内置窗口：更换形象、图片透明化工作台、文案编辑器。

由 pet.py 按需调用；PyInstaller 打包时随 import 自动收录（含 pet_assets / PIL）。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtCore import QPoint, QPointF, QRect, QStandardPaths, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSlider, QSpinBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget, QDialog,
)

import pet_assets

PREVIEW_MAX = 520          # 预览区最长边（显示像素）
UNDO_LIMIT = 8


# ---------------------------------------------------------------- 工具函数

def pil_to_pixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, img.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


def checkerboard_pil(w: int, h: int, cell: int = 14) -> Image.Image:
    board = Image.new("RGB", (w, h), "#ffffff")
    d = ImageDraw.Draw(board)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if (x // cell + y // cell) % 2:
                d.rectangle((x, y, x + cell - 1, y + cell - 1), fill="#d8dde6")
    return board


def preview_image(img: Image.Image) -> Image.Image:
    """棋盘底 + 缩放到预览尺寸。"""
    fit = img.copy()
    fit.thumbnail((PREVIEW_MAX, PREVIEW_MAX), Image.Resampling.LANCZOS)
    board = checkerboard_pil(fit.width, fit.height)
    board.paste(fit, (0, 0), fit)
    return board


def pick_image(parent=None):
    path, _ = QFileDialog.getOpenFileName(
        parent, "选择图片（建议透明 PNG 或纯色背景图）", "",
        "图片 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)")
    return path or None


# ---------------------------------------------------------------- 更换形象

class SwapDialog(QDialog):
    """两步：选图 → 应用。透明 PNG 直接用，普通图自动去背景。"""

    def __init__(self, pet):
        super().__init__(pet)
        self.pet = pet
        self.setWindowTitle("更换形象 · 凌丸")
        self.setMinimumWidth(560)
        self.source = None       # 原图
        self.result = None       # 处理结果
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        title = QLabel("更换桌宠形象")
        title.setFont(QFont("Microsoft YaHei UI", 15, QFont.Weight.Bold))
        layout.addWidget(title)
        tip = QLabel("第一步选图片：透明背景 PNG 直接使用；普通照片自动去除纯色/渐变背景。\n"
                     "背景复杂时请先用「图片透明化工具」擦干净，再来这里选擦好的 PNG。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#8a7f99;font-size:12px;")
        layout.addWidget(tip)

        row = QHBoxLayout()
        self.pick_btn = QPushButton("① 选择图片")
        self.pick_btn.clicked.connect(self.pick)
        row.addWidget(self.pick_btn)
        self.tol_label = QLabel("容差 30")
        row.addWidget(self.tol_label)
        self.tol = QSlider(Qt.Orientation.Horizontal)
        self.tol.setRange(0, 120)
        self.tol.setValue(30)
        self.tol.valueChanged.connect(lambda v: self.tol_label.setText(f"容差 {v}"))
        row.addWidget(self.tol, 1)
        layout.addLayout(row)

        self.preview = QLabel("尚未选择图片")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(520, 380)
        self.preview.setStyleSheet("background:#f2eef8;border-radius:12px;color:#9a8fb0;")
        layout.addWidget(self.preview, 1)

        btns = QHBoxLayout()
        self.apply_btn = QPushButton("② 应用到桌宠")
        self.apply_btn.setObjectName("send")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply)
        btns.addWidget(self.apply_btn)
        close = QPushButton("关闭")
        close.clicked.connect(self.close)
        btns.addWidget(close)
        layout.addLayout(btns)

    def pick(self):
        path = pick_image(self)
        if not path:
            return
        try:
            src = pet_assets.load_source(path)
        except Exception as e:
            self.preview.setText(f"图片读取失败：{e}")
            return
        self.source = src
        if pet_assets.has_real_alpha(src):
            self.result = src
            note = "检测到透明背景，直接使用。"
        else:
            self.result = pet_assets.smooth_alpha(pet_assets.remove_background(src, self.tol.value()))
            note = "已自动去背景（容差可重选后再点一次）。"
        if pet_assets.opaque_ratio(self.result) < 0.02:
            self.result = None
            self.preview.setText("去背景后主体几乎为空：这张图背景不是纯色，\n请改用「图片透明化工具」手动擦图后再来。")
            self.apply_btn.setEnabled(False)
            return
        self.preview.setPixmap(pil_to_pixmap(preview_image(self.result)).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        self.status = note
        self.setWindowTitle(f"更换形象 · {note}")
        self.apply_btn.setEnabled(True)

    def apply(self):
        if not self.result:
            return
        try:
            pet_assets.apply_character(self.result, self.pet.assets_dir)
        except Exception as e:
            self.preview.setText(f"应用失败：{e}")
            return
        self.pet.reload_character()
        self.pet.say("新形象上线！", 2600)
        self.close()


# ---------------------------------------------------------------- 图片透明化工作台

class CutoutStudio(QDialog):
    """打开图片 → 容差自动去背景 → 橡皮擦手动修边 → 保存/应用。"""

    def __init__(self, pet):
        super().__init__(pet)
        self.pet = pet
        self.setWindowTitle("图片透明化工具 · 凌丸")
        self.resize(760, 640)
        self.original = None   # 最初载入的图
        self.img = None        # 当前工作图（RGBA，全分辨率）
        self.undo_stack = []
        self.stroke_start = None
        self.last_img_pos = None
        self.restore_mode = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)

        title = QLabel("把图片修成透明背景，供桌宠使用")
        title.setFont(QFont("Microsoft YaHei UI", 14, QFont.Weight.Bold))
        layout.addWidget(title)
        tip = QLabel("流程：打开图片 → 调容差点「自动去背景」→ 在图上按住左键擦除残留 → 右键可撤销上一步 → 保存或直接应用。\n"
                     "提示：纯色背景效果最好；复杂背景耐心多擦几下，画笔大小可用滑杆调。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#8a7f99;font-size:12px;")
        layout.addWidget(tip)

        bar = QHBoxLayout()
        open_btn = QPushButton("打开图片")
        open_btn.clicked.connect(self.open_image)
        bar.addWidget(open_btn)
        self.tol_label = QLabel("容差 30")
        bar.addWidget(self.tol_label)
        self.tol = QSlider(Qt.Orientation.Horizontal)
        self.tol.setRange(0, 120)
        self.tol.setValue(30)
        self.tol.valueChanged.connect(lambda v: self.tol_label.setText(f"容差 {v}"))
        bar.addWidget(self.tol, 1)
        auto_btn = QPushButton("自动去背景")
        auto_btn.clicked.connect(self.auto_remove)
        bar.addWidget(auto_btn)
        layout.addLayout(bar)

        bar2 = QHBoxLayout()
        bar2.addWidget(QLabel("画笔大小"))
        self.brush = QSlider(Qt.Orientation.Horizontal)
        self.brush.setRange(4, 80)
        self.brush.setValue(26)
        bar2.addWidget(self.brush, 1)
        self.undo_btn = QPushButton("撤销 (Ctrl+Z)")
        self.undo_btn.clicked.connect(self.undo)
        bar2.addWidget(self.undo_btn)
        reset_btn = QPushButton("重置")
        reset_btn.clicked.connect(self.reset)
        bar2.addWidget(reset_btn)
        layout.addLayout(bar2)

        self.canvas = QLabel("先打开一张图片")
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setMinimumSize(640, 360)
        self.canvas.setStyleSheet("background:#f2eef8;border-radius:12px;color:#9a8fb0;")
        self.canvas.setMouseTracking(False)
        layout.addWidget(self.canvas, 1)

        btns = QHBoxLayout()
        save_btn = QPushButton("保存透明 PNG")
        save_btn.clicked.connect(self.save_png)
        btns.addWidget(save_btn)
        apply_btn = QPushButton("直接应用到桌宠")
        apply_btn.setObjectName("send")
        apply_btn.clicked.connect(self.apply)
        btns.addWidget(apply_btn)
        close = QPushButton("关闭")
        close.clicked.connect(self.close)
        btns.addWidget(close)
        layout.addLayout(btns)

    # ---- 基础
    def open_image(self):
        path = pick_image(self)
        if not path:
            return
        try:
            self.original = pet_assets.load_source(path)
        except Exception as e:
            self.canvas.setText(f"读取失败：{e}")
            return
        if not pet_assets.has_real_alpha(self.original):
            self.original = pet_assets.remove_background(self.original, self.tol.value())
        self.img = self.original.copy()
        self.undo_stack.clear()
        self.refresh()

    def auto_remove(self):
        if not self.original:
            return
        self.push_undo()
        base = self.original.copy()
        if pet_assets.has_real_alpha(base):
            self.img = base
        else:
            self.img = pet_assets.smooth_alpha(pet_assets.remove_background(base, self.tol.value()))
        self.refresh()

    def reset(self):
        if self.original:
            self.push_undo()
            self.img = self.original.copy()
            self.refresh()

    # ---- 撤销
    def push_undo(self):
        if self.img is None:
            return
        self.undo_stack.append(self.img.copy())
        if len(self.undo_stack) > UNDO_LIMIT:
            self.undo_stack.pop(0)

    def undo(self):
        if self.undo_stack:
            self.img = self.undo_stack.pop()
            self.refresh()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.undo()
        else:
            super().keyPressEvent(event)

    # ---- 画布
    def _display_scale(self):
        """显示坐标 → 图片坐标 的缩放系数。"""
        pm = self.canvas.pixmap()
        if not self.img or not pm or pm.isNull():
            return None, 0
        shown = pm.size()
        scale = self.img.width / max(1, shown.width())
        return scale, shown

    def _paint_at(self, pos, restore=False):
        scale, shown = self._display_scale()
        if scale is None:
            return
        img_x = int(pos.x() * scale)
        img_y = int(pos.y() * scale)
        r = max(1, round(self.brush.value() * scale / 2))
        if restore:
            # 右键恢复：从原图取回被擦掉的像素（画圆域内还原）
            fx = self.original.width / self.img.width
            fy = self.original.height / self.img.height
            sx, sy = round(img_x * fx), round(img_y * fy)
            rx, ry = round(r * fx), round(r * fy)
            box = (max(0, sx - rx), max(0, sy - ry),
                   min(self.original.width, sx + rx), min(self.original.height, sy + ry))
            if box[2] <= box[0] or box[3] <= box[1]:
                return
            patch = self.original.crop(box)
            mask = Image.new("L", patch.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, patch.width - 1, patch.height - 1), fill=255)
            self.img.paste(patch, (box[0], box[1]), mask)
        else:
            d = ImageDraw.Draw(self.img)
            d.ellipse((img_x - r, img_y - r, img_x + r, img_y + r), fill=(0, 0, 0, 0))
        self.refresh()

    def mousePressEvent(self, event):
        if self.img is None or event.button() not in (
                Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return
        pos = self.canvas.mapFrom(self, event.position().toPoint())
        self.stroke_start = pos
        self.last_img_pos = pos
        self.restore_mode = (event.button() == Qt.MouseButton.RightButton)
        self.push_undo()
        self._paint_at(QPoint(pos.x(), pos.y()), restore=self.restore_mode)

    def mouseMoveEvent(self, event):
        if self.stroke_start is None or self.img is None:
            return
        pos = self.canvas.mapFrom(self, event.position().toPoint())
        # 画布内才画
        pm = self.canvas.pixmap()
        if pm and pm.isNull() is False:
            if not (0 <= pos.x() < pm.width() and 0 <= pos.y() < pm.height()):
                return
        # 连线画，避免快速移动出现断点
        self._paint_line(self.last_img_pos, pos, restore=self.restore_mode)
        self.last_img_pos = pos

    def mouseReleaseEvent(self, event):
        self.stroke_start = None
        self.last_img_pos = None

    def _paint_line(self, p0, p1, restore=False):
        if p0 is None:
            p0 = p1
        steps = max(1, int(((p1.x() - p0.x()) ** 2 + (p1.y() - p0.y()) ** 2) ** .5 // 4) + 1)
        for i in range(steps + 1):
            t = i / steps
            self._paint_at(QPoint(round(p0.x() + (p1.x() - p0.x()) * t),
                                  round(p0.y() + (p1.y() - p0.y()) * t)), restore=restore)

    def refresh(self):
        if not self.img:
            return
        pm = pil_to_pixmap(preview_image(self.img))
        self.canvas.setPixmap(pm.scaled(self.canvas.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))

    # ---- 输出
    def save_png(self):
        if not self.img:
            return
        desktop = QStandardPaths.standardLocations(QStandardPaths.StandardLocation.DesktopLocation)
        default_name = (desktop[0] + "/透明形象.png") if desktop else "透明形象.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存透明 PNG", default_name,
            "PNG 图片 (*.png)")
        if not path:
            return
        out = self.img.copy()
        bbox = out.getchannel("A").getbbox()
        if bbox:
            out = out.crop(bbox)
        out.save(path)
        self.pet.say("透明 PNG 保存好了！", 2600)

    def apply(self):
        if not self.img:
            return
        if pet_assets.opaque_ratio(self.img) < 0.02:
            self.canvas.setText("主体几乎被擦空了，无法应用。")
            return
        try:
            pet_assets.apply_character(self.img.copy(), self.pet.assets_dir)
        except Exception as e:
            self.canvas.setText(f"应用失败：{e}")
            return
        self.pet.reload_character()
        self.pet.say("擦得真干净，新形象上线！", 2600)
        self.close()


# ---------------------------------------------------------------- 文案编辑器

SCENE_LABELS = [
    ("hello", "开场白（启动时说）"), ("idle", "闲聊（闲置时随机说）"),
    ("jump", "点击-跳跃"), ("squish", "点击-压扁"), ("shake", "点击-摇摆"),
    ("pat", "摸摸头"), ("feed", "喂吃的"), ("walk", "走路"),
    ("sleep", "睡觉"), ("follow", "跟随鼠标"), ("drag", "被拖动"), ("wake", "被唤醒"),
    ("miss", "想你提醒（冷落时弹窗说）"), ("sad", "被冷落掉好感时"), ("full", "好感度满格"),
]

CHAT_RULES_LABEL = (
    "聊天回复规则（不联网）：每个规则两行，规则之间空一行。\n"
    "第一行：触发关键词，用逗号分隔；第二行开始：每行一句回复，程序随机挑一句。\n"
    "示例：\n  早,你好,嗨\n  你好呀！今天有什么想分享的？\n  嗨嗨，我在呢～")


def load_dialogues(data_dir: Path, defaults: dict) -> dict:
    try:
        data = json.loads((data_dir / "custom_texts.json").read_text(encoding="utf-8"))
        d = data.get("dialogues", {})
        if isinstance(d, dict):
            merged = {k: list(v) for k, v in defaults.items()}
            for k, v in d.items():
                if isinstance(v, list) and v and k in merged:
                    merged[k] = [str(x) for x in v]
            return merged
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {k: list(v) for k, v in defaults.items()}


def load_chat_rules(data_dir: Path, defaults: list, fallback: list):
    try:
        data = json.loads((data_dir / "custom_texts.json").read_text(encoding="utf-8"))
        raw = data.get("chat_rules")
        if isinstance(raw, list):
            rules = []
            for item in raw:
                if isinstance(item, dict):
                    kw = [str(x) for x in item.get("keywords", [])]
                    rep = [str(x) for x in item.get("replies", [])]
                    if kw and rep:
                        rules.append((tuple(kw), rep))
            if rules:
                fb = data.get("chat_fallback")
                if isinstance(fb, list) and fb:
                    fallback = [str(x) for x in fb]
                return rules, fallback
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return list(defaults), list(fallback)


def save_texts(data_dir: Path, dialogues: dict, chat_rules: list, chat_fallback: list) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "dialogues": dialogues,
        "chat_rules": [{"keywords": list(kw), "replies": rep} for kw, rep in chat_rules],
        "chat_fallback": chat_fallback,
    }
    (data_dir / "custom_texts.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def rules_to_text(rules: list) -> str:
    blocks = []
    for kw, replies in rules:
        blocks.append(",".join(kw) + "\n" + "\n".join(replies))
    return "\n\n".join(blocks)


def text_to_rules(text: str):
    rules = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if len(lines) >= 2:
            kw = [w for w in lines[0].replace("，", ",").split(",") if w]
            rep = lines[1:]
            if kw and rep:
                rules.append((tuple(kw), rep))
    return rules


class DialogueEditor(QDialog):
    def __init__(self, pet):
        super().__init__(pet)
        self.pet = pet
        self.setWindowTitle("编辑文案 · 凌丸")
        self.resize(620, 660)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        # Tab1 气泡台词
        bubble = QWidget()
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(10, 10, 10, 10)
        note = QLabel("每行一句台词，程序随机挑选；留空或删光则恢复默认。改完点右下角「保存并生效」。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#8a7f99;font-size:12px;")
        bl.addWidget(note)
        self.bubble_edits = {}
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setSpacing(8)
        for key, label in SCENE_LABELS:
            cap = QLabel(label)
            cap.setStyleSheet("color:#5a4e6e;font-weight:bold;")
            il.addWidget(cap)
            edit = QTextEdit()
            edit.setPlainText("\n".join(self.pet.dialogues.get(key, [])))
            edit.setMinimumHeight(56)
            edit.setSizePolicy(edit.sizePolicy().horizontalPolicy(), edit.sizePolicy().verticalPolicy())
            self.bubble_edits[key] = edit
            il.addWidget(edit)
        il.addStretch(1)
        inner.setLayout(il)
        scroll.setWidget(inner)
        bl.addWidget(scroll, 1)
        tabs.addTab(bubble, "气泡台词")

        # Tab2 聊天回复
        chat = QWidget()
        cl = QVBoxLayout(chat)
        cl.setContentsMargins(10, 10, 10, 10)
        cap = QLabel(CHAT_RULES_LABEL)
        cap.setWordWrap(True)
        cap.setStyleSheet("color:#8a7f99;font-size:12px;")
        cl.addWidget(cap)
        self.rules_edit = QTextEdit()
        self.rules_edit.setPlainText(rules_to_text(self.pet.chat_rules))
        cl.addWidget(self.rules_edit, 1)
        cl.addWidget(QLabel("兜底回复（没匹配到关键词时随机说，每行一句）："))
        self.fallback_edit = QTextEdit()
        self.fallback_edit.setPlainText("\n".join(self.pet.chat_fallback))
        self.fallback_edit.setMaximumHeight(110)
        cl.addWidget(self.fallback_edit)
        tabs.addTab(chat, "聊天回复")

        btns = QHBoxLayout()
        save = QPushButton("保存并生效")
        save.setObjectName("send")
        save.clicked.connect(self.save)
        btns.addWidget(save)
        reset = QPushButton("全部恢复默认")
        reset.clicked.connect(self.reset_all)
        btns.addWidget(reset)
        close = QPushButton("关闭")
        close.clicked.connect(self.close)
        btns.addWidget(close)
        layout.addLayout(btns)

    def save(self):
        dialogues = {}
        for key, edit in self.bubble_edits.items():
            lines = [ln.strip() for ln in edit.toPlainText().replace("\r\n", "\n").split("\n") if ln.strip()]
            if lines:
                dialogues[key] = lines
        rules = text_to_rules(self.rules_edit.toPlainText())
        fallback = [ln.strip() for ln in self.fallback_edit.toPlainText().replace("\r\n", "\n").split("\n") if ln.strip()]
        try:
            save_texts(self.pet.data_dir, dialogues, rules, fallback)
        except OSError as e:
            self.setWindowTitle(f"编辑文案 · 保存失败：{e}")
            return
        self.pet.apply_texts(dialogues, rules, fallback)
        self.pet.say("台词已更新，说给你听！", 2600)
        self.close()

    def reset_all(self):
        self.pet.clear_texts()
        for key, edit in self.bubble_edits.items():
            edit.setPlainText("\n".join(self.pet.dialogues.get(key, [])))
        self.rules_edit.setPlainText(rules_to_text(self.pet.chat_rules))
        self.fallback_edit.setPlainText("\n".join(self.pet.chat_fallback))


# ---------------------------------------------------------------- 打开入口

def open_swap(pet):
    _open_once(pet, "swap_dialog", SwapDialog)


def open_cutout(pet):
    _open_once(pet, "cutout_dialog", CutoutStudio)


def open_dialogue_editor(pet):
    _open_once(pet, "text_dialog", DialogueEditor)


def _open_once(pet, attr, cls):
    dlg = getattr(pet, attr, None)
    if dlg is None or not dlg.isVisible():
        dlg = cls(pet)
        setattr(pet, attr, dlg)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
