"""STLink ?붾컮?댁뒪 媛먯? (USB VID 0483 湲곕컲)."""
import subprocess
import re
import json as _json
from dataclasses import dataclass, field
from typing import List, Optional, Set

_PID_MAP = {
    "3748": "ST-LINK/V2",
    "374b": "ST-LINK/V2-1",
    "374d": "ST-LINK/V2-1",
    "374e": "STLINK-V3E",
    "374f": "STLINK-V3S",
    "3752": "STLINK-V3",
    "3753": "STLINK-V3",
    "3754": "STLINK-V3E",
    "572a": "STM32 Bootloader (DFU)",
}

_VID = "0483"
_V2_PIDS = {"3748", "374b", "374d"}
_V3_PIDS = {"374e", "374f", "3752", "3753", "3754"}
_SKIP_PIDS = {"3744", "572a"}


@dataclass
class StlinkDevice:
    instance_id: str
    vid: str
    pid: str
    model: str
    short_id: str
    serial: str = ""
    dedupe_key: str = ""
    status: str = ""


def _parse_vid_pid(instance_id: str):
    vid_m = re.search(r"VID_([0-9a-fA-F]{4})", instance_id)
    pid_m = re.search(r"PID_([0-9a-fA-F]+)", instance_id)
    vid = vid_m.group(1).lower() if vid_m else None
    pid = pid_m.group(1).lower() if pid_m else None
    return vid, pid


def _is_iface(instance_id: str) -> bool:
    return bool(re.search(r"&MI_[0-9A-F]{2}", instance_id))


def _get_serial(instance_id: str) -> str:
    if _is_iface(instance_id):
        return ""
    m = re.search(r'[^\\]+$', instance_id)
    return m.group(0) if m else ''


def _is_dummy_serial(serial: str) -> bool:
    if not serial:
        return True
    dummy_patterns = ("000000", "device", "default", "usb", "hub")
    lowered = serial.lower()
    return any(pattern in lowered for pattern in dummy_patterns) or serial.isdigit()


def _physical_key(dev: dict) -> str:
    """
    Physical device 怨좎쑀 ???앹꽦.
    ?곗꽑?쒖쐞:
    1. ContainerId (媛숈? 臾쇰━ ?μ튂 洹몃９)
    2. VID+PID+serial (?좏슚 serial???덉쓣 ??
    3. VID+PID+instance_id (serial???붾?????
    """
    inst_id = dev["inst_id"]
    serial = dev["serial"]
    vid = dev["vid"] or ""
    pid = dev["pid"] or ""

    # ContainerId 異붿텧 ?쒕룄
    container = ""
    m = re.search(r"ContainerId.([A-Fa-f0-9-]+)", inst_id, re.IGNORECASE)
    if m:
        container = m.group(1)

    if container:
        return f"container:{container}"

    if serial and not _is_dummy_serial(serial) and not _is_iface(inst_id):
        return f"{vid}:{pid}:{serial}"

    return f"{vid}:{pid}:{inst_id}"


def _safe_decode(data: bytes) -> Optional[str]:
    encodings = ["utf-8", "utf-16-le", "cp949", "mbcs"]
    for enc in encodings:
        try:
            return data.decode(enc, errors="strict")
        except (UnicodeDecodeError, LookupError):
            pass
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return None


def _query_stlinks() -> List[dict]:
    """
    PowerShell濡?ST-Link VID 0483 ?μ튂 raw 紐⑸줉 議고쉶 (PresentOnly, FriendlyName ?ы븿).
    JSON ?뚯떛 + fallback WMI 荑쇰━ ?ы븿.
    """
    import os
    _DEBUG = os.environ.get("STLINK_DEBUG", "").lower() in ("1", "true", "yes")

    ps_cmd = (
        r"Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like '*VID_0483*' } | "
        r"ForEach-Object { [PSCustomObject]@{InstanceId=$_.InstanceId;Status=$_.Status;FriendlyName=$_.FriendlyName} } | "
        r"ConvertTo-Json -Compress"
    )

    def _run_ps(cmd: str) -> list:
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            if _DEBUG:
                print(f"[DEBUG] PS command: {cmd}")
                if result.stdout:
                    print(f"[DEBUG] PS stdout (first 500): {result.stdout[:500]}")
                if result.stderr:
                    print(f"[DEBUG] PS stderr (first 200): {result.stderr[:200]}")
            if result.returncode != 0:
                if _DEBUG:
                    print(f"[DEBUG] PS returncode={result.returncode}")
                return []
            decoded = result.stdout.strip()
            if not decoded:
                return []
            parsed = _json.loads(decoded)
            if isinstance(parsed, dict):
                parsed = [parsed]
            return parsed
        except Exception as e:
            if _DEBUG:
                print(f"[DEBUG] PS query exception: {e}")
            return []

    # Primary: Get-PnpDevice
    entries = _run_ps(ps_cmd)
    if entries:
        return entries

    # Fallback: Get-CimInstance Win32_PnPEntity
    if _DEBUG:
        print("[DEBUG] PNP query returned 0, trying Win32_PnPEntity fallback")
    fallback_cmd = (
        r"Get-CimInstance Win32_PnPEntity | "
        r"Where-Object { $_.PNPDeviceID -like '*VID_0483*' -and $_.Present -ne $false } | "
        r"ForEach-Object { [PSCustomObject]@{InstanceId=$_.PNPDeviceID;Status=$_.Status;FriendlyName=$_.Caption} } | "
        r"ConvertTo-Json -Compress"
    )
    entries = _run_ps(fallback_cmd)
    return entries


