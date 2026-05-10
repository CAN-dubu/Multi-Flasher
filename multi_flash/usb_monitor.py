"""USB port monitoring and ST-LINK auto-update queue.

ST-LINK firmware update design constraint:
  STLinkUpgrade.jar does NOT support targeting a specific device by serial,
  path, or index. When multiple ST-LINK V2/V2-1 devices are connected,
  the JAR enumerates all and processes only the FIRST one it finds.
  The experimental Windows PnP isolation path temporarily disables all
  non-target ST-LINK devices so the JAR can only see one device.
"""
import threading
import time
import platform
import serial.tools.list_ports

_root = None
_ui = None
_flash_worker = None
_usb_hint_event = threading.Event()
_stlink_rescan_event = threading.Event()

_stlink_devices = []
_stlink_raw_n = 0
_stlink_merged = 0
_stlink_update_in_progress = False
_stlink_pending_rescan = False
_stlink_last_physical_keys = None
_active_board = None
_board_generation = 0

_stlink_lock = threading.RLock()
_stlink_queue = []
_stlink_known_keys = set()
_stlink_slot_by_key = {}
_stlink_next_slot = 1
_stlink_worker_running = False
_stlink_current_key = None
_stlink_multi_blocked = False
_stlink_show_detecting_on_add = False
_stlink_completed_keys = set()
_stlink_multi_unfinished_keys = set()
_stlink_last_multi_signature = None
_stlink_isolation_running = False
_stlink_jre_ready = False
_stlink_jre_checking = False
def init(root, ui_module, flash_worker_module):
    global _root, _ui, _flash_worker
    _root = root
    _ui = ui_module
    _flash_worker = flash_worker_module


def get_esp_ports():
    try:
        supported_vids = {0x10C4, 0x1A86, 0x303A}
        return [p for p in serial.tools.list_ports.comports() if p.vid in supported_vids]
    except Exception:
        return []


def on_usb_change():
    _usb_hint_event.set()


def monitor_ports():
    last_ports = {p.device for p in get_esp_ports()}

    while True:
        got_hint = _usb_hint_event.wait(timeout=1.0)

        if got_hint:
            _usb_hint_event.clear()
            time.sleep(0.05)

        try:
            current_ports = get_esp_ports()
            current_set = {p.device for p in current_ports}
        except Exception:
            continue

        new_ports = current_set - last_ports - set(_ui.port_frames.keys())
        for port_name in new_ports:
            _handle_new_port(port_name, current_ports)

        _handle_removed_ports(current_set)
        last_ports = current_set


def _handle_new_port(port_name, current_ports):
    port_info = next((p for p in current_ports if p.device == port_name), None)
    port_type = ""
    if port_info:
        if port_info.vid == 0x10C4:
            port_type = " [CP2102]"
        elif port_info.vid == 0x1A86:
            port_type = " [CH343P]"
        elif port_info.vid == 0x303A:
            port_type = " [Native USB]"

    board_name = _flash_worker.get_board()
    _root.after(0, lambda p=port_name, pt=port_type: _ui.create_port_gui(p, pt))
    _root.after(0, _ui.update_subtitle)
    threading.Thread(
        target=_flash_worker.flash_device,
        args=(port_name, port_type, board_name),
        daemon=True,
    ).start()


def _handle_removed_ports(current_set):
    removed = set(_ui.port_frames.keys()) - current_set
    if not removed:
        return
    for port in removed:
        frame = _ui.port_frames.pop(port, None)
        if frame:
            _root.after(0, lambda f=frame: f.destroy())
        _ui.port_logs.pop(port, None)
        _ui.port_labels.pop(port, None)
        _ui.port_status_labels.pop(port, None)
        _ui.port_status_bars.pop(port, None)
        _ui.port_log_widgets.pop(port, None)
        _ui.port_accent_lines.pop(port, None)
    _root.after(0, _ui.adjust_window_size)
    _root.after(0, _ui.update_subtitle)
    _root.after(0, _ui.update_status_bar)


def _device_key(dev):
    return dev.dedupe_key or f"{dev.vid}:{dev.pid}:{dev.serial or dev.instance_id}"


def _experimental_pnp_isolation_enabled():
    if platform.system() != "Windows":
        return False
    try:
        _, config = _flash_worker.snapshot_board(_active_board)
        return bool(config.get("experimental_pnp_isolation"))
    except Exception:
        return False


def _debounce_trigger():
    time.sleep(0.15)
    _stlink_rescan_event.set()


