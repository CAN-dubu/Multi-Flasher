"""STLink V2/V2-1 firmware update worker.

JAR limitation: STLinkUpgrade.jar does not accept a device target argument
(serial, path, or index). It always enumerates connected ST-LINKs and
updates the FIRST one it finds. This worker therefore requires that
exactly ONE ST-LINK V2/V2-1 device is connected before flash_all() is called.
Multiple connected devices are NOT safe to pass to this worker.
"""
import subprocess
import os
import time
import threading
from typing import List, Callable, Optional

from .stlink_detector import StlinkDevice

# V2/V2-1 target PIDs only
_TARGET_PIDS = {"3748", "374b", "374d"}
# Always skip
_SKIP_PIDS = {"3744", "572a"}
# V3 skip
_V3_PIDS = {"374e", "374f", "3752", "3753", "3754"}

_JAR_ARGS_V2 = ["-force_prog", "-jtag_swim"]  # 3748
_JAR_ARGS_V2_1 = ["-force_prog"]              # 374b, 374d

_jar_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "lib", "stlink_tools", "AllPlatforms", "STLinkUpgrade.jar"
)

_TIMEOUT_SECONDS = 180


def _jar_args(pid: str) -> List[str]:
    if pid == "3748":
        return _JAR_ARGS_V2
    return _JAR_ARGS_V2_1  # 374b, 374d


def _err_exit_code(rc: int) -> str:
    if rc == -1 or rc == 4294967295:
        return "device not in DFU mode or communication error (WinError -1)"
    return f"exit code {rc}"


def _ensure_jre(log_cb: Callable[[int, str], None]) -> bool:
    from multi_flash.helper.java_installer import ensure_jre, get_java_exe

    def jre_log(msg):
        log_cb(0, msg)

    if not ensure_jre(progress_callback=jre_log):
        log_cb(0, "[ERROR] JRE installation failed.")
        return False

    java_exe = get_java_exe()
    try:
        result = subprocess.run([java_exe, "-version"], capture_output=True, timeout=10)
    except Exception as e:
        log_cb(0, f"[ERROR] Java not runnable: {java_exe} ({e})")
        return False
    if result.returncode != 0:
        log_cb(0, f"[ERROR] Java not runnable: {java_exe}")
        return False

    return True


def _run_jar(
    args: List[str],
    log_cb: Callable[[int, str], None],
    slot_idx: int = 0,
    timeout: int = 60,
    jar_path: Optional[str] = None,
) -> tuple:
    """(ok: bool, rc: int, combined_output: str)"""
    from multi_flash.helper.java_installer import get_java_exe

    java_exe = get_java_exe()
    cmd = [java_exe, "-jar", jar_path or _jar_path] + args

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as e:
        log_cb(slot_idx, f"[ERROR] Executable not found: {java_exe}")
        log_cb(slot_idx, f"[ERROR] Command: {' '.join(cmd)}")
        return False, -1, ""
    except OSError as e:
        log_cb(slot_idx, f"[ERROR] OS error: {e}")
        log_cb(slot_idx, f"[ERROR] Command: {' '.join(cmd)}")
        return False, -1, ""

    start_time = time.time()
    output_lines = []

    def pump_stream(stream):
        for line in iter(stream.readline, ""):
            if not line:
                break
            line = line.strip()
            if line:
                output_lines.append(line)
                log_cb(slot_idx, line)

    t_out = threading.Thread(target=pump_stream, args=(proc.stdout,), daemon=True)
    t_err = threading.Thread(target=pump_stream, args=(proc.stderr,), daemon=True)
    t_out.start()
    t_err.start()

    timed_out = False
    while True:
        ret = proc.poll()
        if ret is not None:
            break
        elapsed = int(time.time() - start_time)
        if elapsed >= timeout:
            proc.kill()
            timed_out = True
            break
        time.sleep(0.5)

    t_out.join(timeout=2)
    t_err.join(timeout=2)

    combined = "\n".join(output_lines)
    rc = proc.returncode

    if timed_out:
        log_cb(slot_idx, f"[ERROR] Timeout after {timeout}s")
        return False, rc, combined

    return True, rc, combined


