import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

APP_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "NinjaModSkin"
DATA_DIR = APP_DIR / "Data"


class AppError(Exception):
    pass


class AppCore:
    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.token = ""
        APP_DIR.mkdir(parents=True, exist_ok=True)

    def set_token(self, token):
        self.token = token or ""

    def _url(self, suffix):
        base = self.config.get("auth_api_url", "").rstrip("/")
        if not base or "YOUR-AUTH-SERVICE" in base:
            raise AppError("خدمة تسجيل الدخول لم يتم إعدادها بعد. سنربطها معك بعد إنشاء مستودع GitHub.")
        return base + suffix

    def login(self, username, password, log=lambda x: None):
        try:
            response = requests.post(
                self._url("/login"),
                json={"username": username, "password": password, "device": os.environ.get("COMPUTERNAME", "Windows-PC")},
                timeout=20
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok") or not data.get("token"):
                raise AppError(data.get("message", "بيانات الدخول غير صحيحة أو الحساب غير مفعل."))
            return data["token"]
        except requests.RequestException as exc:
            raise AppError("تعذر الاتصال بخدمة التحقق. تأكد من الإنترنت وحاول مجدداً.") from exc

    def validate_token(self, token, log=lambda x: None):
        try:
            response = requests.get(
                self._url("/validate"), headers={"Authorization": f"Bearer {token}"}, timeout=20
            )
            response.raise_for_status()
            data = response.json()
            if data.get("ok"):
                return token
            raise AppError(data.get("message", "الجلسة غير صالحة. سجّل الدخول مجدداً."))
        except requests.RequestException as exc:
            raise AppError("لا يمكن التحقق من الجلسة دون إنترنت.") from exc

    def _check_online(self):
        try:
            requests.get("https://api.github.com", timeout=12).raise_for_status()
        except requests.RequestException as exc:
            raise AppError("لا يوجد اتصال إنترنت. لن يتم تنزيل الملفات أو تشغيل الإجراء.") from exc

    def prepare_payload(self, log=lambda x: None):
        self._check_online()
        if not self.token:
            raise AppError("انتهت الجلسة. سجّل الدخول مرة أخرى.")
        self.validate_token(self.token)
        adb = DATA_DIR / "adb.exe"
        pak = DATA_DIR / "ModSkin" / self.config["payload_filename"]
        if adb.exists() and pak.exists():
            log("تم العثور على ملفات البرنامج المحلية.")
            return "الملفات موجودة وتم التحقق من الاتصال والترخيص. اضغط جاهز للمتابعة."
        url = self.config.get("payload_url", "")
        if not url or "YOUR-USERNAME" in url:
            raise AppError("رابط ملفات GitHub غير مضبوط. سنضعه بعد إنشاء المستودع وإصدار Release.")
        log("تنزيل حزمة التشغيل من GitHub...")
        archive = APP_DIR / "modskin_payload.zip"
        try:
            with requests.get(url, stream=True, timeout=(20, 180)) as response:
                response.raise_for_status()
                with archive.open("wb") as output:
                    for chunk in response.iter_content(1024 * 256):
                        if chunk:
                            output.write(chunk)
            expected = self.config.get("payload_sha256", "").strip().lower()
            if expected:
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                if digest.lower() != expected:
                    archive.unlink(missing_ok=True)
                    raise AppError("فشل التحقق من سلامة الحزمة التي تم تنزيلها.")
            temp = APP_DIR / "extract_tmp"
            shutil.rmtree(temp, ignore_errors=True)
            temp.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as zf:
                for item in zf.infolist():
                    target = (temp / item.filename).resolve()
                    if not str(target).startswith(str(temp.resolve()) + os.sep):
                        raise AppError("الحزمة تحتوي على مسار غير آمن.")
                zf.extractall(temp)
            extracted_data = temp / "Data"
            if not (extracted_data / "adb.exe").exists() or not (extracted_data / "ModSkin" / self.config["payload_filename"]).exists():
                raise AppError("الحزمة لا تحتوي على ملفات Data المطلوبة.")
            shutil.rmtree(DATA_DIR, ignore_errors=True)
            shutil.copytree(extracted_data, DATA_DIR)
            shutil.rmtree(temp, ignore_errors=True)
            archive.unlink(missing_ok=True)
            log("اكتمل التنزيل وفحص الملفات.")
            return "تم تنزيل الملفات وتجهيزها بنجاح. اضغط جاهز للمتابعة."
        except requests.RequestException as exc:
            raise AppError("فشل تنزيل الملفات من GitHub. تحقق من الرابط والإنترنت.") from exc

    def _run_adb(self, args, timeout=35):
        adb = DATA_DIR / "adb.exe"
        if not adb.exists():
            raise AppError("ملف ADB غير موجود. اضغط التحقق من الملفات / تنزيلها.")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run([str(adb), *args], capture_output=True, text=True, timeout=timeout, creationflags=flags)
        except subprocess.TimeoutExpired as exc:
            raise AppError("انتهت مهلة تنفيذ ADB. تحقق من تشغيل GameLoop.") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "ADB returned an error").strip()
            raise AppError(f"فشل أمر ADB: {detail[:500]}")
        return result.stdout.strip()

    def apply_patch(self, log=lambda x: None):
        self._check_online()
        if not self.token:
            raise AppError("انتهت الجلسة. سجّل الدخول مرة أخرى.")
        self.validate_token(self.token)
        adb = DATA_DIR / "adb.exe"
        pak = DATA_DIR / "ModSkin" / self.config["payload_filename"]
        if not adb.exists() or not pak.exists():
            raise AppError("ملفات التشغيل غير مكتملة. اضغط تنزيل الملفات أولاً.")
        log("بدء خدمة ADB...")
        self._run_adb(["start-server"])
        devices = self._run_adb(["devices"])
        connected = [line.split()[0] for line in devices.splitlines()[1:] if len(line.split()) >= 2 and line.split()[1] == "device"]
        if not connected:
            raise AppError("لم يتم العثور على جهاز GameLoop عبر ADB. افتح GameLoop وتأكد من تفعيل ADB.")
        pkg = self.config["package_name"]
        dest_dir = self.config["destination_dir"]
        dest_file = dest_dir.rstrip("/") + "/" + self.config["payload_filename"]
        log("تم العثور على جهاز. تجهيز مجلد الوجهة...")
        self._run_adb(["shell", "am", "force-stop", pkg])
        self._run_adb(["shell", "mkdir", "-p", dest_dir])
        log("إرسال الملف إلى الجهاز...")
        self._run_adb(["push", str(pak), dest_file], timeout=180)
        log("التحقق من وجود الملف...")
        self._run_adb(["shell", "ls", "-l", dest_file])
        log("محاولة تشغيل اللعبة...")
        self._run_adb(["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"])
        self._run_adb(["kill-server"])
        return "اكتملت العملية. إذا لم تعمل اللعبة، راجع توافق ملف التعديل وإعدادات GameLoop."