def _monitor_stlink():
    global _stlink_pending_rescan
    while True:
        got_rescan = _stlink_rescan_event.wait(timeout=2.0)
        if not got_rescan:
            continue
        _stlink_rescan_event.clear()

        if not _is_stlink_board(_active_board):
            continue

        if _stlink_update_in_progress:
            with _stlink_lock:
                _stlink_pending_rescan = True
            _do_stlink_rescan(_board_generation, presence_only=True)
            continue

        _do_stlink_rescan(_board_generation)


def _do_stlink_rescan(generation, presence_only=False):
    global _stlink_show_detecting_on_add
    if not _is_stlink_board(_active_board):
        return
    if generation != _board_generation:
        print(f"[DEBUG] Ignore stale ST-LINK rescan: request_gen={generation} current_gen={_board_generation}")
        return

    try:
        from multi_flash.stlink.stlink_detector import detect_stlinks
        devs, raw_n, merged = detect_stlinks(v2_only=True)
        v2_devs = [d for d in devs if d.pid in {"3748", "374b", "374d"}]
        current_keys = frozenset(_device_key(d) for d in v2_devs)
        previous_keys = _stlink_last_physical_keys or frozenset()
        with _stlink_lock:
            show_detecting = _stlink_show_detecting_on_add
            _stlink_show_detecting_on_add = False
        should_show_detecting = show_detecting and bool(current_keys - previous_keys)
        apply_delay_ms = 250 if should_show_detecting else 0
        if should_show_detecting:
            _root.after(0, _ui.show_stlink_detecting_card)

        def update_ui():
            if generation != _board_generation:
                print(f"[DEBUG] Ignored ST-LINK apply because board changed (gen={generation} != {_board_generation})")
                return
            if presence_only:
                _apply_stlink_presence_ui(v2_devs, raw_n, merged)
            else:
                _apply_stlink_cards(v2_devs, raw_n, merged)

        _root.after(apply_delay_ms, update_ui)
    except Exception as e:
        with _stlink_lock:
            _stlink_show_detecting_on_add = False
        _root.after(0, _ui.hide_stlink_detecting_card)
        print(f"[ERROR] _do_stlink_rescan: {e}")


def _apply_stlink_presence_ui(devices, raw_n, merged):
    """Refresh ST-LINK cards during an active update without changing workers."""
    global _stlink_devices, _stlink_raw_n, _stlink_merged
    global _stlink_last_physical_keys, _stlink_next_slot

    if not _is_stlink_board(_active_board):
        return

    _ui.hide_stlink_detecting_card()
    _stlink_devices = list(devices)
    _stlink_raw_n = raw_n
    _stlink_merged = merged

    current_keys = frozenset(_device_key(d) for d in devices)
    keys_changed = _stlink_last_physical_keys is None or _stlink_last_physical_keys != current_keys
    _stlink_last_physical_keys = current_keys
    if keys_changed:
        print(f"[INFO] USB change during update. Raw={raw_n}, Physical={len(devices)}, Merged={merged}")

    device_by_key = {_device_key(d): d for d in devices}

    with _stlink_lock:
        removed = [key for key in list(_stlink_slot_by_key.keys()) if key not in current_keys]
        for key in removed:
            slot = _stlink_slot_by_key.pop(key, None)
            _stlink_known_keys.discard(key)
            _stlink_multi_unfinished_keys.discard(key)
            _stlink_queue[:] = [d for d in _stlink_queue if _device_key(d) != key]
            if slot is not None:
                _root.after(0, lambda s=slot: _ui.remove_stlink_slot(s))

        new_items = []
        for key, dev in device_by_key.items():
            if key in _stlink_slot_by_key:
                continue
            slot = _stlink_next_slot
            _stlink_next_slot += 1
            _stlink_slot_by_key[key] = slot
            _stlink_known_keys.add(key)
            new_items.append((slot, key, dev))

    if devices and not _ui.stlink_slot_frames:
        _ui.show_stlink_banner(len(devices))

    for slot, key, dev in new_items:
        _ui.create_stlink_slot(slot, dev.model)
        if key in _stlink_completed_keys:
            _ui.update_stlink_slot(slot, "UPDATED", "#4ade80", "#000000", "#275f3a")
            _ui.stlink_queue_log(slot, f"[DONE] Already updated in this session. PID={dev.pid.upper()}.")
        elif key == _stlink_current_key:
            _ui.update_stlink_slot(slot, "UPDATING", "#7aa2f7", "#ffffff", "#333355")
            _ui.stlink_queue_log(slot, f"[INFO] Update in progress. PID={dev.pid.upper()}.")
        else:
            _ui.update_stlink_slot(slot, "WAITING", "#f59e0b", "#000000", "#333355")
            _ui.stlink_queue_log(slot, f"[INFO] Waiting for current ST-LINK update to finish. PID={dev.pid.upper()}.")

    if not devices:
        _ui.update_subtitle()
        _ui.update_status_bar()
        return

    _ui.update_subtitle()
    _ui.update_status_bar()
