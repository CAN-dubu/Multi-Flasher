import os

BOARD_GROUP_FLASH = "Basic Flash"
BOARD_GROUP_PRODUCTION = "Production Test"
BOARD_GROUP_ORDER = (BOARD_GROUP_FLASH, BOARD_GROUP_PRODUCTION)

OPERATION_FLASH = "Flash"
OPERATION_TEST = "Test"

# Board configurations
BOARD_CONFIGS = {
    # HG-S3
    "HG-ESP32-S3": {
        "type": "esp32",
        "group": BOARD_GROUP_FLASH,
        "chip": "esp32s3",
        "bin_dir": os.path.join("..", "bin", "HG-ESP32-S3"),
        "files": [
            ("0x0", "bootloader.bin"),
            ("0x8000", "partitions.bin"),
            ("0x10000", "firmware.bin"),
        ],
        "baud": "921600",
    },
    # HG-V4
    "HG-ESP32-V4": {
        "type": "esp32",
        "group": BOARD_GROUP_FLASH,
        "chip": "esp32",
        "bin_dir": os.path.join("..", "bin", "HG-ESP32-V4"),
        "files": [
            ("0x1000", "bootloader.bin"),
            ("0x8000", "partitions.bin"),
            ("0x10000", "firmware.bin"),
        ],
        "baud": "921600",
    },
    # ESP32-S3-ETH-CAN485
    "ESP32-S3-ETH-CAN485": {
        "type": "esp32",
        "group": BOARD_GROUP_PRODUCTION,
        "chip": "esp32s3",
        "bin_dir": os.path.join("..", "bin", "ESP32-S3-ETH-CAN485"),
        "files": [
            ("0x0", "bootloader.bin"),
            ("0x8000", "partitions.bin"),
            ("0x10000", "firmware.bin"),
        ],
        "baud": "921600",
        "test_steps": ("DEBUG", "BUTTON", "EEPROM", "SPI_FLASH", "UART", "RS232", "RS485", "CAN", "UDP"),
        "test_baud": 115200,
        "test_flow": [
            {
                "name": "DEBUG",
                "expect": "debug output",
                "status_wait": "DEBUG WAIT",
                "status_ok": "DEBUG OK",
                "timeout": 12,
                "send": "test start",
                "send_interval": 0.5,
                "operator_message": "보드 응답을 확인 중입니다. 잠시 기다려주세요.",
            },
            {
                "name": "BUTTON",
                "expect": "button output",
                "status_wait": "BUTTON WAIT",
                "status_ok": "BUTTON OK",
                "timeout": 30,
                "operator_message": "보드의 버튼을 한 번 눌러주세요.",
            },
            {
                "name": "EEPROM",
                "expect": "eeprom output",
                "status_wait": "EEPROM WAIT",
                "status_ok": "EEPROM OK",
                "timeout": 15,
                "operator_message": "EEPROM 자동 검사 중입니다. 잠시 기다려주세요.",
            },
            {
                "name": "SPI_FLASH",
                "expect": "spi flash output",
                "status_wait": "SPI FLASH WAIT",
                "status_ok": "SPI FLASH OK",
                "timeout": 15,
                "operator_message": "SPI Flash 자동 검사 중입니다. 잠시 기다려주세요.",
            },
            {
                "name": "UART",
                "expect": "uart output",
                "status_wait": "UART WAIT",
                "status_ok": "UART OK",
                "timeout": 15,
                "operator_message": "UART 루프백 검사 중입니다. 잠시 기다려주세요.",
            },
            {
                "name": "RS232",
                "expect": "rs232 output",
                "status_wait": "RS232 WAIT",
                "status_ok": "RS232 OK",
                "timeout": 15,
                "operator_message": "RS232 통신 검사 중입니다. 잠시 기다려주세요.",
            },
            {
                "name": "RS485",
                "expect": "rs485 output",
                "status_wait": "RS485 WAIT",
                "status_ok": "RS485 OK",
                "timeout": 30,
                "operator_message": "RS485 통신 검사 중입니다. 잠시 기다려주세요.",
            },
            {
                "name": "CAN",
                "expect": "can output",
                "status_wait": "CAN WAIT",
                "status_ok": "CAN OK",
                "timeout": 15,
                "operator_message": "CAN 통신 검사 중입니다. 잠시 기다려주세요.",
            },
            {
                "name": "UDP",
                "expect": "udp output",
                "status_wait": "UDP WAIT",
                "status_ok": "UDP OK",
                "timeout": 15,
                "operator_message": "UDP 통신 검사 중입니다. 잠시 기다려주세요.",
            },
        ],
    },
    # ST-Link V2 Firmware Update
    "ST-LINK V2": {
        "type": "stlink",
        "group": BOARD_GROUP_FLASH,
        "kind": "stlink_v2",
        "is_sequential": True,
        "experimental_pnp_isolation": True,
        "jar_path": None,
    },
}

CURRENT_BOARD = "HG-ESP32-S3"

THEME_DARK = "Dark"
THEME_WHITE = "White"
THEME_NAMES = (THEME_DARK, THEME_WHITE)

