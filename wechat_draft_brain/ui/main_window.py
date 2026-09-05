from __future__ import annotations

from datetime import datetime
from sqlite3 import Error as SQLiteError

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from wechat_draft_brain.brain import SCENE_LABELS
from wechat_draft_brain.config import (
    CAPTURE_CHOICES,
    THEME_CHOICES,
    load_config,
    load_config_result,
    normalize_theme,
    save_user_settings,
)
from wechat_draft_brain.paths import LAST_SHOT, USER_CONFIG, DATA_DIR, icon_path
from wechat_draft_brain.pipeline import (
    clear_local_history,
    ingest_text,
    reload_config,
    restart_hotkeys,
)
from wechat_draft_brain.store import init_db, list_drafts, list_events, update_draft

_THEME_COLORS = {
    "dark": {
        "bg": "#14110e",
        "paper": "#1c1813",
        "ink": "#efe6d4",
        "mute": "#9a8f7c",
        "line": "#3a332a",
        "input": "#12100d",
        "accent": "#c9d4a2",
        "accent_ink": "#0b0907",
        "danger": "#d45b3e",
        "shot": "#0d0b09",
    },
    "light": {
        "bg": "#f3eee6",
        "paper": "#fffdf8",
        "ink": "#1c1813",
        "mute": "#6f675c",
        "line": "#d4cbbe",
        "input": "#ffffff",
        "accent": "#5e6b38",
        "accent_ink": "#f7f4ea",
        "danger": "#c4452f",
        "shot": "#ece6db",
    },
}

_STYLE_TEMPLATE = """
QMainWindow, QDialog, QWidget#root {{
  background: {bg};
  color: {ink};
  font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
  font-size: 13px;
}}
QLabel {{ color: {ink}; }}
QLabel#kicker {{
  color: {mute};
  letter-spacing: 3px;
  font-size: 11px;
}}
QLabel#title {{
  font-size: 28px;
  font-weight: 400;
  letter-spacing: 4px;
}}
QLabel#mute, QLabel#meta, QLabel#fine {{ color: {mute}; }}
QLabel#risk {{ color: {danger}; }}
QLabel#shot {{
  color: {mute};
  background: {shot};
  border: 1px solid {line};
}}
QFrame#card, QFrame#panel, QFrame#stat {{
  background: {paper};
  border: 1px solid {line};
}}
QTextEdit, QLineEdit, QComboBox {{
  background: {input};
  color: {ink};
  border: 1px solid {line};
  padding: 8px;
  selection-background-color: {line};
}}
QComboBox QAbstractItemView {{
  background: {paper};
  color: {ink};
  selection-background-color: {line};
}}
QPushButton {{
  background: {input};
  color: {ink};
  border: 1px solid {line};
  padding: 8px 12px;
}}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton#primary {{
  background: {accent};
  color: {accent_ink};
  border: 0;
  font-weight: 600;
}}
QPushButton#ghost {{ color: {mute}; }}
QFrame#card QPushButton {{
  text-align: left;
}}
QListWidget {{
  background: {paper};
  color: {mute};
  border: 0;
  font-size: 12px;
}}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{
  background: {bg};
  width: 10px;
  border: 0;
}}
QScrollBar::handle:vertical {{ background: {line}; min-height: 24px; }}
QMenu {{
  background: {paper};
  color: {ink};
  border: 1px solid {line};
}}
QMenu::item:selected {{ background: {line}; }}
QDialogButtonBox QPushButton {{
  min-width: 72px;
}}
"""


def stylesheet_for(theme: str | None = None) -> str:
    key = normalize_theme(theme)
    return _STYLE_TEMPLATE.format(**_THEME_COLORS[key])


def apply_theme(theme: str | None = None) -> str:
    theme = normalize_theme(theme if theme is not None else load_config().get("theme"))
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(stylesheet_for(theme))
    return theme


class Worker(QThread):
    ok = Signal(object)
    fail = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.ok.emit(self._fn())
        except Exception as e:
            self.fail.emit(str(e))


