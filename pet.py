from __future__ import annotations

import html
import json
import math
import os
from pathlib import Path
import random
import sys
import time
import traceback

import pet_gui
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, QStandardPaths, QLockFile
from PySide6.QtGui import QColor, QCursor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QApplication, QWidget, QMenu, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextBrowser, QSystemTrayIcon,
)

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
APP_NAME = "凌丸"
# 打包变体：assets/app.json 的 {"name": "..."} 可覆盖应用名（设置目录随之独立，可与主程序同时运行）
try:
    _cfg = json.loads((ASSETS / "app.json").read_text(encoding="utf-8"))
    if isinstance(_cfg.get("name"), str) and _cfg["name"].strip():
        APP_NAME = _cfg["name"].strip()
except (OSError, ValueError, TypeError, AttributeError):
    pass
STYLE = """
QMenu { background:#fcf9ff; color:#332c42; border:1px solid #e0d6ed; border-radius:10px; padding:7px; font:10pt 'Microsoft YaHei UI'; }
QMenu::item { padding:9px 28px 9px 17px; border-radius:5px; }
QMenu::item:selected { background:#ede5f6; color:#684992; }
QMenu::separator { height:1px; background:#e9e1ef; margin:5px 10px; }
QDialog { background:#f9f6fc; color:#332c42; }
QLabel { color:#443652; }
QTextBrowser { background:white; border:1px solid #e8dff0; border-radius:12px; padding:12px; color:#332c42; }
QLineEdit { background:white; border:1px solid #daccE7; border-radius:10px; padding:11px; color:#332c42; }
QLineEdit:focus { border:1px solid #9371bc; }
QPushButton { background:#eee7f6; border:0; border-radius:8px; padding:9px 13px; color:#69478d; }
QPushButton:hover { background:#e1d4ef; }
QPushButton#send { background:#795799; color:white; padding:11px 20px; }
QPushButton#send:hover { background:#654680; }
"""
NEGLECT_MINUTES = 30      # 冷落多少分钟后弹出提醒
DECAY_DELAY_SECONDS = 90  # 提醒后多少秒未处理则降低好感度
DECAY_AMOUNT = 5
COMPANION_GAIN_SECONDS = 60  # 走路/跟随模式陪伴每满这么多秒 +1

DIALOGUES = {
    "hello": ["凌丸上线，今天也陪你！", "眨个眼，快乐开始营业～", "左键拖我，右键发现小惊喜～"],    "jump": ["凌丸一蹦，快乐起跳！", "蹦一下，灵感就来啦！", "接住今天的一点小开心～"],
    "squish": ["压扁的是我，弹回来的是快乐。", "Q 弹一下，继续营业！", "弹性满分，烦恼清零～"],
    "shake": ["摇一摇，把困意甩掉！", "今天也在认真可爱。", "左右摇摆，快乐加倍～"],
    "pat": ["摸摸头，能量 +100！", "收到你的温柔啦。", "再摸一下也不是不可以～"],
    "feed": ["啊呜！这一口是快乐味的。", "谢谢投喂，今天你最可爱！", "吃饱啦，继续陪你努力。"],
    "walk": ["出发！巡视一下你的桌面。", "散散步，灵感也许就在拐角。", "小步快跑，快乐报到！"],
    "sleep": ["我眯一小会儿，点我就醒。", "晚安按钮已按下，Zzz…", "做个好梦，你也记得休息。"],
    "follow": ["跟着你的小箭头探险！", "你指哪里，我就去哪里～", "小尾巴模式，开启！"],
    "drag": ["搬家咯，抓稳啦！", "跑跑跑，换个好位置！", "这趟桌面旅行由你导航～"],
    "wake": ["醒啦！刚刚梦到好吃的了。", "电量补满，继续陪你！"],
    "idle": ["肩膀放松一点，喝口水吧。", "不用一下做完，前进一点也很好。", "我在这里，陪你慢慢来。"],
    "miss": ["呜呜，好久没人理我了……点我一下好不好？", "屏幕都冷清了，快来摸摸头！", "想你了！再不理我好感度要掉啦～"],
    "sad": ["好感度下降了……我有点难过。", "哼，不理我，我就蹲在这里画圈圈。", "心疼 +1，记得常来陪我呀。"],
    "full": ["好感度满格！你是我最好的人类朋友！", "满分喜欢！今天也超开心～"],
}


