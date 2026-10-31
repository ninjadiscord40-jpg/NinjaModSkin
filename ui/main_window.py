import json
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QSettings
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QProgressBar, QTextEdit, QStackedWidget,
    QMessageBox, QFrame
)
from core import AppCore, AppError

ROOT = Path(__file__).resolve().parents[1]

STYLE = """
QWidget { background:#0b1020; color:#e8edf8; font-family:'Segoe UI'; font-size:14px; }
QFrame#panel { background:#131c30; border:1px solid #253451; border-radius:16px; }
QLabel#brand { font-size:27px; font-weight:800; color:#ffffff; }
QLabel#sub { color:#9eacc6; }
QLineEdit { background:#0c1426; border:1px solid #30415f; border-radius:9px; padding:12px; color:white; }
QLineEdit:focus { border:1px solid #6d8cff; }
QPushButton { background:#536dfe; border:0; border-radius:10px; padding:12px 18px; color:white; font-weight:700; }
QPushButton:hover { background:#6c82ff; }
QPushButton:disabled { background:#39445d; color:#9ba6bb; }
QPushButton#secondary { background:#24334f; }
QProgressBar { background:#0c1426; border:0; border-radius:6px; height:12px; text-align:center; }
QProgressBar::chunk { background:#5b7cfa; border-radius:6px; }
QTextEdit { background:#0c1426; border:1px solid #263754; border-radius:9px; padding:8px; color:#cbd6eb; }
QCheckBox { color:#aebbd2; spacing:8px; }
"""


