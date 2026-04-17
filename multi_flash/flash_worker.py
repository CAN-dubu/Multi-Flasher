import sys
import os
import subprocess
import serial
import threading
import time
from constants import *

_root = None
_queue_log = None
_update_status_fn = None

def init(root, queue_log_fn, update_status_fn):
    global _root, _queue_log, _update_status_fn
    _root = root
    _queue_log = queue_log_fn
    _update_status_fn = update_status_fn

# ===== 포트 재연결 대기 =====
def wait_for_port(port, timeout=5):
    start = time.time()
    while time.time() - start < timeout:
        try:
            ser = serial.Serial(port, 115200, timeout=0.05)
            ser.close()
            return True
        except serial.SerialException:
            time.sleep(0.1)
    return False

# ===== UART 체크 인라인 =====
def check_uart_inline(port, baudrate=115200, timeout=8):
    try:
        ser = serial.Serial(port, baudrate, timeout=0.05)
        ser.reset_input_buffer()
        ser.setDTR(False)
        time.sleep(0.1)
        ser.setDTR(True)
        start_time = time.time()
        total_bytes = 0
        output_lines = []
        while time.time() - start_time < timeout:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                total_bytes += len(data)
                try:
                    decoded = data.decode('utf-8', errors='ignore')
                    lines = decoded.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line:
                            output_lines.append(line)
                            _queue_log(port, f"[RX] {line}")
                            if "output" in line.lower():
                                ser.close()
                                return (True, f"OK ({len(output_lines)} lines, {total_bytes} bytes)")
                except:
                    pass
            time.sleep(0.01)
        ser.close()
        if total_bytes > 0:
            return (True, f"OK ({total_bytes} bytes, {len(output_lines)} lines)")
        else:
            return (False, f"Timeout - no data in {timeout}s")
    except serial.SerialException as e:
        return (False, f"Serial error: {e}")
    except Exception as e:
        return (False, f"Error: {e}")

# ===== 현재 보드 설정 =====
_current_board = CURRENT_BOARD

def set_board(board_name):
    global _current_board
    if board_name not in BOARD_CONFIGS:
        raise ValueError(f"Unknown board: {board_name}\nAvailable: {list(BOARD_CONFIGS.keys())}")
    _current_board = board_name

def get_board():
    return _current_board

def get_board_config():
    return BOARD_CONFIGS[_current_board]

# ===== esptool subprocess 실행 =====
def run_esptool_stream(port, script_dir):
    from utils import clean_ansi

    config = get_board_config()
    bin_dir = os.path.join(script_dir, config["bin_dir"])

    # 파일 존재 확인
    for addr, filename in config["files"]:
        filepath = os.path.join(bin_dir, filename)
        if not os.path.exists(filepath):
            _queue_log(port, f"[ERROR] File not found: {filepath}")
            return 1

    # flash 인자 생성: addr1 file1 addr2 file2 ...
    flash_args = []
    for addr, filename in config["files"]:
        flash_args.append(addr)
        flash_args.append(os.path.join(bin_dir, filename))

    cmd = [
        sys.executable, "-m", "esptool",
        "--chip", config["chip"],
        "--port", port,
        "--baud", config["baud"],
        "--before", "default-reset",
        "--after", "hard-reset",
        "write_flash", "-z", "--flash_mode", "dio",
    ] + flash_args

    _queue_log(port, f"[INFO] Board: {_current_board} ({config['chip']})")

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, cwd=script_dir)
    flash_success = False
    for line in iter(process.stdout.readline, ''):
        stripped = clean_ansi(line).strip()
        if stripped:
            _queue_log(port, stripped)
            if "100%" in stripped or "Hash of data verified" in stripped:
                flash_success = True
            if "Hard resetting" in stripped:
                break

    def cleanup():
        try: process.stdout.close()
        except: pass
        try: process.wait(timeout=5)
        except: process.kill()
    threading.Thread(target=cleanup, daemon=True).start()
    return 0 if flash_success else 1

# ===== 플래싱 (백그라운드 스레드) =====
def flash_device(port, port_type_str=""):
    start_time = time.time()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    is_cp2102 = "CP2102" in port_type_str
    is_native_usb = "Native" in port_type_str
    port_type = "CP2102 (UART)" if is_cp2102 else "Native USB" if is_native_usb else "Unknown"
    _queue_log(port, f"[INFO] Port: {port_type}")
    _queue_log(port, f"[INFO] Flashing on {port}...")
    _root.after(0, lambda p=port: _update_status_fn(p, "FLASHING", STATUS_UPLOADING_BG, STATUS_UPLOADING_FG, "#8b7a20"))
    returncode = run_esptool_stream(port, script_dir)
    if returncode != 0:
        _queue_log(port, "[FAIL] Flashing failed.")
        _root.after(0, lambda p=port: _update_status_fn(p, "FAILED", STATUS_FAIL_BG, STATUS_FAIL_FG, "#7a2d2d"))
        return
    _queue_log(port, "[UPLOAD DONE]")
    if is_cp2102:
        _root.after(0, lambda p=port: _update_status_fn(p, "UART CHECK", STATUS_UART_BG, STATUS_UART_FG, "#2d4a7a"))
        port_ready = wait_for_port(port, timeout=5)
        if port_ready:
            success, msg = check_uart_inline(port, 115200, timeout=8)
            if success:
                _queue_log(port, "[SUCCESS] UART verified!")
                _queue_log(port, f"[INFO] {msg}")
                _root.after(0, lambda p=port: _update_status_fn(p, "DONE", STATUS_DONE_BG, STATUS_DONE_FG, "#2d7a4a"))
            else:
                _queue_log(port, f"[FAIL] {msg}")
                _root.after(0, lambda p=port: _update_status_fn(p, "UART FAIL", STATUS_FAIL_BG, STATUS_FAIL_FG, "#7a2d2d"))
        else:
            _queue_log(port, "[FAIL] Port not ready")
            _root.after(0, lambda p=port: _update_status_fn(p, "PORT ERROR", STATUS_FAIL_BG, STATUS_FAIL_FG, "#7a2d2d"))
    else:
        _queue_log(port, "[INFO] Native USB - UART skipped")
        _root.after(0, lambda p=port: _update_status_fn(p, "DONE", STATUS_DONE_BG, STATUS_DONE_FG, "#4ade80"))
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = elapsed % 60
    if minutes > 0:
        _queue_log(port, f"[INFO] Total time: {minutes}m {seconds:.1f}s")
    else:
        _queue_log(port, f"[INFO] Total time: {seconds:.1f}s")
    _queue_log(port, "[DONE]")