def _apply_stlink_cards(devices, raw_n, merged):
    """
    Apply ST-LINK device cards.

    Three distinct states:
    - total_physical > 1: BLOCKED ??show all devices as blocked, no queue, no update.
    - total_physical == 1: NORMAL ??single device ready for update.
    - total_physical == 0: IDLE ??all cleared, no cards shown.

    Note: _stlink_known_keys tracks devices that have been successfully queued
    for update. Devices shown in BLOCKED state are NOT added to known_keys
    so they can be re-processed when the device count drops to 1.
    """
    global _stlink_devices, _stlink_raw_n, _stlink_merged
    global _stlink_last_physical_keys, _stlink_next_slot, _stlink_multi_blocked
    global _stlink_last_multi_signature, _stlink_multi_unfinished_keys
    global _stlink_jre_ready, _stlink_jre_checking

    if not _is_stlink_board(_active_board):
        return
    _ui.hide_stlink_detecting_card()

    _stlink_devices = list(devices)
    _stlink_raw_n = raw_n
    _stlink_merged = merged

    total_physical = len(devices)
    current_keys = frozenset(_device_key(d) for d in devices)
    keys_changed = _stlink_last_physical_keys is None or _stlink_last_physical_keys != current_keys
    _stlink_last_physical_keys = current_keys

    if keys_changed:
        print(f"[INFO] USB change. Raw={raw_n}, Physical={total_physical}, Merged={merged}")

    # =================================================================
    # ZERO DEVICES: total_physical == 0
    # =================================================================
    if total_physical == 0:
        _stlink_multi_blocked = False
        _stlink_last_multi_signature = None
        _stlink_multi_unfinished_keys.clear()
        with _stlink_lock:
            _stlink_queue.clear()
            _stlink_known_keys.clear()
            _stlink_slot_by_key.clear()
            _stlink_next_slot = 1

        _ui.clear_stlink_slots()
        _ui.queue_log("SYSTEM", "[INFO] No ST-LINK/V2 devices detected.")
        _ui.update_subtitle()
        _ui.update_status_bar()
        # Do NOT call _start_next_stlink_update()
        return

    # =================================================================
    # MULTI-DEVICE: total_physical > 1  ??BLOCKED
    # =================================================================
    if total_physical > 1:
        isolation_enabled = _experimental_pnp_isolation_enabled()
        _stlink_multi_blocked = not isolation_enabled
        completed_in_view = current_keys & _stlink_completed_keys
        multi_signature = (tuple(sorted(current_keys)), tuple(sorted(completed_in_view)))
        if _stlink_last_multi_signature == multi_signature and _ui.stlink_slot_frames:
            if isolation_enabled:
                _start_pnp_isolated_stlink_updates(devices)
            _ui.update_subtitle()
            _ui.update_status_bar()
            return
        _stlink_last_multi_signature = multi_signature
        _stlink_multi_unfinished_keys = set(current_keys - _stlink_completed_keys)

        with _stlink_lock:
            _stlink_queue.clear()
            _stlink_slot_by_key.clear()
            _stlink_next_slot = 1
            # Do NOT clear _stlink_known_keys here ??BLOCKED keys are not "queued"
            # They will be re-processed when device count drops to 1.

        _ui.queue_log("SYSTEM", f"[WARN] {total_physical} ST-LINKs detected!")
        if isolation_enabled:
            _ui.queue_log("SYSTEM",
                "[INFO] Experimental PnP isolation enabled.")
            _ui.queue_log("SYSTEM",
                "[INFO] Non-target ST-LINK devices will be temporarily disabled.")
        else:
            _ui.queue_log("SYSTEM",
                "[WARN] STLinkUpgrade.jar cannot select a specific attached ST-LINK.")
            _ui.queue_log("SYSTEM",
                "[WARN] Automatic sequential update is blocked until only one ST-LINK is visible.")

        # Always rebuild cards: clear old ones and create fresh BLOCKED cards.
        # This ensures transition from BLOCKED?뭆INGLE works correctly.
        _ui.clear_stlink_slots()

        if not _ui.stlink_slot_frames:
            _ui.show_stlink_banner(total_physical)

        for dev in devices:
            key = _device_key(dev)
            slot = _stlink_next_slot
            _stlink_next_slot += 1
            _stlink_slot_by_key[key] = slot
            _ui.create_stlink_slot(slot, dev.model)
            if key in _stlink_completed_keys:
                _ui.update_stlink_slot(
                    slot, "UPDATED", "#4ade80", "#000000", "#275f3a"
                )
                _ui.stlink_queue_log(
                    slot,
                    f"[DONE] Already updated in this session. PID={dev.pid.upper()}.",
                )
            else:
                with _stlink_lock:
                    _stlink_queue.append(dev)
                _ui.update_stlink_slot(
                    slot, "WAITING", "#f59e0b", "#000000", "#333355"
                )
                _ui.stlink_queue_log(
                    slot,
                    f"[INFO] Waiting for isolated update. PID={dev.pid.upper()}.",
                )

        _ui.update_subtitle()
        _ui.update_status_bar()
        if isolation_enabled:
            _start_pnp_isolated_stlink_updates(devices)
        return

    # =================================================================
    # SINGLE DEVICE: total_physical == 1 ??NORMAL
    # =================================================================
    # When transitioning from BLOCKED (multi?뭩ingle), _stlink_known_keys may
    # contain keys from the previous BLOCKED cards. Those are not "processed"
    # updates ??they are display-only BLOCKED markers. Clear them so the
    # single remaining device gets a fresh READY slot.
    if _stlink_multi_blocked:
        # Was BLOCKED; now single. Reset state for fresh single-device flow.
        with _stlink_lock:
            _stlink_known_keys.clear()
            _stlink_slot_by_key.clear()
            _stlink_next_slot = 1

    _stlink_multi_blocked = False
    _stlink_last_multi_signature = None

    device = devices[0]
    key = _device_key(device)
    force_update_from_multi = key in _stlink_multi_unfinished_keys

    if key in _stlink_known_keys and key in _stlink_slot_by_key:
        _ui.update_subtitle()
        _ui.update_status_bar()
        _start_next_stlink_update()
        return

    if key in _stlink_completed_keys and not force_update_from_multi:
        _ui.clear_stlink_slots()
        with _stlink_lock:
            _stlink_queue.clear()
            _stlink_known_keys.clear()
            _stlink_slot_by_key.clear()
            _stlink_next_slot = 1

            slot = _stlink_next_slot
            _stlink_next_slot += 1
            _stlink_slot_by_key[key] = slot
            _stlink_known_keys.add(key)

        _ui.create_stlink_slot(slot, device.model)
        _ui.update_stlink_slot(
            slot, "UPDATED", "#4ade80", "#000000", "#275f3a"
        )
        _ui.stlink_queue_log(
            slot,
            "[DONE] This ST-LINK was already updated successfully in this session. Auto-update skipped.",
        )
        _ui.update_subtitle()
        _ui.update_status_bar()
        return

    # If this exact key is already known and has a slot, the card already exists
    # (e.g. single device was re-detected after a brief blip ??no need to recreate).
    # Fresh single device: clear old cards and build READY slot.
    _ui.clear_stlink_slots()

    with _stlink_lock:
        _stlink_known_keys.clear()
        _stlink_slot_by_key.clear()
        _stlink_queue.clear()
        _stlink_next_slot = 1

        slot = _stlink_next_slot
        _stlink_next_slot += 1
        _stlink_slot_by_key[key] = slot
        _stlink_known_keys.add(key)
        _stlink_queue.append(device)
        _stlink_multi_unfinished_keys.discard(key)

    _ui.show_stlink_banner(1)
    _ui.create_stlink_slot(slot, device.model)
    _ui.update_stlink_slot(
        slot, "READY", "#555577", "#ffffff", "#333355"
    )
    _ui.stlink_queue_log(
        slot,
        f"[INFO] Ready: {device.model} PID={device.pid.upper()}.",
    )

    _ui.update_subtitle()
    _ui.update_status_bar()
    _start_next_stlink_update()