class Worker(QThread):
    progress = Signal(str)
    done = Signal(bool, str)

    def __init__(self, task, *args):
        super().__init__()
        self.task = task
        self.args = args

    def run(self):
        try:
            result = self.task(*self.args, log=self.progress.emit)
            self.done.emit(True, result or "تمت العملية بنجاح.")
        except Exception as exc:
            self.done.emit(False, str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ninja ModSkin")
        self.setMinimumSize(570, 650)
        self.setStyleSheet(STYLE)
        self.core = AppCore(ROOT / "config.json")
        self.settings = QSettings()
        self.worker = None
        self._build_ui()
        self._try_saved_session()

    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)

        header = QVBoxLayout()
        brand = QLabel("NINJA MODSKIN")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignCenter)
        sub = QLabel("Secure launcher • Online verification")
        sub.setObjectName("sub")
        sub.setAlignment(Qt.AlignCenter)
        header.addWidget(brand)
        header.addWidget(sub)
        outer.addLayout(header)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        self.login_page = QFrame()
        self.login_page.setObjectName("panel")
        login = QVBoxLayout(self.login_page)
        login.setContentsMargins(26, 28, 26, 28)
        login.setSpacing(14)
        title = QLabel("تسجيل الدخول")
        title.setStyleSheet("font-size:21px;font-weight:700")
        title.setAlignment(Qt.AlignCenter)
        self.username = QLineEdit()
        self.username.setPlaceholderText("اسم المستخدم")
        self.password = QLineEdit()
        self.password.setPlaceholderText("كلمة المرور")
        self.password.setEchoMode(QLineEdit.Password)
        self.remember = QCheckBox("تذكر تسجيل الدخول على هذا الجهاز")
        self.login_button = QPushButton("تسجيل الدخول")
        self.login_button.clicked.connect(self._login)
        self.login_status = QLabel("يلزم اتصال بالإنترنت للتحقق من الحساب.")
        self.login_status.setObjectName("sub")
        self.login_status.setWordWrap(True)
        login.addWidget(title)
        login.addSpacing(8)
        login.addWidget(self.username)
        login.addWidget(self.password)
        login.addWidget(self.remember)
        login.addWidget(self.login_button)
        login.addWidget(self.login_status)
        login.addStretch()
        self.stack.addWidget(self.login_page)

        self.home_page = QFrame()
        self.home_page.setObjectName("panel")
        home = QVBoxLayout(self.home_page)
        home.setContentsMargins(24, 24, 24, 24)
        home.setSpacing(14)
        ready_title = QLabel("البرنامج جاهز")
        ready_title.setAlignment(Qt.AlignCenter)
        ready_title.setStyleSheet("font-size:23px;font-weight:800")
        self.ready_label = QLabel("سجّل الدخول لتحميل ملفات التشغيل والتحقق منها.")
        self.ready_label.setAlignment(Qt.AlignCenter)
        self.ready_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.action_button = QPushButton("جاهز")
        self.action_button.clicked.connect(self._run_mod)
        self.refresh_button = QPushButton("التحقق من الملفات / تنزيلها")
        self.refresh_button.setObjectName("secondary")
        self.refresh_button.clicked.connect(self._prepare)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(170)
        self.logout_button = QPushButton("تسجيل الخروج")
        self.logout_button.setObjectName("secondary")
        self.logout_button.clicked.connect(self._logout)
        home.addWidget(ready_title)
        home.addWidget(self.ready_label)
        home.addWidget(self.progress)
        home.addWidget(self.action_button)
        home.addWidget(self.refresh_button)
        home.addWidget(self.log, 1)
        home.addWidget(self.logout_button)
        self.stack.addWidget(self.home_page)
        self.setCentralWidget(central)

    def _append(self, text):
        self.log.append(text)

    def _set_busy(self, busy, message=None):
        for widget in (self.login_button, self.action_button, self.refresh_button, self.logout_button):
            widget.setEnabled(not busy)
        self.progress.setVisible(busy)
        if message:
            self.ready_label.setText(message)

    def _start_worker(self, task, *args):
        self._set_busy(True)
        self.worker = Worker(task, *args)
        self.worker.progress.connect(self._append)
        self.worker.done.connect(self._worker_done)
        self.worker.start()

    def _worker_done(self, ok, message):
        self._set_busy(False)
        self._append(("✓ " if ok else "✕ ") + message)
        self.ready_label.setText(message)
        if not ok:
            QMessageBox.warning(self, "Ninja ModSkin", message)

    def _login(self):
        user = self.username.text().strip()
        password = self.password.text()
        if not user or not password:
            self.login_status.setText("اكتب اسم المستخدم وكلمة المرور أولاً.")
            return
        self.login_button.setEnabled(False)
        self.login_status.setText("جارٍ التحقق من الحساب عبر الإنترنت...")
        self.worker = Worker(self.core.login, user, password)
        self.worker.done.connect(self._login_done)
        self.worker.start()

    def _login_done(self, ok, message):
        self.login_button.setEnabled(True)
        if not ok:
            self.login_status.setText(message)
            QMessageBox.warning(self, "تعذر تسجيل الدخول", message)
            return
        token = message
        if self.remember.isChecked():
            self.settings.setValue("session_token", token)
        self.core.set_token(token)
        self.stack.setCurrentWidget(self.home_page)
        self._append("تم التحقق من الحساب بنجاح.")
        self._prepare()

    def _try_saved_session(self):
        token = self.settings.value("session_token", "")
        if token:
            self.login_status.setText("جارٍ التحقق من الجلسة المحفوظة عبر الإنترنت...")
            self.login_button.setEnabled(False)
            self.worker = Worker(self.core.validate_token, token)
            self.worker.done.connect(self._saved_session_done)
            self.worker.start()

    def _saved_session_done(self, ok, message):
        self.login_button.setEnabled(True)
        if ok:
            self.core.set_token(message)
            self.stack.setCurrentWidget(self.home_page)
            self._append("تم تجديد التحقق من الجلسة المحفوظة.")
            self._prepare()
        else:
            self.settings.remove("session_token")
            self.login_status.setText("انتهت الجلسة. سجّل الدخول من جديد.")

    def _prepare(self):
        self._append("بدء فحص الاتصال وتجهيز الملفات...")
        self._start_worker(self.core.prepare_payload)

    def _run_mod(self):
        answer = QMessageBox.question(
            self, "تأكيد التشغيل",
            "سيتم استخدام ADB لإرسال ملف التعديل إلى GameLoop ثم محاولة تشغيل اللعبة.\n\nتأكد من أن هذا التعديل مسموح ومتوافق مع شروط اللعبة. هل تريد المتابعة؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer == QMessageBox.Yes:
            self._start_worker(self.core.apply_patch)

    def _logout(self):
        self.settings.remove("session_token")
        self.core.set_token("")
        self.stack.setCurrentWidget(self.login_page)
        self.password.clear()
        self.login_status.setText("تم تسجيل الخروج. يلزم الاتصال بالإنترنت عند الدخول مجدداً.")
