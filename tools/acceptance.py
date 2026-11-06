"""Focused acceptance checks against the real Qt event loop and Windows window."""
import ctypes
import json
from pathlib import Path
import sys
import time
import traceback

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QContextMenuEvent, QCursor, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


class Acceptance:
    def __init__(self, app, pet, output: Path, errors):
        self.app, self.pet, self.output, self.errors = app, pet, output, errors
        self.results = []

    def check(self, name, ok, details=""):
        self.results.append({"name": name, "passed": bool(ok), "details": details})
        if not ok:
            raise AssertionError(f"{name}: {details}")

    def wait(self, ms=150):
        QTest.qWait(ms)

    def start(self):
        try:
            self.run()
        except Exception:
            self.results.append({"name": "acceptance_exception", "passed": False, "details": traceback.format_exc()})
        finally:
            self.pet.save_settings()
            report = {"passed": all(r["passed"] for r in self.results) and not self.errors,
                      "packaged": bool(getattr(sys, "frozen", False)),
                      "checks": self.results, "runtime_errors": self.errors}
            (self.output / "acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.pet.tray.hide()
            self.app.exit(0 if report["passed"] else 1)

    def capture(self, filename):
        self.wait(160)
        screen = self.pet.screen()
        bounds = self.pet.geometry()
        if self.pet.bubble.isVisible():
            bounds = bounds.united(self.pet.bubble.geometry())
        bounds = bounds.adjusted(-28, -24, 28, 24).intersected(screen.geometry())
        # This is a real desktop capture, not a render or reconstructed preview.
        shot = screen.grabWindow(0, bounds.x(), bounds.y(), bounds.width(), bounds.height())
        shot.save(str(self.output / filename))

    def run(self):
        pet = self.pet
        pet.resize_pet(330)
        area = pet.available()
        pet.move(area.right() - pet.width() - 100, area.bottom() - pet.height() - 70)
        self.wait()
        flags = pet.windowFlags()
        self.check("transparent_frameless_topmost", pet.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                   and bool(flags & Qt.WindowType.FramelessWindowHint)
                   and bool(flags & Qt.WindowType.WindowStaysOnTopHint))
        hwnd = int(pet.winId())
        exstyle = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -16)
        self.check("native_windows_layered_topmost_no_caption", bool(exstyle & 0x80000)
                   and bool(exstyle & 0x8) and not bool(style & 0xC00000), f"ex={exstyle:#x}, style={style:#x}")
        self.check("embedded_character_and_12_running_frames", not pet.pixmap.isNull()
                   and pet.pixmap.hasAlphaChannel() and all(not f.isNull() for f in pet.frames))
        pet.say("我来啦！今天也陪你一起加油。", 15000)
        self.wait()
        self.check("bubble_outside_character", not pet.geometry().intersects(pet.bubble.geometry()))
        self.capture("desktop_pet.png")
        point = QPoint(pet.width() // 2, pet.height() // 2)
        for effect in ("jump", "squish", "shake"):
            QTest.mouseClick(pet, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
            self.wait(120)
            self.check("click_cycle_" + effect, pet.effect == effect, pet.effect)
            state = pet.visual_state()
            self.check("visible_animation_" + effect, any(abs(state[i] - default) > 0.01 for i, default in ((1,1),(2,1),(3,0),(4,0),(5,0))))
        before = pet.pos()
        global_start = pet.mapToGlobal(point)
        press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(point), QPointF(global_start), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(pet, press)
        for delta in (QPoint(-35, -10), QPoint(-80, -35)):
            cursor = global_start + delta
            move = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(pet.mapFromGlobal(cursor)), QPointF(cursor), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(pet, move)
            self.wait(50)
        self.check("left_drag_moves_and_runs", pet.pos() != before and pet.dragging and pet.direction == -1)
        self.capture("drag_running.png")
        cursor = global_start + QPoint(-80, -35)
        release = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPointF(pet.mapFromGlobal(cursor)), QPointF(cursor), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(pet, release)
        self.check("drag_release_is_not_click", not pet.dragging and pet.press_global is None and pet.cycle == 3)
        old = pet.pet_height
        wheel = QWheelEvent(QPointF(point), QPointF(pet.mapToGlobal(point)), QPoint(), QPoint(0,120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(pet, wheel)
        self.check("wheel_resizes", pet.pet_height > old)
        # Exercise native context event and every requested action label.
        context = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, pet.mapToGlobal(point))
        QApplication.sendEvent(pet, context)
        self.wait()
        menu = pet.context_menu
        actions = {a.text(): a for a in menu.actions() if not a.isSeparator()}
        required = {"陪我聊聊天", "摸摸头", "喂吃的", "让他走路", "让他睡觉", "跟随鼠标", "调整大小", "置顶开关", "退出程序"}
        self.check("all_requested_context_actions", required <= actions.keys(), str(list(actions)))
        menu.hide()
        actions["摸摸头"].trigger()
        self.check("pat_action", pet.effect == "pat")
        actions["喂吃的"].trigger()
        self.check("feed_action", pet.effect == "feed")
        actions["让他走路"].trigger()
        before_x = pet.x()
        self.wait(600)
        self.check("walking_changes_position", pet.mode == "walk" and pet.x() != before_x)
        pet.direction = 1
        pet.move(area.right() - pet.width() + 1, pet.y())
        self.wait(200)
        self.check("walking_bounces_at_screen_edge", pet.direction == -1 and area.contains(pet.geometry()))
        actions["让他睡觉"].trigger()
        self.check("sleep_mode", pet.mode == "sleep" and pet.timer.interval() == 100)
        QTest.mouseClick(pet, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        self.check("click_wakes", pet.mode == "idle")
        pet.move(area.left() + 35, area.top() + 160)
        cursor = QCursor.pos()
        if (cursor - pet.geometry().center()).manhattanLength() < 300:
            pet.move(area.right() - pet.width() - 60, area.bottom() - pet.height() - 50)
        initial = (cursor - pet.geometry().center()).manhattanLength()
        actions["跟随鼠标"].trigger()
        self.wait(500)
        current = (cursor - pet.geometry().center()).manhattanLength()
        self.check("follows_mouse", pet.mode == "follow" and current < initial, f"{initial} -> {current}")
        pet.set_mode("idle")
        for height in (150, 330, 720):
            pet.resize_pet(height)
            for x, y in ((area.left(),area.top()), (area.right()-pet.width()+1,area.top()),
                         (area.left(),area.bottom()-pet.height()+1), (area.right()-pet.width()+1,area.bottom()-pet.height()+1)):
                pet.move(x, y)
                pet.say("靠近屏幕边缘也能好好说话～", 1000)
                self.wait(40)
                self.check(f"bubble_edge_{height}_{x}_{y}", pet.bubble.isVisible()
                           and not pet.geometry().intersects(pet.bubble.geometry())
                           and area.contains(pet.bubble.geometry()))
        pet.resize_pet(330)
        pet.move(area.right() - pet.width() - 100, area.bottom() - pet.height() - 70)
        pet.set_topmost(False)
        self.wait()
        self.check("topmost_off_native", not (ctypes.windll.user32.GetWindowLongW(int(pet.winId()), -20) & 8))
        pet.set_topmost(True)
        self.wait()
        self.check("topmost_on_native", bool(ctypes.windll.user32.GetWindowLongW(int(pet.winId()), -20) & 8))
        pet.open_chat()
        pet.chat.move(area.center().x() - 170, area.center().y() - 270)
        self.wait()
        pet.chat.input.setText("今天有点累")
        QTest.keyClick(pet.chat.input, Qt.Key.Key_Return)
        text = pet.chat.history.toPlainText()
        self.check("chinese_chat_enter_reply", "今天有点累" in text and ("喝口水" in text or "拥抱" in text))
        pet.chat.send("<b>开心</b>")
        self.check("chat_escapes_markup", "<b>开心</b>" in pet.chat.history.toPlainText())
        self.wait()
        screen = pet.chat.screen()
        r = pet.chat.frameGeometry()
        screen.grabWindow(0, r.x(), r.y(), r.width(), r.height()).save(str(self.output / "chat_window.png"))
        pet.chat.close()
        self.check("closing_chat_keeps_pet_alive", pet.isVisible() and not pet.chat.isVisible())
        pet.resize_pet(720)
        pet.set_mode("idle")
        for effect in ("jump", "squish", "shake"):
            pet.effect = effect
            for fraction in (0.17, 0.5, 0.83):
                pet.effect_start = time.monotonic() - pet.effect_duration * fraction
                image = pet.grab().toImage()
                border = [image.pixelColor(x, y).alpha() for x in range(image.width()) for y in (0, image.height()-1)]
                border += [image.pixelColor(x, y).alpha() for y in range(image.height()) for x in (0, image.width()-1)]
                self.check(f"large_animation_no_clipping_{effect}_{fraction}", not any(border))
        pet.effect = ""
        pet.resize_pet(330)
        pet.move(area.right() - pet.width() - 100, area.bottom() - pet.height() - 70)
        pet.save_settings()
        saved = json.loads(pet.settings_path.read_text(encoding="utf-8"))
        self.check("position_size_topmost_persisted", all(saved.get(k) == v for k, v in {"height":330,"x":pet.x(),"y":pet.y(),"on_top":True}.items()))
        pet.say("验证完成，准备陪你一起工作啦！", 5000)
        self.capture("desktop_final.png")
        self.check("no_runtime_exceptions", not self.errors, str(self.errors))