def _set_stlink_update_active(active):
    global _stlink_update_in_progress
    with _stlink_lock:
        _stlink_update_in_progress = active


def _start_next_stlink_update():
    global _stlink_worker_running, _stlink_current_key, _stlink_update_in_progress

    if not _is_stlink_board(_active_board):
        return

    # BLOCKED state: never start update with multiple devices present
    if _stlink_multi_blocked:
        return

    with _stlink_lock:
        if _stlink_worker_running or not _stlink_queue:
            return
        if not _stlink_jre_ready:
            _start_stlink_jre_preflight()
            return

        device = _stlink_queue.pop(0)
        key = _device_key(device)
        slot = _stlink_slot_by_key.get(key)
        _stlink_worker_running = True
        _stlink_current_key = key
        _stlink_update_in_progress = True

    _root.after(
        0,
        lambda s=slot: _ui.update_stlink_slot(
            s, "UPDATING", "#7aa2f7", "#ffffff", "#333355"
        ),
    )

    def run():
        try:
            _, config = _flash_worker.snapshot_board(_active_board)
            from multi_flash.stlink.stlink_worker import StlinkSequentialWorker

            worker = StlinkSequentialWorker(jar_path=config.get("jar_path"))
            if not worker.jar_path:
                _ui.stlink_queue_log(slot, "[ERROR] STLinkUpgrade.jar not found.")
                _root.after(
                    0,
                    lambda s=slot: _ui.update_stlink_slot(
                        s, "JAR NOT FOUND", "#f87171", "#000000", "#7a2d2d"
                    ),
                )
                return

            def log_cb(_worker_slot, message):
                _ui.stlink_queue_log(slot, message)
                lower_message = message.lower()
                if "firmware version detected" in lower_message:
                    _root.after(0, lambda s=slot: _ui.set_stlink_progress(s, 0.24, "#7aa2f7"))
                elif "upgrade is successful" in lower_message:
                    _root.after(0, lambda s=slot: _ui.set_stlink_progress(s, 0.90, "#7aa2f7"))
                elif "version read" in lower_message:
                    _root.after(0, lambda s=slot: _ui.set_stlink_progress(s, 0.97, "#7aa2f7"))

            final_status = {"value": None}

            def progress_cb(_worker_slot, status_text, label_bg, label_fg):
                final_status["value"] = status_text
                border_color = "#275f3a" if status_text in ("SUCCESS", "DONE", "UPDATED") else "#333355"
                _root.after(
                    0,
                    lambda s=slot, t=status_text, bg=label_bg, fg=label_fg, border=border_color: _ui.update_stlink_slot(
                        s, t, bg, fg, border
                    ),
                )

            # StlinkSequentialWorker processes the single connected ST-LINK.
            # JAR does not accept a device target argument; it always operates
            # on the first enumerated device.
            worker.flash_all([device], log_cb, progress_cb)
            if final_status["value"] == "SUCCESS":
                with _stlink_lock:
                    _stlink_completed_keys.add(key)
        except Exception as e:
            import traceback
            _ui.stlink_queue_log(slot, f"[ERROR] Worker crashed: {e}")
            print(f"[ERROR] ST-LINK worker crashed:\n{traceback.format_exc()}")
            _root.after(
                0,
                lambda s=slot: _ui.update_stlink_slot(
                    s, "FAILED", "#f87171", "#000000", "#7a2d2d"
                ),
            )
        finally:
            _finish_stlink_update()

    threading.Thread(target=run, daemon=True).start()