CHAT_RULES = [
    (("难过", "伤心", "焦虑", "压力", "烦", "累"), ["先给你一个小小的拥抱。把最烦的一件事说出来吧，我陪你慢慢梳理。", "今天已经很努力了。先喝口水、松松肩，我们一次只处理一件小事。"]),
    (("睡", "晚安", "困"), ["把今天轻轻放下吧。愿你今晚睡得香，明天醒来有个好心情。"]),
    (("早", "你好", "嗨", "hello"), ["你好呀！桌面小伙伴已上线，今天有什么想分享的？"]),
    (("饿", "吃", "饭", "奶茶"), ["认真吃饭也是大事！想吃热乎的饭，还是清爽的小点心？", "我的快乐清单：好好吃饭、晒晒太阳，还有陪你聊天。"]),
    (("工作", "学习", "考试", "作业", "加油"), ["给你加满勇气！先专注 20 分钟，再给自己一个小休息，怎么样？", "把大目标切成一小块：现在最容易开始的那一步是什么？"]),
    (("笑话", "开心", "有趣"), ["为什么电脑不怕冷？因为它有 Windows（窗户），还会自己发热呀。", "我的特长是陪伴，副业是在你桌面上认真摸鱼。"]),
    (("谢谢", "喜欢", "可爱", "爱你"), ["收到！这份好心情我好好收下啦～", "有你在，今天的桌面也亮了一点。"]),
    (("天气", "新闻", "联网", "搜索"), ["我擅长本地陪伴和趣味聊天。实时天气、新闻可以交给浏览器，回来记得和我分享呀。"]),
    (("几点", "时间", "日期", "星期"), [time.strftime("现在是 %Y 年 %m 月 %d 日 %H:%M。也记得给自己留一点休息时间。")]),
]
CHAT_FALLBACK = ["我在听呀。今天这件事让你有什么感觉？", "愿意多和我说一点吗？我喜欢听你分享日常。", "嗯嗯，收到你的分享啦。忙碌的时候，也别忘了照顾自己。", "给平凡的一天加一点小快乐：伸个懒腰，再继续吧！"]


def local_reply(message: str, rules=None, fallback=None) -> str:
    text = message.strip().lower()
    rules = rules if rules is not None else CHAT_RULES
    fallback = fallback if fallback is not None else CHAT_FALLBACK
    for words, replies in rules:
        if any(word in text for word in words):
            return random.choice(replies)
    return random.choice(fallback)