class StlinkSequentialWorker:
    """STLink V2/V2-1 firmware update worker.

    JAR limitation: STLinkUpgrade.jar does not accept a device target argument
    (serial, path, or index). It always enumerates connected ST-LINKs and
    updates the FIRST one it finds. This worker therefore requires that
    exactly ONE ST-LINK V2/V2-1 device is connected before flash_all() is called.
    Multiple connected devices are NOT safe to pass to this worker.
    """

    def __init__(self, jar_path: Optional[str] = None):
        self._jar_path = jar_path or _jar_path
        if not os.path.exists(self._jar_path):
            self._jar_path = None
        self._slot_index = 0
        self._lock = threading.Lock()
        self._processed_keys: set = set()

    @property
    def jar_path(self) -> Optional[str]:
        return self._jar_path

    @property
    def current_slot(self) -> int:
        return self._slot_index

    def flash_all(
        self,
        devices: List[StlinkDevice],
        log_callback: Callable[[int, str], None],
        progress_callback: Callable[[int, str, str, str], None],
    ):
        """Update firmware for the single ST-LINK device in `devices`.

        IMPORTANT: `devices` must contain exactly ONE device.
        The JAR cannot target a specific device; it always updates the first
        enumerated ST-LINK. Passing multiple devices does NOT update them
        sequentially ??only the first enumerated device will be touched.
        Caller is responsible for ensuring only one ST-LINK is connected.
        """
        if not self._jar_path:
            log_callback(0, "[ERROR] STLinkUpgrade.jar not found.")
            progress_callback(0, "JAR NOT FOUND", "#f87171", "#000000")
            return

        progress_callback(0, "CHECKING_JRE", "#6366f1", "#ffffff")
        if not _ensure_jre(log_callback):
            progress_callback(0, "JRE ERROR", "#f87171", "#000000")
            return

        # Filter to valid targets
        filtered = []
        for dev in devices:
            pid = dev.pid.lower() if dev.pid else ""
            if pid in _SKIP_PIDS:
                log_callback(0, f"[INFO] Skip {dev.model} (PID={pid.upper()}): not a ST-LINK target")
                continue
            if pid in _V3_PIDS:
                log_callback(0, f"[INFO] Skip {dev.model} (PID={pid.upper()}): unsupported for V2 updater")
                continue
            if pid not in _TARGET_PIDS:
                log_callback(0, f"[INFO] Skip {dev.model} (PID={pid.upper()}): not in V2 target PIDs")
                continue
            dedupe_key = f"{dev.vid}:{dev.pid}:{dev.serial}" if dev.serial else dev.instance_id
            if dedupe_key in self._processed_keys:
                continue
            self._processed_keys.add(dedupe_key)
            filtered.append(dev)

        if not filtered:
            log_callback(0, "[WARN] No V2/V2-1 ST-LINK devices found.")
            progress_callback(0, "NO TARGET", "#f87171", "#000000")
            return

        # --- DEFENSE: reject multiple devices ---
        if len(filtered) > 1:
            log_callback(0, "[ERROR] Multiple ST-LINK devices were passed to single-device updater.")
            log_callback(0, "[ERROR] Disconnect all but ONE ST-LINK and retry.")
            for dev in filtered:
                log_callback(0, f"[ERROR]  - {dev.model} PID={dev.pid.upper()} serial={dev.serial}")
            progress_callback(0, "MULTI ERROR", "#f87171", "#000000")
            return

        # Exactly one device ??proceed with update
        log_callback(0, "[INFO] ST-LINK/V2 updater started")
        device = filtered[0]
        slot = 1
        with self._lock:
            self._slot_index = slot

        progress_callback(slot, "UPDATING", "#7aa2f7", "#ffffff")
        result = self._flash_one(slot, device, log_callback, progress_callback)

        if result is True:
            log_callback(0, "[SUMMARY] Success=1, Need DFU=0, Failed=0")
        elif result is None:
            log_callback(0, "[SUMMARY] Success=0, Need DFU=1, Failed=0")
        else:
            log_callback(0, "[SUMMARY] Success=0, Need DFU=0, Failed=1")

    def _flash_one(
        self,
        slot_idx: int,
        device: StlinkDevice,
        log_callback: Callable[[int, str], None],
        progress_callback: Callable[[int, str, str, str], None],
    ) -> bool | None:
        """Update one ST-LINK device.

        Returns:
          True  - successful update
          None  - NEED_DFU (device not in DFU mode)
          False - actual failure
        """
        log_callback(slot_idx, f"[INFO] {device.model} VID={device.vid} PID={device.pid.upper()} serial={device.serial}")
        args = _jar_args(device.pid)
        log_callback(slot_idx, f"[INFO] Exec: java -jar STLinkUpgrade.jar {' '.join(args)}")

        ok, rc, out = _run_jar(args, log_callback, slot_idx, timeout=_TIMEOUT_SECONDS, jar_path=self._jar_path)
        combined = out

        if "Upgrade is successful" in combined:
            if "Failure exiting upgrade mode" in combined:
                log_callback(slot_idx, "[SUCCESS] Firmware upgraded.")
                log_callback(slot_idx, "[WARN] Failed to exit upgrade mode automatically. Please reconnect the ST-LINK.")
                progress_callback(slot_idx, "SUCCESS", "#4ade80", "#000000")
            else:
                log_callback(slot_idx, "[SUCCESS] Firmware updated.")
                progress_callback(slot_idx, "SUCCESS", "#4ade80", "#000000")
            return True

        if "not in the DFU mode" in combined:
            log_callback(slot_idx, "[NEED_DFU] ST-LINK is not in firmware update mode.")
            log_callback(slot_idx, "[NEED_DFU] 1. Disconnect ST-LINK")
            log_callback(slot_idx, "[NEED_DFU] 2. Hold button (V2-1) / reconnect while holding")
            log_callback(slot_idx, "[NEED_DFU] 3. Re-enter DFU mode, then retry")
            progress_callback(slot_idx, "NEED_DFU", "#f59e0b", "#000000")
            return None

        log_callback(slot_idx, f"[FAIL] Upgrade failed: {_err_exit_code(rc)}")
        progress_callback(slot_idx, "FAILED", "#f87171", "#000000")
        return False

    def check_version(self, log_callback: Callable[[int, str], None]) -> bool:
        from multi_flash.helper.java_installer import get_java_exe

        if not self._jar_path:
            log_callback(0, "[ERROR] JAR not found.")
            return False

        if not _ensure_jre(log_callback):
            return False

        java_exe = get_java_exe()
        cmd = [java_exe, "-jar", self._jar_path, "-checkVer"]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30,
                                   encoding="utf-8", errors="replace")
        except Exception:
            log_callback(0, "[ERROR] Java execution failed.")
            return False

        for line in (result.stdout + result.stderr).splitlines():
            line = line.strip()
            if line:
                log_callback(0, line)

        return result.returncode == 0