def _start_pnp_isolated_stlink_updates(all_devices):
    global _stlink_worker_running, _stlink_current_key, _stlink_update_in_progress
    global _stlink_isolation_running

    if not _is_stlink_board(_active_board) or not _experimental_pnp_isolation_enabled():
        return

    with _stlink_lock:
        if _stlink_worker_running or _stlink_isolation_running or not _stlink_queue:
            return
        if not _stlink_jre_ready:
            _start_stlink_jre_preflight()
            return
        pending_devices = list(_stlink_queue)
        _stlink_queue.clear()
        all_devices_snapshot = list(all_devices)
        _stlink_worker_running = True
        _stlink_isolation_running = True
        _stlink_update_in_progress = True

    def run():
        global _stlink_worker_running, _stlink_current_key, _stlink_update_in_progress
        global _stlink_isolation_running, _stlink_pending_rescan
        try:
            from multi_flash.stlink import pnp_isolation
            from multi_flash.stlink.stlink_detector import detect_stlinks
            _, config = _flash_worker.snapshot_board(_active_board)
            from multi_flash.stlink.stlink_worker import StlinkSequentialWorker

            worker = StlinkSequentialWorker(jar_path=config.get("jar_path"))
            if not worker.jar_path:
                _ui.queue_log("SYSTEM", "[ERROR] STLinkUpgrade.jar not found.")
                return

            for target in pending_devices:
                target_key = _device_key(target)
                slot = _stlink_slot_by_key.get(target_key)
                if slot is None:
                    continue
                if target_key in _stlink_completed_keys:
                    _root.after(
                        0,
                        lambda s=slot: _ui.update_stlink_slot(
                            s, "UPDATED", "#4ade80", "#000000", "#275f3a"
                        ),
                    )
                    continue

                disabled_ids = []
                _stlink_current_key = target_key
                _ui.stlink_queue_log(slot, "[INFO] PnP isolation: preparing target.")
                _root.after(
                    0,
                    lambda s=slot: _ui.update_stlink_slot(
                        s, "ISOLATING", "#f59e0b", "#000000", "#333355"
                    ),
                )

                try:
                    for other in all_devices_snapshot:
                        if _device_key(other) == target_key:
                            continue
                        ok, output = pnp_isolation.disable_device(other.instance_id)
                        if not ok:
                            _ui.stlink_queue_log(slot, f"[ERROR] Failed to disable non-target ST-LINK: {output}")
                            _root.after(
                                0,
                                lambda s=slot: _ui.update_stlink_slot(
                                    s, "PNP ERROR", "#f87171", "#000000", "#7a2d2d"
                                ),
                            )
                            return
                        disabled_ids.append(other.instance_id)
                        _ui.stlink_queue_log(slot, f"[INFO] Disabled non-target PID={other.pid.upper()} serial={other.serial}")

                    time.sleep(2.0)
                    visible, _, _ = detect_stlinks(v2_only=True, active_only=True)
                    disabled_id_set = {instance_id.lower() for instance_id in disabled_ids}
                    ignored_disabled = [
                        d for d in visible
                        if d.pid in {"3748", "374b", "374d"}
                        and d.instance_id.lower() in disabled_id_set
                    ]
                    for ignored in ignored_disabled:
                        _ui.stlink_queue_log(
                            slot,
                            f"[INFO] Ignoring disabled non-target still reported by PnP: {ignored.instance_id}",
                        )
                    visible_v2 = [
                        d for d in visible
                        if d.pid in {"3748", "374b", "374d"}
                        and d.instance_id.lower() not in disabled_id_set
                    ]
                    visible_keys = {_device_key(d) for d in visible_v2}
                    if visible_keys != {target_key}:
                        _ui.stlink_queue_log(
                            slot,
                            f"[ERROR] Isolation check failed. Visible targets={len(visible_v2)}",
                        )
                        _ui.stlink_queue_log(slot, f"[ERROR] Visible keys: {sorted(visible_keys)}")
                        _root.after(
                            0,
                            lambda s=slot: _ui.update_stlink_slot(
                                s, "ISOLATION FAIL", "#f87171", "#000000", "#7a2d2d"
                            ),
                        )
                        return

                    _ui.stlink_queue_log(slot, "[INFO] Isolation OK. Starting ST-LINK firmware update.")

                    def log_cb(_worker_slot, message, _slot=slot):
                        _ui.stlink_queue_log(_slot, message)
                        lower_message = message.lower()
                        if "firmware version detected" in lower_message:
                            _root.after(0, lambda s=_slot: _ui.set_stlink_progress(s, 0.24, "#7aa2f7"))
                        elif "upgrade is successful" in lower_message:
                            _root.after(0, lambda s=_slot: _ui.set_stlink_progress(s, 0.90, "#7aa2f7"))
                        elif "version read" in lower_message:
                            _root.after(0, lambda s=_slot: _ui.set_stlink_progress(s, 0.97, "#7aa2f7"))

                    final_status = {"value": None}

                    def progress_cb(_worker_slot, status_text, label_bg, label_fg, _slot=slot):
                        final_status["value"] = status_text
                        border_color = "#275f3a" if status_text in ("SUCCESS", "DONE", "UPDATED") else "#333355"
                        _root.after(
                            0,
                            lambda s=_slot, t=status_text, bg=label_bg, fg=label_fg, border=border_color: _ui.update_stlink_slot(
                                s, t, bg, fg, border
                            ),
                        )

                    worker.flash_all([target], log_cb, progress_cb)
                    if final_status["value"] == "SUCCESS":
                        with _stlink_lock:
                            _stlink_completed_keys.add(target_key)
                            _stlink_multi_unfinished_keys.discard(target_key)
                    else:
                        return
                finally:
                    for instance_id, ok, output in pnp_isolation.enable_devices(disabled_ids):
                        if ok:
                            _ui.stlink_queue_log(slot, f"[INFO] Re-enabled device: {instance_id}")
                        else:
                            _ui.stlink_queue_log(slot, f"[ERROR] Failed to re-enable device: {output}")
                    time.sleep(2.0)
        except Exception as e:
            import traceback
            _ui.queue_log("SYSTEM", f"[ERROR] PnP isolation worker crashed: {e}")
            print(f"[ERROR] PnP isolation worker crashed:\n{traceback.format_exc()}")
        finally:
            with _stlink_lock:
                _stlink_worker_running = False
                _stlink_isolation_running = False
                _stlink_current_key = None
                _stlink_update_in_progress = False
                _stlink_pending_rescan = False
            trigger_stlink_rescan(show_pending=False)

    threading.Thread(target=run, daemon=True).start()