class SettingsDialog(QDialog):
    history_cleared = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(440)
        config_result = load_config_result()
        cfg = config_result.config
        llm = cfg.get("llm") or {}
        form = QFormLayout(self)
        self.hotkey = QLineEdit(str(cfg.get("hotkey") or "<ctrl>+<alt>+w"))
        self.capture = QComboBox()
        current_capture = cfg.get("capture") or "ocr"
        for value, label in CAPTURE_CHOICES:
            self.capture.addItem(label, value)
        idx = self.capture.findData(current_capture)
        self.capture.setCurrentIndex(idx if idx >= 0 else 0)
        self.theme = QComboBox()
        current_theme = cfg.get("theme") or "dark"
        for value, label in THEME_CHOICES:
            self.theme.addItem(label, value)
        tidx = self.theme.findData(current_theme)
        self.theme.setCurrentIndex(tidx if tidx >= 0 else 0)
        self.base_url = QLineEdit(str(llm.get("base_url") or ""))
        self.api_key = QLineEdit(str(llm.get("api_key") or ""))
        self.api_key.setEchoMode(QLineEdit.Password)
        self.model = QLineEdit(str(llm.get("model") or "gpt-4o-mini"))
        privacy = cfg.get("privacy") or {}
        self.save_source_text = QCheckBox("在草稿库中保存聊天原文")
        self.save_source_text.setChecked(bool(privacy.get("save_source_text", True)))
        self.save_last_screenshot = QCheckBox("保存最近一次 OCR 截图")
        self.save_last_screenshot.setChecked(
            bool(privacy.get("save_last_screenshot", True))
        )
        self.clear_history_btn = QPushButton("清除草稿、日志和截图…")
        self.clear_history_btn.setObjectName("ghost")
        self.clear_history_btn.clicked.connect(self.clear_history_data)
        hint = QLabel(f"密钥只存在本机\n{USER_CONFIG}")
        hint.setObjectName("fine")
        hint.setWordWrap(True)
        form.addRow("快捷键", self.hotkey)
        form.addRow("快捷键读取", self.capture)
        form.addRow("外观", self.theme)
        form.addRow("接口地址", self.base_url)
        form.addRow("API Key", self.api_key)
        form.addRow("模型", self.model)
        form.addRow("聊天原文", self.save_source_text)
        form.addRow("末帧截图", self.save_last_screenshot)
        form.addRow("本地历史", self.clear_history_btn)
        if config_result.warnings:
            warning = QLabel("\n".join(config_result.warnings))
            warning.setObjectName("risk")
            warning.setWordWrap(True)
            form.addRow("配置警告", warning)
        form.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def apply(self) -> None:
        save_user_settings(
            hotkey=self.hotkey.text(),
            api_key=self.api_key.text(),
            base_url=self.base_url.text(),
            model=self.model.text(),
            capture=str(self.capture.currentData() or "ocr"),
            theme=str(self.theme.currentData() or "dark"),
            save_source_text=self.save_source_text.isChecked(),
            save_last_screenshot=self.save_last_screenshot.isChecked(),
        )
        reload_config()
        restart_hotkeys()
        apply_theme()

    def clear_history_data(self) -> None:
        answer = QMessageBox.question(
            self,
            "清除本地历史",
            "将删除草稿、聊天原文、事件日志、快捷键去重记录和末帧截图。设置与 API Key 会保留。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            removed = clear_local_history()
        except (OSError, SQLiteError) as exc:
            QMessageBox.warning(self, "夜班台", f"清理失败：{exc}")
            return
        self.history_cleared.emit()
        QMessageBox.information(
            self,
            "夜班台",
            f"已清除 {removed['drafts']} 条草稿和 {removed['events']} 条日志。",
        )


class DraftCard(QFrame):
    changed = Signal()

    def __init__(self, row: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self.row = row
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        scene = SCENE_LABELS.get(row.get("scene") or "", row.get("scene") or "")
        source_label = {
            "llm": "模型草稿",
            "rules": "规则草稿",
            "none": "未生成草稿",
        }.get(row.get("generation_source"), "规则草稿")
        meta = QLabel(
            f"#{row.get('id')} · {row.get('contact') or '未知'} · {scene} · "
            f"{source_label} · {row.get('status')}"
        )
        meta.setObjectName("meta")
        layout.addWidget(meta)
        reason = QLabel(row.get("reason") or "")
        reason.setWordWrap(True)
        reason.setObjectName("risk" if row.get("risks") else "mute")
        layout.addWidget(reason)
        fallback_reason = row.get("fallback_reason") or ""
        if fallback_reason:
            fallback = QLabel(f"模型已降级：{fallback_reason}")
            fallback.setObjectName("risk")
            fallback.setWordWrap(True)
            layout.addWidget(fallback)
        src = (row.get("source_text") or "")[:280]
        if src:
            preview = QLabel(src)
            preview.setObjectName("mute")
            preview.setWordWrap(True)
            layout.addWidget(preview)
        for text in row.get("drafts") or []:
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, t=text: self.copy_text(t))
            layout.addWidget(btn)
        dismiss = QPushButton("丢掉")
        dismiss.setObjectName("ghost")
        dismiss.clicked.connect(self.dismiss)
        layout.addWidget(dismiss, alignment=Qt.AlignLeft)

    def copy_text(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        update_draft(int(self.row["id"]), status="copied", chosen_text=text)
        self.changed.emit()

    def dismiss(self) -> None:
        update_draft(int(self.row["id"]), status="dismissed")
        self.changed.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("夜班台")
        self.resize(1180, 760)
        ico = icon_path()
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))
        self._worker: Worker | None = None
        self._stamp = None
        self._last_id = 0
        self._ready = False
        self._really_quit = False
        init_db()

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        kicker = QLabel("NIGHT DESK")
        kicker.setObjectName("kicker")
        title = QLabel("夜班台")
        title.setObjectName("title")
        titles.addWidget(kicker)
        titles.addWidget(title)
        header.addLayout(titles)
        header.addStretch()
        self.settings_btn = QPushButton("设置")
        self.settings_btn.clicked.connect(self.open_settings)
        header.addWidget(self.settings_btn, alignment=Qt.AlignBottom)
        outer.addLayout(header)

        stats = QHBoxLayout()
        self.hint = self._stat("快捷键拟稿", "Ctrl+Alt+W 只 OCR 当前窗口")
        self.model_line = self._stat("模型", "规则拟稿")
        stats.addWidget(self.hint)
        stats.addWidget(self.model_line)
        outer.addLayout(stats)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._compose_panel())
        split.addWidget(self._queue_panel())
        split.addWidget(self._side_panel())
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 5)
        split.setStretchFactor(2, 4)
        outer.addWidget(split, 1)

        self._setup_tray()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()
        self._ready = True

    def _stat(self, title: str, body: str) -> QFrame:
        box = QFrame()
        box.setObjectName("stat")
        lay = QVBoxLayout(box)
        head = QLabel(title)
        head.setObjectName("meta")
        self_body = QLabel(body)
        self_body.setObjectName("mute")
        self_body.setWordWrap(True)
        lay.addWidget(head)
        lay.addWidget(self_body)
        box.body = self_body  # type: ignore[attr-defined]
        return box

    def _compose_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        lay = QVBoxLayout(panel)
        lay.addWidget(QLabel("丢一段对话进来"))
        self.source = QTextEdit()
        self.source.setPlaceholderText("对方: 今晚还出不出来\n我: 我看一下")
        lay.addWidget(self.source, 1)
        row = QHBoxLayout()
        self.contact = QLineEdit()
        self.contact.setPlaceholderText("联系人（可选）")
        self.draft_btn = QPushButton("生成草稿")
        self.draft_btn.setObjectName("primary")
        self.draft_btn.clicked.connect(self.on_draft)
        row.addWidget(self.contact)
        row.addWidget(self.draft_btn)
        lay.addLayout(row)
        fine = QLabel("把微信置于前台，按 Ctrl+Alt+W。默认只 OCR 聊天区，不读剪贴板。点一条草稿即复制。")
        fine.setObjectName("fine")
        fine.setWordWrap(True)
        lay.addWidget(fine)
        return panel

    def _queue_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        lay = QVBoxLayout(panel)
        lay.addWidget(QLabel("待确认"))
        self.queue_host = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_host)
        self.queue_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.queue_host)
        lay.addWidget(scroll, 1)
        return panel

    def _side_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        lay = QVBoxLayout(panel)
        lay.addWidget(QLabel("末帧"))
        self.shot = QLabel("还没有截屏")
        self.shot.setObjectName("shot")
        self.shot.setAlignment(Qt.AlignCenter)
        self.shot.setMinimumHeight(160)
        self.shot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self.shot, 1)
        lay.addWidget(QLabel("日志"))
        self.log = QListWidget()
        lay.addWidget(self.log, 1)
        return panel

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = QSystemTrayIcon(self)
        ico = icon_path()
        if ico.exists():
            self.tray.setIcon(QIcon(str(ico)))
        else:
            self.tray.setIcon(self.windowIcon())
        self.tray.setToolTip("夜班台")
        menu = QMenu()
        show_act = QAction("打开夜班台", self)
        show_act.triggered.connect(self.show_window)
        quit_act = QAction("退出", self)
        quit_act.triggered.connect(self.quit_app)
        menu.addAction(show_act)
        menu.addAction(quit_act)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def open_settings(self) -> None:
        dlg = SettingsDialog(self)
        dlg.history_cleared.connect(lambda: self.refresh(force=True))
        if dlg.exec() == QDialog.Accepted:
            try:
                dlg.apply()
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "夜班台", str(exc))
                return
            self.refresh(force=True)
            QMessageBox.information(self, "夜班台", "设置已保存。密钥只写在本机用户目录。")

    def on_draft(self) -> None:
        text = self.source.toPlainText().strip()
        if not text:
            return
        contact = self.contact.text().strip()
        self.draft_btn.setEnabled(False)
        self.draft_btn.setText("拟稿中…")
        self._worker = Worker(lambda: ingest_text(text, contact=contact, mode="copilot"))
        self._worker.ok.connect(self._draft_ok)
        self._worker.fail.connect(self._draft_fail)
        self._worker.start()

    def _draft_ok(self, payload: dict) -> None:
        self.draft_btn.setEnabled(True)
        self.draft_btn.setText("生成草稿")
        self.source.clear()
        self.refresh(force=True)
        if not payload.get("ok", True) and payload.get("error"):
            QMessageBox.warning(self, "夜班台", payload["error"])

    def _draft_fail(self, message: str) -> None:
        self.draft_btn.setEnabled(True)
        self.draft_btn.setText("生成草稿")
        QMessageBox.warning(self, "夜班台", message)

    def refresh(self, force: bool = False) -> None:
        from wechat_draft_brain.pipeline import current_flags

        flags = current_flags()
        capture = flags.get("capture") or "ocr"
        if capture == "clipboard":
            hint = f"{flags['hotkey']} 只读剪贴板，只出草稿不发送。"
        elif capture == "both":
            hint = f"{flags['hotkey']} 先 OCR 窗口，没有字再用剪贴板。"
        else:
            hint = f"{flags['hotkey']} 只 OCR 当前窗口聊天区，不读剪贴板。"
        self.hint.body.setText(hint)
        self.model_line.body.setText(
            flags["model"] if flags["llm_ready"] else "未配置 API Key，走规则拟稿"
        )
        drafts = list_drafts(40)
        events = list_events(30)
        shot_mtime = LAST_SHOT.stat().st_mtime if LAST_SHOT.exists() else 0
        stamp = (
            tuple((d["id"], d["status"]) for d in drafts),
            tuple(e["id"] for e in events),
            shot_mtime,
            flags["hotkey"],
            flags["llm_ready"],
            flags["model"],
            flags.get("capture"),
        )
        newest = drafts[0]["id"] if drafts else 0
        if self._ready and newest > self._last_id and drafts and drafts[0].get("status") == "pending":
            n = len(drafts[0].get("drafts") or [])
            if self.tray:
                self.tray.showMessage("夜班台", f"已拟 {n} 条草稿", QSystemTrayIcon.Information, 2500)
        if newest:
            self._last_id = newest
        if not force and stamp == self._stamp:
            return
        self._stamp = stamp
        self._render_queue(drafts)
        self._render_log(events)
        self._render_shot()

    def _render_queue(self, drafts: list[dict]) -> None:
        while self.queue_layout.count() > 1:
            item = self.queue_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not drafts:
            empty = QLabel("还没有草稿")
            empty.setObjectName("mute")
            self.queue_layout.insertWidget(0, empty)
            return
        for row in drafts:
            card = DraftCard(row)
            card.changed.connect(lambda: self.refresh(force=True))
            self.queue_layout.insertWidget(self.queue_layout.count() - 1, card)

    def _render_log(self, events: list[dict]) -> None:
        self.log.clear()
        for e in events:
            t = datetime.fromtimestamp(e["created_at"]).strftime("%H:%M:%S")
            QListWidgetItem(f"{t}  {e['message']}", self.log)

    def _render_shot(self) -> None:
        if not LAST_SHOT.exists():
            self.shot.setPixmap(QPixmap())
            self.shot.setText("还没有截屏")
            return
        pix = QPixmap(str(LAST_SHOT))
        if pix.isNull():
            self.shot.setText("截屏无法显示")
            return
        self.shot.setText("")
        self.shot.setPixmap(
            pix.scaled(self.shot.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if LAST_SHOT.exists():
            self._render_shot()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.tray and not self._really_quit:
            event.ignore()
            self.hide()
            self.tray.showMessage("夜班台", "仍在托盘运行，快捷键可用。", QSystemTrayIcon.Information, 2000)
            return
        event.accept()

    def quit_app(self) -> None:
        self._really_quit = True
        QApplication.quit()


def run() -> int:
    import sys

    from PySide6.QtCore import QLockFile

    from wechat_draft_brain.pipeline import start_background, stop_background

    app = QApplication(sys.argv)
    app.setApplicationName("夜班台")
    app.setQuitOnLastWindowClosed(False)
    apply_theme()
    ico = icon_path()
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))

    lock = QLockFile(str(DATA_DIR / "instance.lock"))
    lock.setStaleLockTime(15000)
    if not lock.tryLock(100):
        QMessageBox.information(None, "夜班台", "夜班台已经在运行。")
        return 0

    start_background()
    win = MainWindow()
    win.show()
    code = app.exec()
    stop_background()
    lock.unlock()
    return int(code)
