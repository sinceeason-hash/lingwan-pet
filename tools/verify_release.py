"""Verify the EXE in isolation, then launch it with no command-line arguments."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
DELIVERY = ROOT / "delivery"
OUT = ROOT / "validation" / "isolated"
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = next(DELIVERY.glob("*.exe"))
EXE = OUT / SOURCE.name
shutil.copy2(SOURCE, EXE)
env = os.environ.copy()
env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
for key in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
    env.pop(key, None)
env["PHOTO_PET_DATA_DIR"] = str(OUT / "normal_profile")
qa = subprocess.run([str(EXE), "--self-test", str(OUT / "packaged")], cwd=OUT, env=env, timeout=45)
report = json.loads((OUT / "packaged" / "acceptance.json").read_text(encoding="utf-8"))
assert qa.returncode == 0 and report["passed"] and report["packaged"], report
user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def windows():
    found = []
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindowLongW(hwnd, -20) & 0x20:
            return True
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        if title.value != SOURCE.stem:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)
        if handle:
            name = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(name))
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size))
            kernel32.CloseHandle(handle)
            if ok and Path(name.value).resolve() == EXE.resolve():
                found.append((hwnd, pid.value))
        return True
    user32.EnumWindows(callback_type(callback), 0)
    return found


start = time.monotonic()
process = subprocess.Popen([str(EXE)], cwd=OUT, env=env)
visible = []
try:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        visible = windows()
        if visible:
            break
        if process.poll() is not None:
            raise AssertionError("Normal launch exited before a window appeared")
        time.sleep(.1)
    assert len(visible) == 1, visible
    seconds = round(time.monotonic() - start, 3)
    duplicate = subprocess.run([str(EXE)], cwd=OUT, env=env, timeout=25)
    assert duplicate.returncode == 0 and len(windows()) == 1, f"Duplicate instance: code={duplicate.returncode}, windows={windows()}"
    # Close the exact owned window through its native close message.
    user32.PostMessageW(visible[0][0], 0x10, 0, 0)
    code = process.wait(timeout=15)
    assert code == 0 and not windows(), "Clean exit failed"
    settings = json.loads((OUT / "normal_profile" / "settings.json").read_text(encoding="utf-8"))
    assert settings["height"] == 260 and settings["on_top"] is True
    # Inspect packed contents: all runtime/image dependencies are internal.
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(EXE))
    names = list(archive.toc)
    assert any("character.png" in n for n in names)
    assert any("python312.dll" in n.lower() for n in names)
    assert any("qwindows.dll" in n.lower() for n in names)
    assert not any("tkinter" in n.lower() or "_tkinter" in n.lower() for n in names)
    result = {"passed": True, "exe": str(SOURCE), "bytes": SOURCE.stat().st_size,
              "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "independent_no_argument_launch": True, "launch_seconds": seconds,
              "path_restricted_to_windows_system32": True, "duplicate_instance_prevented": True,
              "normal_exit_code": code, "settings_saved": settings,
              "packaged_interaction_checks": len(report["checks"]),
              "packaged_interaction_report": str(OUT / "packaged" / "acceptance.json"),
              "embedded_runtime": True, "tkinter_absent": True}
    (ROOT / "validation" / "release_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
finally:
    if process.poll() is None:
        for hwnd, pid in windows():
            user32.PostMessageW(hwnd, 0x10, 0, 0)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
