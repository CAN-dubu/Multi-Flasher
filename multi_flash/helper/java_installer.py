"""JRE auto-install helper."""
import os
import shutil
import subprocess
import tempfile
import urllib.request
from urllib.parse import quote
import zipfile

_JRE_VERSION = "17"
_JRE_BUILD = "17.0.13+11"
_JRE_BUILD_FILE = _JRE_BUILD.replace("+", "_")
_JRE_ARCH = "x64"
_PLATFORM = "windows"
_JRE_TYPE = "jre"
_FILENAME = f"OpenJDK{_JRE_VERSION}U-{_JRE_TYPE}_{_JRE_ARCH}_{_PLATFORM}_hotspot_{_JRE_BUILD_FILE}.zip"
_TAG = f"jdk-{quote(_JRE_BUILD, safe='')}"
_DOWNLOAD_URL = f"https://github.com/adoptium/temurin{_JRE_VERSION}-binaries/releases/download/{_TAG}/{_FILENAME}"
_INSTALL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
_JRE_HOME = os.path.join(_INSTALL_DIR, f"jdk-{_JRE_BUILD}-jre")
_JAVA_EXE = os.path.join(_JRE_HOME, "bin", "java.exe")


def _can_run_java(java_exe: str) -> bool:
    try:
        result = subprocess.run(
            [java_exe, "-version"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


def _system_java_exe() -> str | None:
    java = shutil.which("java")
    if java and _can_run_java(java):
        return java
    return None


def _check_java() -> bool:
    return os.path.exists(_JAVA_EXE) or _system_java_exe() is not None


def get_java_path() -> str:
    """Return the bundled JRE home path."""
    return _JRE_HOME


def get_java_exe() -> str:
    """Return a runnable java executable path or command."""
    if os.path.exists(_JAVA_EXE):
        return _JAVA_EXE
    system_java = _system_java_exe()
    if system_java:
        return system_java
    return _JAVA_EXE


def ensure_jre(progress_callback=None) -> bool:
    """Install bundled JRE when no bundled or system Java is available."""
    if progress_callback:
        progress_callback(f"[INFO] Java check... URL: {_DOWNLOAD_URL}")

    if os.path.exists(_JAVA_EXE):
        if progress_callback:
            progress_callback(f"[OK] Bundled Java available: {_JAVA_EXE}")
        return True

    system_java = _system_java_exe()
    if system_java:
        if progress_callback:
            progress_callback(f"[OK] System Java available: {system_java}")
        return True

    if progress_callback:
        progress_callback("[INFO] Java not found. Installing JRE 17...")

    tmp_path = None
    try:
        os.makedirs(_INSTALL_DIR, exist_ok=True)

        if progress_callback:
            progress_callback(f"[INFO] Downloading JRE... {_DOWNLOAD_URL}")

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip")
        os.close(tmp_fd)

        urllib.request.urlretrieve(_DOWNLOAD_URL, tmp_path)

        if progress_callback:
            progress_callback("[INFO] Extracting JRE...")

        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(_INSTALL_DIR)

        if progress_callback:
            progress_callback("[INFO] Verifying installation...")

        if os.path.exists(_JAVA_EXE) and _can_run_java(_JAVA_EXE):
            if progress_callback:
                progress_callback("[OK] JRE installed successfully.")
            return True

        if progress_callback:
            progress_callback(f"[ERROR] JRE installation failed - java.exe not found: {_JAVA_EXE}")
        return False

    except Exception as e:
        if progress_callback:
            progress_callback(f"[ERROR] JRE install failed: {e}")
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