def _finish_stlink_update():
    global _stlink_worker_running, _stlink_current_key, _stlink_update_in_progress
    global _stlink_pending_rescan

    with _stlink_lock:
        _stlink_worker_running = False
        _stlink_current_key = None
        _stlink_update_in_progress = False
        pending_rescan = _stlink_pending_rescan
        _stlink_pending_rescan = False

    if not _is_stlink_board(_active_board):
        return

    if pending_rescan:
        print("[INFO] Deferred ST-LINK rescan triggered after update")
        trigger_stlink_rescan(show_pending=False)
    else:
        # After update, re-check _stlink_multi_blocked before starting next
        if _stlink_multi_blocked:
            return
        _start_next_stlink_update()


def get_stlink_devices():
    return list(_stlink_devices)


def set_update_in_progress(val):
    global _stlink_update_in_progress, _stlink_pending_rescan
    with _stlink_lock:
        _stlink_update_in_progress = bool(val)
        should_rescan = not val and _stlink_pending_rescan
        if should_rescan:
            _stlink_pending_rescan = False
    if should_rescan:
        trigger_stlink_rescan(show_pending=False)


def _start_stlink_jre_preflight():
    """Install/verify Java with visible UI status when ST-LINK mode is selected."""
    global _stlink_jre_ready, _stlink_jre_checking
    with _stlink_lock:
        if _stlink_jre_ready or _stlink_jre_checking:
            return
        _stlink_jre_checking = True

    _root.after(
        0,
        lambda: _ui.show_stlink_jre_card(
            "CHECKING_JRE",
            "Checking or installing Java runtime...",
            "#6366f1",
            "#ffffff",
            "#333355",
            True,
        ),
    )

    def run():
        global _stlink_jre_ready, _stlink_jre_checking
        try:
            from multi_flash.helper.java_installer import ensure_jre, get_java_exe

            def log(message):
                _ui.queue_log("SYSTEM", message)
                if "Downloading JRE" in message:
                    _root.after(0, lambda: _ui.show_stlink_jre_card("DOWNLOADING", "Downloading Java runtime...", "#f59e0b", "#000000", "#8b7a20", True))
                elif "Extracting JRE" in message:
                    _root.after(0, lambda: _ui.show_stlink_jre_card("EXTRACTING", "Extracting Java runtime...", "#f59e0b", "#000000", "#8b7a20", True))
                elif "Verifying" in message:
                    _root.after(0, lambda: _ui.show_stlink_jre_card("VERIFYING", "Verifying Java runtime...", "#6366f1", "#ffffff", "#333355", True))

            ok = ensure_jre(progress_callback=log)
            with _stlink_lock:
                _stlink_jre_ready = bool(ok)
                _stlink_jre_checking = False
            if ok:
                java_exe = get_java_exe()
                _ui.queue_log("SYSTEM", f"[OK] Java ready: {java_exe}")
                _root.after(0, lambda p=java_exe: _ui.show_stlink_jre_card("JRE READY", p, "#4ade80", "#000000", "#275f3a", False))
                trigger_stlink_rescan(show_pending=False)
            else:
                _ui.queue_log("SYSTEM", "[ERROR] Java setup failed. ST-LINK update cannot start.")
                _root.after(0, lambda: _ui.show_stlink_jre_card("JRE ERROR", "Java setup failed. Check network or install Java manually.", "#f87171", "#000000", "#7a2d2d", False))
        except Exception as e:
            with _stlink_lock:
                _stlink_jre_ready = False
                _stlink_jre_checking = False
            _ui.queue_log("SYSTEM", f"[ERROR] Java setup crashed: {e}")
            _root.after(0, lambda err=str(e): _ui.show_stlink_jre_card("JRE ERROR", err, "#f87171", "#000000", "#7a2d2d", False))

    threading.Thread(target=run, daemon=True).start()
