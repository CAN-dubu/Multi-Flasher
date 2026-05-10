"""Windows PnP isolation helpers for experimental multi ST-LINK updates."""
import subprocess
from typing import Iterable


def _quote_ps_single(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_process(args: list[str], timeout: int) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except Exception as e:
        return False, str(e)

    output = "\n".join(
        part for part in (result.stdout.strip(), result.stderr.strip()) if part
    )
    return result.returncode == 0, output


def _run_powershell_pnp_command(cmdlet: str, instance_id: str, timeout: int = 30) -> tuple[bool, str]:
    # Pass the raw PnP InstanceId. Windows expects values like
    # USB\VID_0483&PID_3748\..., not URL-encoded USB%5CVID_...
    ps_command = (
        f"{cmdlet} -InstanceId {_quote_ps_single(instance_id)} "
        f"-Confirm:$false -ErrorAction Stop | Out-Null"
    )
    return _run_process(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_command,
        ],
        timeout,
    )


def _run_pnputil_command(action: str, instance_id: str, timeout: int = 30, force: bool = False) -> tuple[bool, str]:
    args = ["pnputil", action, instance_id]
    if force:
        args.append("/force")
    return _run_process(args, timeout)


def _combine_errors(primary_name: str, primary_output: str, fallback_name: str, fallback_output: str) -> str:
    parts = []
    if primary_output:
        parts.append(f"{primary_name}: {primary_output}")
    else:
        parts.append(f"{primary_name}: failed with no output")
    if fallback_output:
        parts.append(f"{fallback_name}: {fallback_output}")
    else:
        parts.append(f"{fallback_name}: failed with no output")
    return "\n".join(parts)


def disable_device(instance_id: str) -> tuple[bool, str]:
    ok, output = _run_powershell_pnp_command("Disable-PnpDevice", instance_id)
    if ok:
        return True, output

    fallback_ok, fallback_output = _run_pnputil_command(
        "/disable-device", instance_id, force=True
    )
    if fallback_ok:
        return True, fallback_output

    return False, _combine_errors(
        "Disable-PnpDevice", output, "pnputil /disable-device /force", fallback_output
    )


def enable_device(instance_id: str) -> tuple[bool, str]:
    ok, output = _run_powershell_pnp_command("Enable-PnpDevice", instance_id)
    if ok:
        return True, output

    fallback_ok, fallback_output = _run_pnputil_command("/enable-device", instance_id)
    if fallback_ok:
        return True, fallback_output

    return False, _combine_errors(
        "Enable-PnpDevice", output, "pnputil /enable-device", fallback_output
    )


def enable_devices(instance_ids: Iterable[str]) -> list[tuple[str, bool, str]]:
    results = []
    for instance_id in instance_ids:
        ok, output = enable_device(instance_id)
        results.append((instance_id, ok, output))
    return results
