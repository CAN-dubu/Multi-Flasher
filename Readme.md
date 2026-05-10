# Higenis Multi Flasher

Higenis Multi Flasher는 Higenis 보드 펌웨어 다운로드, 생산 테스트, ST-LINK 업데이트를 한 화면에서 처리하는 Windows용 PC 프로그램입니다.

## 실행

```bat
run.bat
```

프로그램을 실행하면 연결된 USB 장치를 감지하고, 선택된 `Board`와 `Do` 값에 맞춰 Flash 또는 Test 작업을 수행합니다.

## 화면 구성

상단 조작부는 세 가지로 구성됩니다.

| 항목 | 설명 |
| --- | --- |
| `Board` | 작업 대상 보드를 선택합니다. |
| `Do` | 선택한 보드에서 수행할 작업을 선택합니다. |
| `Config` | 테마 설정 창을 엽니다. |

`Config` 창에서는 색상 테마만 변경할 수 있습니다.

- `Dark`
- `White`

설정을 변경하면 설정 창은 자동으로 닫힙니다.

## 지원 보드 및 작업

| Board | Do |
| --- | --- |
| `HG-ESP32-S3` | `Flash` |
| `HG-ESP32-V4` | `Flash` |
| `ESP32-S3-ETH-CAN485` | `Flash`, `Test` |
| `ST-LINK V2` | `Flash` |

## ESP Flash

ESP 보드를 USB로 연결하면 프로그램이 포트를 감지합니다. `Do`가 `Flash`인 경우 선택된 보드 설정에 맞춰 펌웨어를 다운로드합니다.

펌웨어 파일은 보드별로 `bin` 폴더 아래에 배치됩니다. 보드별 플래시 주소와 파일 목록은 `multi_flash/constants.py`의 `BOARD_CONFIGS`에서 관리합니다.

## ESP32-S3-ETH-CAN485 생산 테스트

`Board`를 `ESP32-S3-ETH-CAN485`, `Do`를 `Test`로 선택하면 생산 테스트 모드로 동작합니다.

테스트 모드에서는 펌웨어 다운로드를 생략하고 보드를 리셋한 뒤 시리얼 통신으로 테스트를 진행합니다.

기본 테스트 순서:

1. `DEBUG`
2. `BUTTON`
3. `EEPROM`
4. `SPI_FLASH`
5. `UART`
6. `RS232`
7. `RS485`
8. `CAN`
9. `UDP`

`BUTTON` 단계에서는 보드의 버튼 입력이 필요합니다. 각 단계의 성공/실패 상태는 카드와 로그에 표시됩니다.

## ST-LINK V2 업데이트

`Board`를 `ST-LINK V2`, `Do`를 `Flash`로 선택하면 ST-LINK 펌웨어 업데이트 흐름이 실행됩니다.

프로그램은 Java Runtime 상태를 먼저 확인하고, 준비가 끝나면 ST-LINK 장치를 감지해 업데이트를 진행합니다. 진행 상태와 결과는 별도 카드로 표시됩니다.

## 상태 표시

프로그램은 작업 상황을 카드와 로그로 표시합니다.

주요 상태 예시:

- `USB DETECTED`
- `DETECTING`
- `FLASHING`
- `DONE`
- `FAILED`
- `TEST READY`
- `TEST DONE`
- `JRE READY`
- `UPDATING`
- `SUCCESS`

화이트/다크 테마 모두 상태 배지, 카드 테두리, 로그 영역 색상이 구분되도록 구성되어 있습니다.

## 설정 파일 구조

주요 파일:

| 파일 | 역할 |
| --- | --- |
| `multi_flash/main.py` | 앱 시작, 상단 컨트롤, 설정 창, 전체 UI 연결 |
| `multi_flash/app_state.py` | 보드 목록과 보드별 `Do` 옵션 규칙 |
| `multi_flash/constants.py` | 보드 설정, 펌웨어 경로, 테마 팔레트 |
| `multi_flash/widgets.py` | 테마 적용 드롭다운 위젯 |
| `multi_flash/theme.py` | 윈도우 타이틀바 및 테마 보조 함수 |
| `multi_flash/ui.py` | 카드, 로그, 상태 표시 UI |
| `multi_flash/flash_worker.py` | ESP 플래시 및 생산 테스트 작업 |
| `multi_flash/usb_monitor.py` | USB 감지 및 ST-LINK 업데이트 작업 |

## 보드 설정 추가 또는 수정

보드 설정은 `multi_flash/constants.py`의 `BOARD_CONFIGS`에서 관리합니다.

ESP 보드 설정에는 일반적으로 다음 항목이 포함됩니다.

- `chip`
- `baud`
- `firmware`
- `display_name`
- `usb_hint`

생산 테스트가 필요한 보드는 `group`과 `test_flow` 설정을 함께 사용합니다.

`Do` 드롭다운 옵션은 보드 그룹에 따라 결정됩니다. 일반 보드는 `Flash`만 표시되고, 생산 테스트 보드는 `Flash`와 `Test`를 표시할 수 있습니다.

## 문제 해결

### 생산 테스트 DEBUG 단계에서 timeout이 발생하는 경우

다음을 우선 확인합니다.

- 펌웨어에서 `Serial.begin(115200)`이 호출되는지 확인합니다.
- PC 프로그램이 기다리는 응답 문자열과 펌웨어가 출력하는 문자열이 일치하는지 확인합니다.
- 보드 리셋 직후 부트 로그만 출력되고 앱 로그가 나오지 않는지 확인합니다.
- 다른 시리얼 모니터나 프로그램이 같은 COM 포트를 점유하고 있지 않은지 확인합니다.
- USB-Serial 칩셋 또는 리셋 타이밍 문제로 간헐적인 무응답이 생기는지 반복 테스트합니다.

### ST-LINK 업데이트가 진행되지 않는 경우

다음을 확인합니다.

- Java Runtime 카드가 `JRE READY` 상태인지 확인합니다.
- ST-LINK 장치가 정상적으로 인식되는지 확인합니다.
- 업데이트 중 USB 연결이 끊기지 않았는지 확인합니다.

### COM 포트 감지가 되지 않는 경우

다음을 확인합니다.

- USB 케이블과 보드 전원을 확인합니다.
- Windows 장치 관리자에서 COM 포트가 생성되는지 확인합니다.
- 다른 프로그램이 포트를 사용 중이면 종료한 뒤 다시 연결합니다.

## 개발 메모

이 프로젝트는 UI 표시 상태와 작업 상태를 분리하는 방향으로 정리되어 있습니다. 디자인 변경은 주로 `constants.py`, `ui.py`, `widgets.py`에서 처리하고, Flash/Test 기능 흐름은 `flash_worker.py`와 `usb_monitor.py`에서 관리합니다.

기능 변경 시에는 기존 Flash/Test/ST-LINK 흐름이 깨지지 않도록 보드별 `Do` 옵션과 실제 실행 분기를 함께 확인해야 합니다.
