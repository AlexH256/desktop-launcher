import getpass
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

TASK_NAME = "DesktopLauncher"
TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
SCHTASKS_TIMEOUT = 5.0
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

ET.register_namespace("", TASK_NAMESPACE)


def _tag(name: str) -> str:
    return f"{{{TASK_NAMESPACE}}}{name}"


def _nuitka_executable() -> Path | None:
    compiled = globals().get("__compiled__")
    if compiled is None:
        return None

    process_exe = getattr(compiled, "process_exe", None)
    if process_exe:
        return Path(str(process_exe))

    if sys.argv and sys.argv[0]:
        return Path(sys.argv[0])

    return None


def build_autostart_action(
    executable: Path | None = None,
    frozen: bool | None = None,
) -> tuple[str, str]:
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False)) or "__compiled__" in globals()

    if executable is None:
        if frozen:
            executable = _nuitka_executable() or sys.executable
        else:
            executable = sys.executable

    executable_path = Path(executable).expanduser()
    try:
        executable_path = executable_path.resolve(strict=False)
    except OSError:
        executable_path = executable_path.absolute()

    if frozen:
        return str(executable_path), ""

    pythonw_path = executable_path.with_name("pythonw.exe")
    interpreter = pythonw_path if pythonw_path.is_file() else executable_path
    return str(interpreter), "-m desktop_launcher"


def _current_user_id() -> str:
    domain = os.environ.get("USERDOMAIN", "").strip()
    user = os.environ.get("USERNAME", "").strip()
    if domain and user:
        return f"{domain}\\{user}"
    return getpass.getuser()


def _build_task_tree(
    command: str,
    arguments: str,
    user: str,
) -> ET.Element:
    root = ET.Element(_tag("Task"), {"version": "1.2"})

    registration = ET.SubElement(root, _tag("RegistrationInfo"))
    ET.SubElement(registration, _tag("Description")).text = (
        "Desktop Launcher 开机自启动"
    )

    triggers = ET.SubElement(root, _tag("Triggers"))
    logon_trigger = ET.SubElement(triggers, _tag("LogonTrigger"))
    ET.SubElement(logon_trigger, _tag("Enabled")).text = "true"
    ET.SubElement(logon_trigger, _tag("UserId")).text = user

    principals = ET.SubElement(root, _tag("Principals"))
    principal = ET.SubElement(principals, _tag("Principal"), {"id": "Author"})
    ET.SubElement(principal, _tag("UserId")).text = user
    ET.SubElement(principal, _tag("LogonType")).text = "InteractiveToken"
    ET.SubElement(principal, _tag("RunLevel")).text = "LeastPrivilege"

    settings = ET.SubElement(root, _tag("Settings"))
    ET.SubElement(settings, _tag("MultipleInstancesPolicy")).text = "IgnoreNew"
    ET.SubElement(settings, _tag("DisallowStartIfOnBatteries")).text = "false"
    ET.SubElement(settings, _tag("StopIfGoingOnBatteries")).text = "false"
    ET.SubElement(settings, _tag("AllowHardTerminate")).text = "true"
    ET.SubElement(settings, _tag("StartWhenAvailable")).text = "false"
    ET.SubElement(settings, _tag("RunOnlyIfNetworkAvailable")).text = "false"
    idle = ET.SubElement(settings, _tag("IdleSettings"))
    ET.SubElement(idle, _tag("StopOnIdleEnd")).text = "true"
    ET.SubElement(idle, _tag("RestartOnIdle")).text = "false"
    ET.SubElement(settings, _tag("AllowStartOnDemand")).text = "true"
    ET.SubElement(settings, _tag("Enabled")).text = "true"
    ET.SubElement(settings, _tag("Hidden")).text = "false"
    ET.SubElement(settings, _tag("RunOnlyIfIdle")).text = "false"
    ET.SubElement(settings, _tag("WakeToRun")).text = "false"
    ET.SubElement(settings, _tag("ExecutionTimeLimit")).text = "PT0S"
    ET.SubElement(settings, _tag("Priority")).text = "7"

    actions = ET.SubElement(root, _tag("Actions"), {"Context": "Author"})
    action = ET.SubElement(actions, _tag("Exec"))
    ET.SubElement(action, _tag("Command")).text = command
    if arguments:
        ET.SubElement(action, _tag("Arguments")).text = arguments

    return root


def _run_schtasks(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["schtasks", *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=SCHTASKS_TIMEOUT,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )


def _decode_output(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("mbcs", errors="replace")


def _query_task_xml() -> ET.Element | None:
    result = _run_schtasks("/Query", "/TN", TASK_NAME, "/XML")
    if result.returncode != 0:
        return None
    try:
        text = _decode_output(result.stdout).lstrip("\ufeff")
        return ET.fromstring(text)
    except ET.ParseError:
        return None


def _task_matches(
    root: ET.Element,
    command: str,
    arguments: str,
) -> bool:
    actions = root.find(f".//{_tag('Actions')}")
    if actions is None:
        return False

    exec_actions = actions.findall(_tag("Exec"))
    if len(exec_actions) != 1:
        return False

    stored_command = (exec_actions[0].findtext(_tag("Command")) or "").strip()
    stored_arguments = (exec_actions[0].findtext(_tag("Arguments")) or "").strip()
    if not stored_command:
        return False

    stored_command = stored_command.strip('"')
    try:
        stored_path = os.path.normcase(os.path.abspath(stored_command))
        expected_path = os.path.normcase(os.path.abspath(command))
    except (OSError, ValueError):
        return False

    return stored_path == expected_path and stored_arguments == arguments.strip()


def _task_exists() -> bool:
    result = _run_schtasks("/Query", "/TN", TASK_NAME)
    return result.returncode == 0


def _create_task(command: str, arguments: str) -> str | None:
    temporary_path: Path | None = None
    try:
        tree = _build_task_tree(command, arguments, _current_user_id())
        with tempfile.NamedTemporaryFile(
            "wb",
            suffix=".xml",
            prefix="desktop-launcher-task-",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            ET.ElementTree(tree).write(
                file,
                encoding="utf-16",
                xml_declaration=True,
            )

        result = _run_schtasks(
            "/Create",
            "/TN",
            TASK_NAME,
            "/XML",
            str(temporary_path),
            "/F",
        )
        if result.returncode != 0:
            return _format_schtasks_error("设置开机自启动失败", result)
        return None
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"设置开机自启动失败：{exc}"
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _remove_task() -> str | None:
    try:
        if not _task_exists():
            return None
        result = _run_schtasks("/Delete", "/TN", TASK_NAME, "/F")
        if result.returncode != 0:
            return _format_schtasks_error("关闭开机自启动失败", result)
        return None
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"关闭开机自启动失败：{exc}"


def _ensure_task(command: str, arguments: str) -> str | None:
    try:
        root = _query_task_xml()
        if root is not None and _task_matches(root, command, arguments):
            return None
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"设置开机自启动失败：{exc}"
    return _create_task(command, arguments)


def _format_schtasks_error(
    prefix: str,
    result: subprocess.CompletedProcess[bytes],
) -> str:
    return f"{prefix}（schtasks 退出码 {result.returncode}）"


def sync_autostart(enabled: bool) -> str | None:
    command, arguments = build_autostart_action()
    if enabled:
        return _ensure_task(command, arguments)
    return _remove_task()
