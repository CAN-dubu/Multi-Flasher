import sys
import os
import subprocess
import serial
import threading
import time
import copy
from constants import *

_root = None
_queue_log = None
_update_status_fn = None
_operation_mode = OPERATION_FLASH

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
def open_serial_for_test(port, baudrate, timeout=5):
    start = time.time()
    last_error = None
    while time.time() - start < timeout:
        try:
            ser = serial.Serial(port, baudrate, timeout=0.05, rtscts=False, dsrdtr=False)
            try:
                ser.setDTR(False)
                ser.setRTS(False)
            except Exception:
                pass
            return ser, None
        except serial.SerialException as e:
            last_error = e
            time.sleep(0.1)
    return None, last_error

def reset_esp32_to_app(ser):
    try:
        ser.reset_input_buffer()
        ser.setDTR(False)
        ser.setRTS(True)
        time.sleep(0.12)
        ser.setRTS(False)
        time.sleep(0.2)
        ser.reset_input_buffer()
        return True
    except Exception:
        return False

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

def set_operation_mode(mode):
    global _operation_mode
    if mode not in (OPERATION_FLASH, OPERATION_TEST):
        raise ValueError(f"Unknown operation mode: {mode}")
    _operation_mode = mode

def get_operation_mode():
    return _operation_mode

def get_board_config(board_name=None):
    board_name = board_name or _current_board
    return BOARD_CONFIGS[board_name]

def snapshot_board(board_name=None):
    board_name = board_name or _current_board
    if board_name not in BOARD_CONFIGS:
        raise ValueError(f"Unknown board: {board_name}\nAvailable: {list(BOARD_CONFIGS.keys())}")
    return board_name, copy.deepcopy(BOARD_CONFIGS[board_name])

def _board_type(board_name=None):
    return get_board_config(board_name).get("type", "esp32")

def is_stlink_board(board_name=None):
    return _board_type(board_name) == "stlink"

def is_esp32_board(board_name=None):
    return _board_type(board_name) == "esp32"

# ===== STLink 순차 업데이트 =====
def _flash_stlink_sequential(devices, log_callback, progress_callback, board_name=None):
    """STLink 순차 업데이트 진입점."""
    from multi_flash.stlink.stlink_worker import StlinkSequentialWorker
    _, config = snapshot_board(board_name)
    worker = StlinkSequentialWorker(jar_path=config.get("jar_path"))
    worker.flash_all(devices, log_callback, progress_callback)

# ===== esptool subprocess 실행 =====
def run_esptool_stream(port, script_dir, board_name, config):
    from utils import clean_ansi

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

    _queue_log(port, f"[INFO] Board: {board_name} ({config['chip']})")

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
def flash_device(port, port_type_str="", board_name=None):
    board_name, config = snapshot_board(board_name)
    board_type = config.get("type", "esp32")
    if board_type == "stlink":
        _flash_stlink_from_ui(port, port_type_str)
        return
    if config.get("group") == BOARD_GROUP_PRODUCTION and _operation_mode == OPERATION_TEST:
        _run_production_test(port, port_type_str, board_name, config)
        return
    _flash_esp32(port, port_type_str, board_name, config)

def _run_production_test(port, port_type_str, board_name, config):
    _queue_log(port, f"[INFO] Board: {board_name}")
    _queue_log(port, f"[INFO] Production test mode on {port}{port_type_str}")
    _queue_log(port, "[INFO] Test mode: flashing skipped.")
    _root.after(0, lambda p=port: _update_status_fn(p, "TEST READY", STATUS_WAIT_BG, STATUS_WAIT_FG, "#333355"))

    test_flow = config.get("test_flow") or []
    if not test_flow:
        _queue_log(port, "[ERROR] No production test flow is configured.")
        _root.after(0, lambda p=port: _update_status_fn(p, "TEST ERROR", STATUS_FAIL_BG, STATUS_FAIL_FG, "#7a2d2d"))
        return

    baudrate = int(config.get("test_baud", 115200))
    ser, open_error = open_serial_for_test(port, baudrate, timeout=5)
    if ser is None:
        _queue_log(port, f"[FAIL] Serial open failed: {open_error}")
        _root.after(0, lambda p=port: _update_status_fn(p, "PORT ERROR", STATUS_FAIL_BG, STATUS_FAIL_FG, "#7a2d2d"))
        return
    if reset_esp32_to_app(ser):
        _queue_log(port, "[INFO] Board reset for production test.")

    try:
        _queue_log(port, f"[INFO] 시리얼 연결 확인 완료 ({baudrate} baud)")
        total_steps = len(test_flow)
        serial_buffer = ""
        for step_index, step in enumerate(test_flow, start=1):
            name = step.get("name", "STEP")
            expected = step.get("expect", "")
            status_wait = step.get("status_wait", f"{name} WAIT")
            status_ok = step.get("status_ok", f"{name} OK")
            timeout = float(step.get("timeout", 10))
            operator_message = step.get("operator_message") or step.get("action")
            send_text = step.get("send")
            send_interval = float(step.get("send_interval", 0.5))

            _queue_log(port, f"[STEP {step_index}/{total_steps}] {name}")
            if operator_message:
                _queue_log(port, f"[안내] {operator_message}")
            _queue_log(port, f"[대기] {name} 검사 진행 중입니다. 제한 시간 {timeout:.0f}초")
            _root.after(0, lambda p=port, s=status_wait: _update_status_fn(p, s, STATUS_UART_BG, STATUS_UART_FG, "#2d4a7a"))

            ok, detail, serial_buffer = _wait_for_serial_text(
                ser, port, expected, timeout, send_text, send_interval, serial_buffer
            )
            if not ok:
                _queue_log(port, f"[FAIL] {name} 검사 실패: 제한 시간 안에 완료되지 않았습니다.")
                _queue_log(port, f"[DEBUG] {detail}")
                _root.after(0, lambda p=port: _update_status_fn(p, "TEST FAIL", STATUS_FAIL_BG, STATUS_FAIL_FG, "#7a2d2d"))
                return

            _queue_log(port, f"[SUCCESS] {status_ok}")
            _root.after(0, lambda p=port, s=status_ok: _update_status_fn(p, s, STATUS_DONE_BG, STATUS_DONE_FG, "#2d7a4a"))

        _queue_log(port, "[SUCCESS] Production test complete.")
        _root.after(0, lambda p=port: _update_status_fn(p, "TEST DONE", STATUS_DONE_BG, STATUS_DONE_FG, "#2d7a4a"))
    except Exception as e:
        _queue_log(port, f"[ERROR] Production test crashed: {e}")
        _root.after(0, lambda p=port: _update_status_fn(p, "TEST ERROR", STATUS_FAIL_BG, STATUS_FAIL_FG, "#7a2d2d"))
    finally:
        try:
            ser.close()
        except Exception:
            pass