def set_active_board(board_key):
    global _active_board, _board_generation, _stlink_devices, _stlink_raw_n, _stlink_merged
    global _stlink_last_physical_keys, _stlink_pending_rescan, _stlink_next_slot, _stlink_current_key
    global _stlink_worker_running, _stlink_update_in_progress, _stlink_multi_blocked
    global _stlink_last_multi_signature, _stlink_multi_unfinished_keys
    global _stlink_jre_ready, _stlink_jre_checking

    if _active_board == board_key:
        return

    old_board = _active_board
    _board_generation += 1
    _active_board = board_key
    is_stlink = _is_stlink_board(board_key)

    print(f"[INFO] Active board changed: {board_key}")

    if is_stlink:
        _start_stlink_jre_preflight()
        trigger_stlink_rescan()
        return

    with _stlink_lock:
        _stlink_devices = []
        _stlink_raw_n = 0
        _stlink_merged = 0
        _stlink_last_physical_keys = None
        _stlink_pending_rescan = False
        _stlink_queue.clear()
        _stlink_known_keys.clear()
        _stlink_slot_by_key.clear()
        _stlink_next_slot = 1
        _stlink_current_key = None
        _stlink_worker_running = False
        _stlink_update_in_progress = False
        _stlink_multi_blocked = False
        _stlink_last_multi_signature = None
        _stlink_multi_unfinished_keys.clear()
        _stlink_jre_ready = False
        _stlink_jre_checking = False

    if old_board is None or _is_stlink_board(old_board):
        _root.after(0, _ui.clear_stlink_slots)
        _root.after(0, _ui.hide_stlink_jre_card)
        _root.after(0, _ui.update_subtitle)


