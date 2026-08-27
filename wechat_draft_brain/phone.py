from __future__ import annotations

import subprocess
import time
from pathlib import Path

from PIL import Image

from wechat_draft_brain.paths import DATA_DIR, LAST_SHOT
from wechat_draft_brain.vision import find_red_badges, find_text, ocr_image, parse_chat, guess_title


class PhoneError(RuntimeError):
    pass


def _which_adb(cfg: dict) -> str:
    raw = ((cfg.get("adb") or {}).get("path") or "").strip()
    if raw:
        p = Path(raw)
        if p.is_dir():
            exe = p / "adb.exe"
            if exe.exists():
                return str(exe)
        if p.exists():
            return str(p)
    from shutil import which

    found = which("adb") or which("adb.exe")
    if found:
        return found
    return ""


def adb_status(cfg: dict) -> dict:
    path = _which_adb(cfg)
    if not path:
        return {"ok": False, "adb": "", "device": "", "error": "未找到 adb。请安装 Android platform-tools，或在 config/default.yaml 的 adb.path 填写路径。"}
    try:
        out = subprocess.check_output([path, "devices"], text=True, timeout=8)
    except Exception as e:
        return {"ok": False, "adb": path, "device": "", "error": f"adb devices 失败: {e}"}
    serial = ((cfg.get("adb") or {}).get("serial") or "").strip()
    rows = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            rows.append(parts[0])
    if serial and serial in rows:
        return {"ok": True, "adb": path, "device": serial, "error": ""}
    if not serial and len(rows) == 1:
        return {"ok": True, "adb": path, "device": rows[0], "error": ""}
    if not rows:
        return {"ok": False, "adb": path, "device": "", "error": "没有在线设备。打开手机 USB 调试并授权这台电脑。"}
    if not serial and len(rows) > 1:
        return {"ok": False, "adb": path, "device": "", "error": f"多台设备: {', '.join(rows)}，请在配置里填写 adb.serial。"}
    return {"ok": False, "adb": path, "device": "", "error": f"指定设备 {serial} 不在线。"}


class AdbPhone:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        st = adb_status(cfg)
        if not st["ok"]:
            raise PhoneError(st["error"])
        self.adb = st["adb"]
        self.serial = st["device"]

    def _run(self, *args: str, timeout: int = 20) -> bytes:
        cmd = [self.adb, "-s", self.serial, *args]
        return subprocess.check_output(cmd, timeout=timeout)

    def screenshot(self) -> Image.Image:
        raw = self._run("exec-out", "screencap", "-p")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LAST_SHOT.write_bytes(raw)
        return Image.open(LAST_SHOT).convert("RGB")

    def tap(self, x: int, y: int) -> None:
        self._run("shell", "input", "tap", str(x), str(y))

    def back(self) -> None:
        self._run("shell", "input", "keyevent", "4")

    def current_app(self) -> str:
        try:
            dump = self._run("shell", "dumpsys", "window", timeout=12).decode("utf-8", "ignore")
        except Exception:
            return ""
        for key in ("mCurrentFocus", "mFocusedApp"):
            for line in dump.splitlines():
                if key in line:
                    return line.strip()
        return ""

    def ensure_wechat(self) -> None:
        pkg = (self.cfg.get("adb") or {}).get("package") or "com.tencent.mm"
        focus = self.current_app()
        if pkg in focus:
            return
        self._run(
            "shell",
            "monkey",
            "-p",
            pkg,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        )
        time.sleep(2.0)

    def input_text(self, text: str) -> None:
        # 中文走 ADB Keyboard 广播；ASCII 可走 input text。
        if any(ord(ch) > 127 for ch in text):
            try:
                self._run(
                    "shell",
                    "am",
                    "broadcast",
                    "-a",
                    "ADB_INPUT_TEXT",
                    "--es",
                    "msg",
                    text,
                    timeout=12,
                )
                return
            except Exception:
                pass
            hexed = text.encode("utf-16be").hex()
            self._run("shell", "am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", hexed)
            return
        escaped = text.replace(" ", "%s").replace("'", "")
        self._run("shell", "input", "text", escaped)

    def send_message(self, text: str, image: Image.Image | None = None) -> None:
        layout = self.cfg.get("layout") or {}
        img = image or self.screenshot()
        w, h = img.size
        ix, iy = layout.get("input") or [0.50, 0.93]
        self.tap(int(w * ix), int(h * iy))
        time.sleep(0.35)
        self.input_text(text)
        time.sleep(0.4)
        img2 = self.screenshot()
        items = ocr_image(img2)
        send_btn = find_text(items, "发送")
        if send_btn:
            self.tap(int(send_btn["x"]), int(send_btn["y"]))
            return
        sx, sy = layout.get("send") or [0.90, 0.93]
        self.tap(int(w * sx), int(h * sy))


def run_auto_tick(cfg: dict) -> dict:
    phone = AdbPhone(cfg)
    phone.ensure_wechat()
    time.sleep(0.4)
    image = phone.screenshot()
    layout = cfg.get("layout") or {}
    region = tuple(layout.get("unread_region") or [0.02, 0.12, 0.22, 0.88])
    badges = find_red_badges(image, region)
    if not badges:
        return {"found": False, "detail": "未发现未读红点"}
    x, y = badges[0]
    # 红点在头像右上，往左下点进行会话
    phone.tap(max(40, x - 70), y + 8)
    time.sleep(1.1)
    chat = phone.screenshot()
    items = ocr_image(chat)
    w, h = chat.size
    contact = guess_title(items, w, h)
    incoming_max = float(layout.get("incoming_max_x") or 0.48)
    outgoing_min = float(layout.get("outgoing_min_x") or 0.52)
    source = parse_chat(items, w, incoming_max, outgoing_min)
    if not source:
        phone.back()
        return {"found": True, "contact": contact, "source": "", "detail": "点进会话但没有识别到气泡文字"}
    return {
        "found": True,
        "contact": contact,
        "source": source,
        "image": chat,
        "phone": phone,
        "detail": "已识别会话",
    }