class Bubble(QWidget):
    def __init__(self, pet: "Pet"):
        super().__init__(pet, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowTransparentForInput)
        self.pet = pet
        self.text = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.setFont(QFont("Microsoft YaHei UI", 10))

    def say(self, text: str, duration=3700):
        self.text = text
        bounds = self.fontMetrics().boundingRect(QRect(0, 0, 230, 500), int(Qt.TextFlag.TextWordWrap), text)
        self.resize(max(126, bounds.width() + 36), max(54, bounds.height() + 34))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.pet.on_top)
        self.reposition()
        self.show()
        self.update()
        self.timer.start(duration)

    def reposition(self):
        # Place against the whole pet window so even jumping frames stay clear.
        pet = self.pet.geometry()
        screen = self.pet.available()
        w, h, gap = self.width(), self.height(), 9
        candidates = [QRect(pet.center().x() - w // 2, pet.top() - h - gap, w, h),
                      QRect(pet.right() + gap, pet.top() + 35, w, h),
                      QRect(pet.left() - w - gap, pet.top() + 35, w, h),
                      QRect(pet.center().x() - w // 2, pet.bottom() + gap, w, h)]
        for r in candidates:
            r.moveLeft(max(screen.left() + 4, min(r.left(), screen.right() - w - 3)))
            r.moveTop(max(screen.top() + 4, min(r.top(), screen.bottom() - h - 3)))
            if not r.intersects(pet):
                self.move(r.topLeft())
                return
        self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#dacde7"), 1))
        p.setBrush(QColor(255, 251, 255, 248))
        p.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), 16, 16)
        p.setPen(QColor("#564065"))
        p.setFont(self.font())
        p.drawText(QRectF(18, 14, self.width() - 36, self.height() - 28), Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignVCenter, self.text)


class ChatDialog(QDialog):
    def __init__(self, pet: "Pet"):
        super().__init__(pet)
        self.pet = pet
        self.setWindowTitle("陪我聊聊天 · 凌丸")
        self.setWindowIcon(pet.windowIcon())
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pet.on_top)
        self.resize(430, 530)
        self.setMinimumSize(370, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(14)
        title = QLabel("和凌丸说说话")
        title.setFont(QFont("Microsoft YaHei UI", 17, QFont.Weight.Bold))
        layout.addWidget(title)
        subtitle = QLabel("本地趣味聊天 · 不联网 · 对话不保存")
        subtitle.setStyleSheet("color:#95829f;font-size:11px;")
        layout.addWidget(subtitle)
        self.history = QTextBrowser()
        self.history.setOpenExternalLinks(False)
        layout.addWidget(self.history, 1)
        quick = QHBoxLayout()
        for label in ("今天有点累", "讲个笑话", "给我加油"):
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, message=label: self.send(message))
            quick.addWidget(btn)
        layout.addLayout(quick)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("想说什么都可以，回车发送…")
        self.input.setMaxLength(500)
        self.input.returnPressed.connect(lambda: self.send())
        row.addWidget(self.input, 1)
        send = QPushButton("发送")
        send.setObjectName("send")
        send.clicked.connect(lambda: self.send())
        row.addWidget(send)
        layout.addLayout(row)
        self.append("凌丸", "嗨，我在这里。开心的事、烦心的小事，都可以和我说说。")

    def append(self, who: str, message: str):
        color = "#8460a5" if who == "凌丸" else "#577ca0"
        self.history.append(f'<p style="margin-top:14px;color:{color};"><b>{who}</b></p><p style="margin-top:5px;line-height:145%;">{html.escape(message)}</p>')
        self.history.verticalScrollBar().setValue(self.history.verticalScrollBar().maximum())

    def send(self, message=None):
        message = (self.input.text() if message is None else message).strip()
        if not message:
            return
        self.input.clear()
        self.append("你", message)
        reply = local_reply(message, self.pet.chat_rules, self.pet.chat_fallback)
        self.append("凌丸", reply)
        self.pet.say("我在认真听，你慢慢说。")
        self.pet.add_affection(2)
        self.input.setFocus()