def _is_stlink_board(board_key):
    from multi_flash.constants import BOARD_CONFIGS
    if board_key not in BOARD_CONFIGS:
        return False
    return BOARD_CONFIGS[board_key].get("kind") == "stlink_v2"


def trigger_stlink_rescan(show_pending=False):
    global _stlink_show_detecting_on_add
    if show_pending and _is_stlink_board(_active_board) and not _stlink_update_in_progress:
        with _stlink_lock:
            _stlink_show_detecting_on_add = True
    threading.Thread(target=_debounce_trigger, daemon=True).start()


def usb_monitor_thread():
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        from ctypes import wintypes
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            LRESULT = ctypes.c_int64
            WPARAM_TYPE = ctypes.c_uint64
            LPARAM_TYPE = ctypes.c_int64
        else:
            LRESULT = ctypes.c_long
            WPARAM_TYPE = ctypes.c_uint
            LPARAM_TYPE = ctypes.c_long

        WM_DEVICECHANGE = 0x0219
        DBT_DEVNODES_CHANGED = 0x0007

        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM_TYPE, LPARAM_TYPE)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HANDLE),
                ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HANDLE),
            ]

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM_TYPE, LPARAM_TYPE]
        user32.DefWindowProcW.restype = LRESULT
        user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
        user32.RegisterClassExW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.POINTER(None)]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = ctypes.c_bool
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_bool
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p

        def wnd_proc(hwnd, msg, wparam, lparam):
            try:
                if msg == WM_DEVICECHANGE and wparam == DBT_DEVNODES_CHANGED:
                    _root.after_idle(on_usb_change)
                    _root.after_idle(lambda: trigger_stlink_rescan(show_pending=True))
            except Exception as e:
                print(f"[ERROR] wnd_proc: {e}")
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        wnd_proc_cb = WNDPROC(wnd_proc)
        h_instance = kernel32.GetModuleHandleW(None)
        class_name = "ESPFlasherUSBMonitor_" + str(int(time.time()))

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = wnd_proc_cb
        wc.hInstance = h_instance
        wc.lpszClassName = class_name

        atom = user32.RegisterClassExW(ctypes.byref(wc))
        if not atom:
            return

        hwnd = user32.CreateWindowExW(
            0, class_name, "ESP Flasher USB Monitor", 0x00CF0000,
            0, 0, 1, 1, None, None, h_instance, None
        )
        if not hwnd:
            return

        user32.ShowWindow(hwnd, 0)
        print(f"[INFO] USB monitor started (hwnd={hwnd})")

        msg_struct = wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg_struct), None, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg_struct))
            user32.DispatchMessageW(ctypes.byref(msg_struct))

    except Exception as e:
        print(f"[ERROR] usb_monitor_thread: {e}")
        import traceback
        traceback.print_exc()


def start_usb_monitor():
    if platform.system() == "Windows":
        threading.Thread(target=usb_monitor_thread, daemon=True).start()
        threading.Thread(target=_monitor_stlink, daemon=True).start()
        print("[INFO] USB device monitor started")
        trigger_stlink_rescan(show_pending=False)