THEMES = {
    THEME_DARK: {
        "MAIN_BG": "#0f0f1a",
        "CARD_BG": "#1a1a2e",
        "HEADER_BG": "#252540",
        "LOG_BG": "#1e1e2e",
        "TEXT_COLOR": "#e0e0e0",
        "TEXT_MUTED": "#888899",
        "ACCENT": "#7aa2f7",
        "TITLE_COLOR": "#7aa2f7",
        "PORT_COLOR": "#c084fc",
        "SEPARATOR": "#333355",
        "STATUS_BAR_BG": "#2d2d4a",
        "STATUS_BAR_TEXT": "#e0e0e0",
        "SUBTITLE_EMPTY_BG": "#555577",
        "SUBTITLE_EMPTY_FG": "#aaaaaa",
        "PROGRESS_BG": "#2a2a3e",
        "DROPDOWN_BG": "#252540",
        "DROPDOWN_BORDER": "#3a3a5c",
        "DROPDOWN_POPUP_BG": "#1a1a2e",
        "DROPDOWN_POPUP_BORDER": "#3a3a5c",
        "DROPDOWN_TEXT": "#e0e0e0",
        "DROPDOWN_SELECTED_BG": "#2a2a4e",
        "DROPDOWN_HOVER_BG": "#31315a",
        "BUTTON_BG": "#252540",
        "BUTTON_TEXT": "#e0e0e0",
        "BUTTON_HOVER": "#2a2a4e",
        "BUTTON_BORDER": "#3a3a5c",
        "LOG_DEFAULT": "#aaaaaa",
        "WARN_TEXT": "#fbbf24",
        "ERROR_TEXT": "#f87171",
        "SUCCESS_TEXT": "#4ade80",
        "STATUS_DONE_BADGE_BG": "#4ade80",
        "STATUS_DONE_BADGE_FG": "#000000",
        "RX_TEXT": "#4ade80",
        "IDLE_MARKER": "#555577",
        "BANNER_INFO_BG": "#1e3a5f",
        "BANNER_INFO_BORDER": "#2a5a8f",
        "BANNER_INFO_TEXT": "#c7d2fe",
        "BANNER_WARN_BG": "#4a3518",
        "BANNER_WARN_BORDER": "#9a6a1f",
        "BANNER_WARN_TEXT": "#fbbf24",
        "BORDER_NEUTRAL": "#333355",
        "BORDER_FAIL": "#7a2d2d",
        "BORDER_DONE": "#2d7a4a",
        "BORDER_DONE_ALT": "#275f3a",
        "BORDER_UPLOAD": "#8b7a20",
        "BORDER_UART": "#2d4a7a",
    },
    THEME_WHITE: {
        "MAIN_BG": "#d3dcec",
        "CARD_BG": "#f7f9fc",
        "HEADER_BG": "#d8e1ed",
        "LOG_BG": "#f2f6fb",
        "TEXT_COLOR": "#172033",
        "TEXT_MUTED": "#53627a",
        "ACCENT": "#245edb",
        "TITLE_COLOR": "#173a8a",
        "PORT_COLOR": "#6c3bd1",
        "SEPARATOR": "#aebdd0",
        "STATUS_BAR_BG": "#e1e8f2",
        "STATUS_BAR_TEXT": "#263449",
        "SUBTITLE_EMPTY_BG": "#dce5f0",
        "SUBTITLE_EMPTY_FG": "#53627a",
        "PROGRESS_BG": "#dce5ef",
        "DROPDOWN_BG": "#f8fbff",
        "DROPDOWN_BORDER": "#8fa1b8",
        "DROPDOWN_POPUP_BG": "#ffffff",
        "DROPDOWN_POPUP_BORDER": "#7f91a8",
        "DROPDOWN_TEXT": "#111827",
        "DROPDOWN_SELECTED_BG": "#c9dcfa",
        "DROPDOWN_HOVER_BG": "#e1ebf8",
        "BUTTON_BG": "#f8fbff",
        "BUTTON_TEXT": "#173a8a",
        "BUTTON_HOVER": "#e7eef9",
        "BUTTON_BORDER": "#8fa1b8",
        "LOG_DEFAULT": "#4f5d73",
        "WARN_TEXT": "#a16207",
        "ERROR_TEXT": "#c93434",
        "SUCCESS_TEXT": "#128444",
        "STATUS_DONE_BADGE_BG": "#15803d",
        "STATUS_DONE_BADGE_FG": "#ffffff",
        "RX_TEXT": "#128444",
        "IDLE_MARKER": "#8997aa",
        "BANNER_INFO_BG": "#e8f0fb",
        "BANNER_INFO_BORDER": "#a7bee3",
        "BANNER_INFO_TEXT": "#173a8a",
        "BANNER_WARN_BG": "#f7efd7",
        "BANNER_WARN_BORDER": "#d6bd68",
        "BANNER_WARN_TEXT": "#8a5a00",
        "BORDER_NEUTRAL": "#b8c6d8",
        "BORDER_FAIL": "#dfb0b0",
        "BORDER_DONE": "#79bd91",
        "BORDER_DONE_ALT": "#8fcda4",
        "BORDER_UPLOAD": "#d9c86e",
        "BORDER_UART": "#a9bfe1",
    },
}

CURRENT_THEME = THEME_DARK


def get_theme_values(theme_name=None):
    theme = theme_name if theme_name in THEMES else CURRENT_THEME
    return dict(THEMES[theme])


def apply_theme(theme_name):
    global CURRENT_THEME
    if theme_name not in THEMES:
        theme_name = THEME_DARK
    CURRENT_THEME = theme_name
    values = get_theme_values(theme_name)
    globals().update(values)
    return values


# Default theme colors
apply_theme(CURRENT_THEME)

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