class Pet(QWidget):
    def __init__(self, data_dir: Path):
        super().__init__()
        self.data_dir = data_dir
        self.assets_dir = ASSETS
        self.settings_path = data_dir / "settings.json"
        self.settings = self.read_settings()
        self.on_top = bool(self.settings.get("on_top", True))
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if self.on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(ASSETS / "pet.ico")))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.pixmap = QPixmap(str(ASSETS / "character.png"))
        if self.pixmap.isNull():
            raise RuntimeError("Character asset could not be loaded")
        self.frames = [QPixmap(str(ASSETS / f"run_{i:02d}.png")) for i in range(12)]
        self.ratio = self.pixmap.width() / self.pixmap.height()
        self.pet_height = 260
        self.dialogues = pet_gui.load_dialogues(data_dir, DIALOGUES)
        self.chat_rules, self.chat_fallback = pet_gui.load_chat_rules(data_dir, CHAT_RULES, CHAT_FALLBACK)
        self.affection = max(0.0, min(100.0, float(self.settings.get("affection", 50))))
        self.last_interaction = time.time()
        self.pending_decay = False
        self.companion_accum = 0.0
        self.miss_dialog = None
        self.mode = "idle"
        self.effect = ""
        self.effect_start = 0.0
        self.effect_duration = 0.85
        self.cycle = 0
        self.direction = 1
        self.press_global = None
        self.press_pos = None
        self.dragging = False
        self.drag_last = 0.0
        self.drag_velocity = 0.0
        self.last_tick = time.monotonic()
        self.clock_start = self.last_tick
        self.move_fraction = QPointF()
        self.chat = None
        self.context_menu = None
        self.bubble = Bubble(self)
        self.resize_pet(int(self.settings.get("height", 260)), save=False)
        area = self.available()
        self.move(int(self.settings.get("x", area.right() - self.width() - 60)),
                  int(self.settings.get("y", area.bottom() - self.height() - 22)))
        self.clamp_position()
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_settings)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self.idle_comment)
        self.idle_timer.start(110000)
        self.na_timer = QTimer(self)
        self.na_timer.timeout.connect(self.check_neglect)
        self.na_timer.start(60000)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("凌丸 · 桌面桌宠 · 右键打开菜单")
        self.tray.activated.connect(self.tray_activated)
        self.tray_menu = self.make_menu(tray=True)
        self.tray.setContextMenu(self.tray_menu)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        app = QApplication.instance()
        app.screenAdded.connect(lambda _: self.clamp_position())
        app.screenRemoved.connect(lambda _: self.clamp_position())
        for screen in app.screens():
            screen.availableGeometryChanged.connect(lambda _: self.clamp_position())

    def read_settings(self):
        try:
            value = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                return {}
            for name in ("height", "x", "y"):
                if name in value and (not isinstance(value[name], int) or abs(value[name]) > 100000):
                    value.pop(name)
            if "affection" in value and not isinstance(value["affection"], (int, float)):
                value.pop("affection")
            return value
        except (OSError, ValueError, TypeError):
            return {}

    def save_settings(self):
        data = {"height": self.pet_height, "x": self.x(), "y": self.y(), "on_top": self.on_top,
                "affection": self.affection}
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.settings_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.settings_path)
        except OSError:
            pass

    def available(self):
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        return screen.availableGeometry()

    def clamp_position(self):
        area = self.available()
        self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                  max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))
        if self.bubble.isVisible():
            self.bubble.reposition()

    def resize_pet(self, height: int, save=True):
        old_bottom = self.geometry().bottom()
        old_center = self.geometry().center().x()
        area = self.available()
        # A wide portrait needs room below its hands when the whole sprite tilts.
        height_limit = (area.height() - 180) / (1.26 + .18 * self.ratio)
        width_limit = (area.width() - 330) / (1.2 * self.ratio + .46)
        self.pet_height = max(110, min(720, int(height_limit), int(width_limit), height))
        width = self.pet_height * self.ratio
        side_padding = math.ceil(.10 * width + .23 * self.pet_height + 20)
        top_padding = max(72, math.ceil(.26 * self.pet_height + .09 * width + 20))
        self.bottom_padding = math.ceil(.09 * width + 20)
        self.resize(math.ceil(width) + side_padding * 2, self.pet_height + top_padding + self.bottom_padding)
        self.move(old_center - self.width() // 2, old_bottom - self.height() + 1)
        self.clamp_position()
        self.update()
        if save:
            self.save_timer.start(350)

    def say(self, text: str, duration=3700):
        self.bubble.say(text, duration)

    def speak(self, kind: str):
        self.say(random.choice(self.dialogues.get(kind, DIALOGUES.get(kind, ["……"]))))

    def idle_comment(self):
        if self.mode == "idle" and not self.dragging and not self.bubble.isVisible():
            self.speak("idle")

    # ---- 好感度 ----
    def affection_label(self) -> str:
        a = self.affection
        if a >= 90:
            return "死心塌地"
        if a >= 70:
            return "很喜欢你"
        if a >= 40:
            return "关系不错"
        if a >= 20:
            return "有点陌生"
        return "快生气了"

    def add_affection(self, amount: float):
        before = self.affection
        self.affection = max(0.0, min(100.0, self.affection + amount))
        self.last_interaction = time.time()
        if self.pending_decay:
            self.pending_decay = False
        if amount > 0 and before < 100 <= self.affection:
            self.speak("full")
        self.update()
        self.save_timer.start(500)

    def check_neglect(self):
        if self.pending_decay or self.dragging:
            return
        if QApplication.activePopupWidget() is not None or (self.chat is not None and self.chat.isVisible()):
            self.last_interaction = time.time()  # 聊天窗口开着也算陪伴
            return
        if time.time() - self.last_interaction >= NEGLECT_MINUTES * 60:
            self.show_miss_dialog()

    def show_miss_dialog(self):
        if self.miss_dialog is not None and self.miss_dialog.isVisible():
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("凌丸想你了")
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 24, 24, 18)
        layout.setSpacing(14)
        icon_label = QLabel("🥺")
        icon_label.setFont(QFont("Segoe UI Emoji", 26))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        text = QLabel(f"已经 {NEGLECT_MINUTES} 分钟没有理凌丸啦！\n" + random.choice(self.dialogues.get("miss", ["想你了～"])))
        text.setWordWrap(True)
        layout.addWidget(text)
        row = QHBoxLayout()
        pat_btn = QPushButton("这就来摸摸头 (+2 好感)")
        pat_btn.setObjectName("send")
        pat_btn.clicked.connect(lambda: (dlg.accept(), self.add_affection(2), self.interact("pat")))
        row.addWidget(pat_btn)
        later_btn = QPushButton("等会儿再说")
        later_btn.clicked.connect(lambda: (dlg.accept(), self.schedule_decay()))
        row.addWidget(later_btn)
        layout.addLayout(row)
        self.miss_dialog = dlg
        QTimer.singleShot(DECAY_DELAY_SECONDS * 1000, lambda: self._miss_timeout(dlg))
        dlg.show()

    def _miss_timeout(self, dlg):
        if dlg.isVisible():  # 一直没处理：自动关掉并掉好感
            dlg.close()
            self.schedule_decay()

    def schedule_decay(self):
        self.pending_decay = True
        self.decay_scheduled_at = time.time()
        QTimer.singleShot(DECAY_DELAY_SECONDS * 1000, self.do_decay)

    def do_decay(self):
        if not self.pending_decay:
            return
        self.pending_decay = False
        if getattr(self, "decay_scheduled_at", 0) < self.last_interaction:
            return  # 期间有过互动就不扣
        self.affection = max(0.0, self.affection - DECAY_AMOUNT)
        self.speak("sad")
        self.update()
        self.save_timer.start(500)

    def set_mode(self, mode: str):
        self.mode = mode
        self.effect = ""
        self.move_fraction = QPointF()
        self.timer.setInterval(100 if mode == "sleep" else 33)
        if mode != "idle":
            self.speak(mode)
        self.update()

    def interact(self, effect: str | None = None):
        if self.mode == "sleep":
            self.set_mode("idle")
            self.speak("wake")
            return
        if effect is None:
            effect = ("jump", "squish", "shake")[self.cycle % 3]
            self.cycle += 1
        self.effect = effect
        self.effect_start = time.monotonic()
        self.effect_duration = 1.4 if effect in ("pat", "feed") else 0.85
        self.add_affection({"pat": 2, "feed": 3}.get(effect, 1))
        self.speak(effect)

    def set_topmost(self, checked: bool):
        self.on_top = checked
        pos = self.pos()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()
        self.move(pos)
        self.bubble.hide()
        if self.chat:
            visible = self.chat.isVisible()
            self.chat.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
            if visible:
                self.chat.show()
        self.save_timer.start(300)

    def open_chat(self):
        if self.chat is None:
            self.chat = ChatDialog(self)
        self.chat.show()
        self.chat.raise_()
        self.chat.activateWindow()
        self.chat.input.setFocus()

    def reload_character(self):
        self.pixmap = QPixmap(str(ASSETS / "character.png"))
        self.frames = [QPixmap(str(ASSETS / f"run_{i:02d}.png")) for i in range(12)]
        if self.pixmap.isNull():
            raise RuntimeError("Character asset could not be loaded")
        self.ratio = self.pixmap.width() / self.pixmap.height()
        self.resize_pet(self.pet_height)

    def apply_texts(self, dialogues, chat_rules, chat_fallback):
        self.dialogues = {k: list(v) for k, v in DIALOGUES.items()}
        self.dialogues.update({k: list(v) for k, v in dialogues.items()})
        self.chat_rules = list(chat_rules)
        self.chat_fallback = list(chat_fallback)

    def clear_texts(self):
        self.dialogues = {k: list(v) for k, v in DIALOGUES.items()}
        self.chat_rules = list(CHAT_RULES)
        self.chat_fallback = list(CHAT_FALLBACK)
        try:
            (self.data_dir / "custom_texts.json").unlink()
        except OSError:
            pass

    def open_swap(self):
        pet_gui.open_swap(self)

    def open_cutout(self):
        pet_gui.open_cutout(self)

    def open_text_editor(self):
        pet_gui.open_dialogue_editor(self)

    def make_menu(self, tray=False):
        menu = QMenu()
        if tray:
            menu.addAction("把他叫回来", self.recall)
            menu.addSeparator()
        menu.addAction("更换形象", self.open_swap)
        menu.addAction("图片透明化工具", self.open_cutout)
        menu.addAction("编辑文案", self.open_text_editor)
        menu.addAction("陪我聊聊天", self.open_chat)
        menu.addAction("摸摸头", lambda: self.interact("pat"))
        menu.addAction("喂吃的", lambda: self.interact("feed"))
        menu.addSeparator()
        for title, mode in (("让他走路", "walk"), ("让他睡觉", "sleep"), ("跟随鼠标", "follow")):
            action = menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(self.mode == mode)
            action.triggered.connect(lambda checked, m=mode: self.set_mode(m if checked else "idle"))
            action.setData(mode)
        menu.addSeparator()
        size = menu.addMenu("调整大小")
        for title, height in (("小巧 · 180", 180), ("标准 · 260", 260), ("大号 · 360", 360), ("更大一点  +", self.pet_height + 30), ("更小一点  −", self.pet_height - 30)):
            if title.startswith("更大"):
                size.addAction(title, lambda: self.resize_pet(self.pet_height + 30))
            elif title.startswith("更小"):
                size.addAction(title, lambda: self.resize_pet(self.pet_height - 30))
            else:
                size.addAction(title, lambda checked=False, h=height: self.resize_pet(h))
        top = menu.addAction("置顶开关")
        top.setCheckable(True)
        top.setChecked(self.on_top)
        top.setData("top")
        top.triggered.connect(self.set_topmost)
        menu.addSeparator()
        aff = menu.addAction(f"好感度 {int(self.affection)} · {self.affection_label()}")
        aff.setEnabled(False)
        aff.setData("aff")
        menu.addAction("退出程序", self.quit)
        menu.aboutToShow.connect(lambda: self.sync_menu(menu))
        return menu

    def sync_menu(self, menu):
        for action in menu.actions():
            if action.data() in ("walk", "sleep", "follow"):
                action.setChecked(self.mode == action.data())
            elif action.data() == "top":
                action.setChecked(self.on_top)
            elif action.data() == "aff":
                action.setText(f"好感度 {int(self.affection)} · {self.affection_label()}")

    def recall(self):
        self.set_mode("idle")
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 32, area.bottom() - self.height() - 20)
        self.clamp_position()
        self.show()
        self.raise_()
        self.say("我在这里呀！")

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.recall()

    def contextMenuEvent(self, event):
        self.context_menu = self.make_menu()
        self.context_menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.context_menu.popup(event.globalPos())

    def quit(self):
        self.save_settings()
        self.tray.hide()
        self.bubble.hide()
        QApplication.instance().quit()

    def closeEvent(self, event):
        self.save_settings()
        self.tray.hide()
        event.accept()
        QApplication.instance().quit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_global = event.globalPosition().toPoint()
            self.press_pos = self.pos()
            self.dragging = False
            self.drag_last = time.monotonic()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self.press_global is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        cursor = event.globalPosition().toPoint()
        delta = cursor - self.press_global
        if not self.dragging and delta.manhattanLength() >= QApplication.startDragDistance():
            self.dragging = True
            self.set_mode("idle")
            self.speak("drag")
        if self.dragging:
            previous_x = self.x()
            self.move(self.press_pos + delta)
            self.clamp_position()
            dx = self.x() - previous_x
            if abs(dx) > 1:
                self.direction = 1 if dx > 0 else -1
            self.drag_velocity = abs(dx)
            self.drag_last = time.monotonic()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.press_global is not None:
            was_dragging = self.dragging
            self.press_global = None
            self.press_pos = None
            self.dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if was_dragging:
                self.save_timer.start(300)
            else:
                self.interact()

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta:
            self.resize_pet(self.pet_height + (22 if delta > 0 else -22))
        event.accept()

    def move_by(self, dx, dy=0.0):
        self.move_fraction += QPointF(dx, dy)
        x, y = round(self.move_fraction.x()), round(self.move_fraction.y())
        self.move_fraction -= QPointF(x, y)
        self.move(self.x() + x, self.y() + y)
        self.clamp_position()

    def tick(self):
        now = time.monotonic()
        dt = min(0.08, now - self.last_tick)
        self.last_tick = now
        if self.effect and now - self.effect_start >= self.effect_duration:
            self.effect = ""
        self.is_running = self.dragging
        blocked = self.press_global is not None or QApplication.activePopupWidget() is not None or (self.chat is not None and self.chat.isVisible())
        if not blocked and self.mode == "walk":
            area = self.available()
            if self.x() <= area.left() + 1:
                self.direction = 1
            elif self.geometry().right() >= area.right() - 1:
                self.direction = -1
            self.move_by(self.direction * 105 * dt)
            self.is_running = True
        elif not blocked and self.mode == "follow":
            cursor = QCursor.pos()
            # Stop short of the pointer so the pet does not steal its clicks.
            center = self.geometry().center()
            dx, dy = cursor.x() - center.x(), cursor.y() - center.y()
            distance = math.hypot(dx, dy)
            stop = max(self.width() * 0.58, 105)
            if distance > stop:
                speed = min(260, (distance - stop) * 2.8)
                self.direction = 1 if dx >= 0 else -1
                self.move_by(dx / distance * speed * dt, dy / distance * speed * dt)
                self.is_running = True
        # 陪伴加分：走路/跟随模式下每满 COMPANION_GAIN_SECONDS 秒 +1 好感
        if getattr(self, "is_running", False) and self.mode in ("walk", "follow") and not blocked:
            self.companion_accum += dt
            if self.companion_accum >= COMPANION_GAIN_SECONDS:
                self.companion_accum = 0.0
                self.add_affection(1)
        if self.bubble.isVisible():
            self.bubble.reposition()
        self.update()

    def visual_state(self):
        now = time.monotonic()
        elapsed = now - self.clock_start
        sx = sy = 1.0
        dx = dy = angle = 0.0
        running = self.dragging or getattr(self, "is_running", False)
        frame = self.pixmap
        if running:
            phase = elapsed * 14
            dy = -abs(math.sin(phase)) * self.pet_height * 0.032
            angle = self.direction * (4.5 + 2.8 * math.sin(phase))
            sx = 1.0 + 0.025 * math.sin(phase * 2)
            sy = 1.0 - 0.018 * math.sin(phase * 2)
            frame = self.frames[int(elapsed * 22) % len(self.frames)]
        elif self.mode == "sleep":
            sy = 0.94 + 0.008 * math.sin(elapsed * 1.7)
            angle = -6
        else:
            sy = 1.0 + 0.004 * math.sin(elapsed * 2)
            dy = -1.2 * math.sin(elapsed * 2)
        progress = min(1.0, max(0.0, (now - self.effect_start) / self.effect_duration))
        if self.effect == "jump":
            dy -= math.sin(math.pi * progress) * self.pet_height * 0.15
            sy *= 1 + 0.04 * math.sin(math.pi * progress)
        elif self.effect == "squish":
            wave = math.sin(progress * 3 * math.pi) * (1 - progress)
            sx *= 1 + 0.20 * wave
            sy *= 1 - 0.25 * wave
        elif self.effect == "shake":
            dx += math.sin(progress * 8 * math.pi) * (1 - progress) * 15
            angle += math.sin(progress * 8 * math.pi) * (1 - progress) * 7
        elif self.effect in ("pat", "feed"):
            sy *= 1 - 0.035 * math.sin(progress * math.pi * 4)
            angle += 2 * math.sin(progress * math.pi * 4)
        return frame, sx, sy, dx, dy, angle, progress

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        frame, sx, sy, dx, dy, angle, progress = self.visual_state()
        base = self.height() - self.bottom_padding
        width = self.pet_height * self.ratio
        p.save()
        p.translate(self.width() / 2 + dx, base + dy)
        p.rotate(angle)
        p.scale(sx * (-1 if self.direction < 0 else 1), sy)
        if self.mode == "sleep":
            p.setOpacity(0.86)
        p.drawPixmap(QRectF(-width / 2, -self.pet_height, width, self.pet_height), frame, QRectF(frame.rect()))
        p.restore()
        if self.effect == "pat":
            for index in range(3):
                x = self.width() / 2 + (index - 1) * 25
                y = base - self.pet_height - 5 - progress * 32 + index % 2 * 8
                self.draw_heart(p, QPointF(x, y), 7 + index, max(0, 1 - progress))
        elif self.effect == "feed":
            x = self.width() / 2 + math.sin(progress * math.pi) * 42
            y = base - self.pet_height * 0.58 - progress * 30
            p.setPen(QPen(QColor("#ad7138"), 2))
            p.setBrush(QColor("#e9b76e"))
            p.drawEllipse(QPointF(x, y), 14, 14)
            p.setBrush(QColor("#83512d"))
            p.setPen(Qt.PenStyle.NoPen)
            for ox, oy in ((-5,-4),(5,2),(-3,7),(6,-6)):
                p.drawEllipse(QPointF(x + ox, y + oy), 2.1, 2.1)
        if self.mode == "sleep":
            p.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
            p.setPen(QColor("#af91ce"))
            p.drawText(QPointF(self.width() / 2 + 30, 48 + 5 * math.sin(time.monotonic() * 1.5)), "z Z")
        if self.dragging or getattr(self, "is_running", False):
            p.setPen(QPen(QColor(174, 142, 205, 155), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            side = self.width() / 2 - self.direction * (width * 0.46 + 9)
            for i in range(3):
                y = base - 38 - i * 9
                p.drawLine(QPointF(side, y), QPointF(side - self.direction * (10 + i * 4), y))
        # ---- 好感度进度条（脚下）----
        if hasattr(self, "affection"):
            bar_w = max(72, width * 0.52)
            bar_h = 6
            x0 = (self.width() - bar_w) / 2
            y0 = base + 4
            pct = max(0.0, min(1.0, self.affection / 100))
            if self.affection >= 70:
                fill = QColor("#e989ad")
            elif self.affection >= 40:
                fill = QColor("#c39ad9")
            else:
                fill = QColor("#9aa0a6")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(236, 228, 243, 215))
            p.drawRoundedRect(QRectF(x0, y0, bar_w, bar_h), 3, 3)
            if pct > 0.02:
                p.setBrush(fill)
                p.drawRoundedRect(QRectF(x0, y0, bar_w * pct, bar_h), 3, 3)
            self.draw_heart(p, QPointF(x0 - 9, y0 + bar_h / 2 - 1), 4.2, 0.9)

    @staticmethod
    def draw_heart(painter, center, size, opacity):
        painter.save()
        painter.translate(center)
        painter.setOpacity(opacity)
        path = QPainterPath(QPointF(0, size))
        path.cubicTo(-size * 2, -size * .2, -size, -size * 1.4, 0, -size * .4)
        path.cubicTo(size, -size * 1.4, size * 2, -size * .2, 0, size)
        painter.fillPath(path, QColor("#e989ad"))
        painter.restore()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("PhotoPet")
    app.setApplicationVersion("1.0.0")
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)
    qa = "--self-test" in sys.argv
    if qa:
        output = Path(sys.argv[sys.argv.index("--self-test") + 1]).resolve()
        output.mkdir(parents=True, exist_ok=True)
        data = output / "profile"
    else:
        data = Path(os.environ.get("PHOTO_PET_DATA_DIR") or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    data.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(data / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        # A second double-click leaves the existing companion in place.
        return 0
    errors = []
    def exception_hook(kind, value, tb):
        message = "".join(traceback.format_exception(kind, value, tb))
        errors.append(message)
        try:
            with (data / "error.log").open("a", encoding="utf-8") as log:
                log.write(message + "\n")
        except OSError:
            pass
    sys.excepthook = exception_hook
    pet = Pet(data)
    pet.show()
    if qa:
        from tools.acceptance import Acceptance
        runner = Acceptance(app, pet, output, errors)
        QTimer.singleShot(500, runner.start)
    else:
        QTimer.singleShot(600, lambda: pet.speak("hello"))
    result = app.exec()
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
