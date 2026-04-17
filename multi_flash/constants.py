import os

# ===== 보드별 설정 =====
BOARD_CONFIGS = {
    # HG-S3
    "HG-ESP32-S3": {
        "chip": "esp32s3",
        "bin_dir": os.path.join("..", "bin", "HG-ESP32-S3"),
        "files": [
            ("0x1000",     "bootloader.bin"),
            ("0x8000",  "partitions.bin"),
            ("0x10000", "firmware.bin"),
        ],
        "baud": "921600",
    },
    # HG-V4
    "HG-ESP32-V4": {
        "chip": "esp32",
        "bin_dir": os.path.join("..", "bin", "HG-ESP32-V4"),
        "files": [
            ("0x1000",     "bootloader.bin"),
            ("0x8000",  "partitions.bin"),
            ("0x10000", "firmware.bin"),
        ],
        "baud": "921600",
    },
}

# 현재 선택된 보드 (기본값)
CURRENT_BOARD = "HG-ESP32-S3"

# ===== 색상 팔레트 (다크 테마) =====
MAIN_BG = "#0f0f1a"
CARD_BG = "#1a1a2e"
HEADER_BG = "#252540"
LOG_BG = "#1e1e2e"
TEXT_COLOR = "#e0e0e0"
TEXT_MUTED = "#888899"
ACCENT = "#7aa2f7"
PORT_COLOR = "#c084fc"

STATUS_UPLOADING_BG = "#fbbf24"
STATUS_UPLOADING_FG = "#000000"
STATUS_DONE_BG = "#4ade80"
STATUS_DONE_FG = "#000000"
STATUS_FAIL_BG = "#f87171"
STATUS_FAIL_FG = "#000000"
STATUS_UART_BG = "#7aa2f7"
STATUS_UART_FG = "#000000"
STATUS_WAIT_BG = "#555577"
STATUS_WAIT_FG = "#ffffff"
STATUS_DETECTING_BG = "#6366f1"
STATUS_DETECTING_FG = "#ffffff"
STATUS_USB_PENDING_BG = "#f59e0b"
STATUS_USB_PENDING_FG = "#ffffff"

STATUS_BAR_HEIGHT = 36
_LOG_FLUSH_INTERVAL = 100