def _wait_for_serial_text(ser, port, expected, timeout, send_text=None, send_interval=0.5, initial_buffer=""):
    expected_lower = expected.lower()
    start_time = time.time()
    last_send_time = 0
    raw_buffer = initial_buffer or ""
    total_bytes = 0
    send_bytes = None

    if send_text:
        send_bytes = (str(send_text) + "\n").encode("utf-8")

    match_index = raw_buffer.lower().find(expected_lower)
    if match_index >= 0:
        next_buffer = raw_buffer[match_index + len(expected):]
        return True, f"matched '{expected}'", next_buffer

    while time.time() - start_time < timeout:
        try:
            now = time.time()
            if send_bytes and now - last_send_time >= send_interval:
                ser.write(send_bytes)
                ser.flush()
                last_send_time = now

            waiting = ser.in_waiting
            data = ser.read(waiting if waiting > 0 else 1)
        except serial.SerialException as e:
            return False, f"Serial error: {e}", raw_buffer

        if data:
            total_bytes += len(data)
            decoded = data.decode("utf-8", errors="ignore")
            raw_buffer += decoded

            match_index = raw_buffer.lower().find(expected_lower)
            if match_index >= 0:
                next_buffer = raw_buffer[match_index + len(expected):]
                return True, f"matched '{expected}'", next_buffer

        time.sleep(0.01)

    if total_bytes > 0:
        received_tail = raw_buffer[-120:].replace("\r", "\\r").replace("\n", "\\n")
        return False, f"timeout after {timeout:.0f}s; received {total_bytes} bytes but not '{expected}'; tail='{received_tail}'", raw_buffer
    return False, f"timeout after {timeout:.0f}s; no serial data", raw_buffer

# ===== ESP32 플래싱 =====
def _flash_esp32(port, port_type_str, board_name, config):
    start_time = time.time()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    is_cp2102 = "CP2102" in port_type_str
    is_ch343p = "CH343P" in port_type_str
    is_native_usb = "Native" in port_type_str
    is_uart_bridge = is_cp2102 or is_ch343p
    port_type = (
        "CP2102 (UART)" if is_cp2102
        else "CH343P (UART)" if is_ch343p
        else "Native USB" if is_native_usb
        else "Unknown"
    )
    _queue_log(port, f"[INFO] Port: {port_type}")
    _queue_log(port, f"[INFO] Flashing on {port}...")
    _root.after(0, lambda p=port: _update_status_fn(p, "FLASHING", STATUS_UPLOADING_BG, STATUS_UPLOADING_FG, "#8b7a20"))
    returncode = run_esptool_stream(port, script_dir, board_name, config)
    if returncode != 0:
        _queue_log(port, "[FAIL] Flashing failed.")
        _root.after(0, lambda p=port: _update_status_fn(p, "FAILED", STATUS_FAIL_BG, STATUS_FAIL_FG, "#7a2d2d"))
        return
    _queue_log(port, "[UPLOAD DONE]")
    if is_uart_bridge:
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

# ===== STLink UI 연동 =====
def _flash_stlink_from_ui(port, port_type_str=""):
    """STLink 모드에서 UI 카드 클릭 시 호출 (STLink는 슬롯 기반)."""
    pass
