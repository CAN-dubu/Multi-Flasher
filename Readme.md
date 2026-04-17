# Higenis Multi Flasher - 사용법

---

## 1. 보드 선택

우측 상단 **Board** 드롭다운에서 플래싱할 보드를 선택합니다.

---

## 2. USB 연결

ESP32 보드를 USB로 연결하면 자동으로 감지되어 플래싱이 시작됩니다.

---

## 3. 상태 확인

| 상태 | 의미 |
|---|---|
| **USB DETECTED** | USB 연결 감지, COM 포트 등록 대기 |
| **DETECTING** | 포트 타입 식별 중 |
| **FLASHING** | 펌웨어 업로드 중 |
| **UART CHECK** | 시리얼 출력 검증 중 (CP2102만) |
| **DONE** | 플래싱 완료 |
| **FAILED** | 플래싱 실패 |

---

## 4. 멀티 플래싱

여러 보드를 동시에 연결하면 각각 별도 카드로 표시되며 병렬로 플래싱됩니다.

---

## 5. 보드 추가

`constants.py`의 `BOARD_CONFIGS`에 항목을 추가합니다.

```python
"새보드이름": {
    "chip": "esp32",              # esp32 / esp32s3 / esp32c3 등
    "bin_dir": os.path.join("..", "bin", "새보드이름"),
    "files": [
        ("0x1000",  "bootloader.bin"),  # ESP32: 0x1000 / ESP32-S3: 0x0
        ("0x8000",  "partitions.bin"),
        ("0x10000", "firmware.bin"),
    ],
    "baud": "921600",
},