def detect_stlinks(v2_only: bool = True, active_only: bool = False) -> List[StlinkDevice]:
    """
    ST-Link ?μ튂 媛먯? + physical dedupe.
    v2_only=True?대㈃ V2/V2-1 PID留?諛섑솚 (V3/DFU ?쒖쇅).
    active_only=True excludes PnP-disabled devices from isolation checks.
    """
    import os
    _DEBUG = os.environ.get("STLINK_DEBUG", "").lower() in ("1", "true", "yes")

    raw_entries = _query_stlinks()

    print(f"[INFO] PNP raw entries (PresentOnly VID_0483): {len(raw_entries)}")
    if _DEBUG:
        for entry in raw_entries:
            print(f"[DEBUG] PNP raw: InstanceId={entry.get('InstanceId','')[:80]} Status={entry.get('Status','')} FriendlyName={entry.get('FriendlyName','')[:40]}")

    # ?먯떆 ?곗씠???뚯떛 ??Status ?꾪꽣??理쒖냼??    raw: List[dict] = []
    raw: List[dict] = []
    for entry in raw_entries:
        inst_id = entry.get("InstanceId", "")
        if not inst_id:
            continue
        vid, pid = _parse_vid_pid(inst_id)
        if vid != _VID or not pid:
            continue
        status = str(entry.get("Status", "") or "")
        if active_only and status.lower() == "disabled":
            print(f"[INFO] Skipping disabled ST-LINK during active-only scan: InstanceId={inst_id[:60]}")
            continue
        # Non-OK devices are still kept for the normal UI scan so they can be shown/logged.
        if status in ("Error", "IOError", "Disabled"):
            print(f"[WARN] ST-LINK with unusual status (kept as candidate): InstanceId={inst_id[:60]} Status={status}")
        serial = _get_serial(inst_id)
        raw.append({
            "inst_id": inst_id,
            "vid": vid,
            "pid": pid,
            "serial": serial,
            "status": status,
            "is_iface": _is_iface(inst_id),
        })

    if _DEBUG:
        print(f"[DEBUG] ST-LINK candidates after status filter: {len(raw)}")
        for dev in raw:
            print(f"[DEBUG]   candidate: PID={dev['pid']} serial={dev['serial']} status={dev['status']} iface={dev['is_iface']}")

    # Physical dedupe
    seen_keys: Set[str] = set()
    deduped: List[StlinkDevice] = []
    interface_merged = 0

    for dev in raw:
        pid = dev["pid"]
        is_iface = dev["is_iface"]

        # V2 only filter
        if v2_only:
            if pid in _SKIP_PIDS or pid in _V3_PIDS:
                continue

        # Interface entries(MI_XX) ??skip but count
        if is_iface:
            interface_merged += 1
            continue

        key = _physical_key(dev)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        model = _PID_MAP.get(pid, f"Unknown PID {pid}")
        serial = dev["serial"]
        short_id = f"{pid}-{serial[-8:]}" if len(serial) >= 8 else f"{pid}-{serial}" if serial else pid

        deduped.append(StlinkDevice(
            instance_id=dev["inst_id"],
            vid=dev["vid"],
            pid=pid,
            model=model,
            short_id=short_id,
            serial=serial,
            dedupe_key=key,
            status=dev.get("status", ""),
        ))

    print(f"[INFO] Present ST-LINK raw entries: {len(raw)}")
    print(f"[INFO] Physical present ST-LINK/V2 devices: {len(deduped)}")

    return deduped, len(raw), interface_merged


def detect_stlinks_detailed() -> tuple:
    """寃利앹슜: rawcount, physical count, merged count 諛섑솚."""
    devs, raw_n, merged = detect_stlinks(v2_only=True)
    return raw_n, len(devs), merged


# ?뚯뒪??if __name__ == "__main__":
    devs, raw_n, merged = detect_stlinks(v2_only=False)
    v2_devs = [d for d in devs if d.pid in _V2_PIDS]
    v3_devs = [d for d in devs if d.pid in _V3_PIDS]
    skip_devs = [d for d in devs if d.pid in _SKIP_PIDS]

    print(f"[INFO] Raw USB entries: {raw_n}")
    print(f"[INFO] Physical ST-LINK devices: {len(devs)}")
    print(f"[INFO]   V2/V2-1: {len(v2_devs)}, V3: {len(v3_devs)}, DFU/Skip: {len(skip_devs)}")
    print(f"[INFO] Interface entries merged: {merged}")
    print()
    for i, d in enumerate(v2_devs, 1):
        print(f"[INFO] Slot #{i}: {d.model} PID={d.pid.upper()} Serial={d.serial} Key={d.dedupe_key}")



