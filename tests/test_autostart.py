import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock

from desktop_launcher.core import autostart as autostart_module
from desktop_launcher.core.autostart import (
    TASK_NAME,
    TASK_NAMESPACE,
    build_autostart_action,
    sync_autostart,
)


def completed(
    returncode: int = 0,
    stdout: bytes = b"",
    stderr: bytes = b"",
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(["schtasks"], returncode, stdout, stderr)


def test_frozen_action_uses_executable(tmp_path: Path) -> None:
    executable = tmp_path / "Desktop Launcher.exe"

    command, arguments = build_autostart_action(executable, frozen=True)

    assert command == str(executable.resolve())
    assert arguments == ""


def test_source_action_prefers_pythonw(tmp_path: Path) -> None:
    python = tmp_path / "python.exe"
    python.write_bytes(b"")
    pythonw = tmp_path / "pythonw.exe"
    pythonw.write_bytes(b"")

    command, arguments = build_autostart_action(python, frozen=False)

    assert command == str(pythonw.resolve())
    assert arguments == "-m desktop_launcher"


def test_source_action_falls_back_to_python(tmp_path: Path) -> None:
    python = tmp_path / "python.exe"
    python.write_bytes(b"")

    command, arguments = build_autostart_action(python, frozen=False)

    assert command == str(python.resolve())
    assert arguments == "-m desktop_launcher"


def test_task_tree_contains_expected_settings() -> None:
    tree = autostart_module._build_task_tree(
        "C:/App/app.exe",
        "-m desktop_launcher",
        "DOMAIN\\User",
    )
    ns = {"t": TASK_NAMESPACE}

    assert tree.findtext(".//t:Actions/t:Exec/t:Command", namespaces=ns) == (
        "C:/App/app.exe"
    )
    assert tree.findtext(".//t:Actions/t:Exec/t:Arguments", namespaces=ns) == (
        "-m desktop_launcher"
    )
    assert tree.findtext(
        ".//t:Triggers/t:LogonTrigger/t:UserId",
        namespaces=ns,
    ) == "DOMAIN\\User"
    assert tree.findtext(
        ".//t:Principals/t:Principal/t:LogonType",
        namespaces=ns,
    ) == "InteractiveToken"
    assert tree.findtext(
        ".//t:Principals/t:Principal/t:RunLevel",
        namespaces=ns,
    ) == "LeastPrivilege"
    assert tree.findtext(
        ".//t:Settings/t:MultipleInstancesPolicy",
        namespaces=ns,
    ) == "IgnoreNew"
    assert tree.findtext(
        ".//t:Settings/t:ExecutionTimeLimit",
        namespaces=ns,
    ) == "PT0S"
    assert tree.findtext(
        ".//t:Settings/t:DisallowStartIfOnBatteries",
        namespaces=ns,
    ) == "false"
    assert tree.findtext(
        ".//t:Settings/t:StopIfGoingOnBatteries",
        namespaces=ns,
    ) == "false"


def test_task_matches_command_and_arguments() -> None:
    tree = autostart_module._build_task_tree(
        "C:/App/app.exe",
        "-m desktop_launcher",
        "DOMAIN\\User",
    )

    assert autostart_module._task_matches(
        tree,
        "C:/App/app.exe",
        "-m desktop_launcher",
    )
    assert not autostart_module._task_matches(
        tree,
        "C:/App/other.exe",
        "-m desktop_launcher",
    )
    assert not autostart_module._task_matches(tree, "C:/App/app.exe", "")


def test_enabled_skips_matching_task(monkeypatch) -> None:
    command = "C:/App/app.exe"
    arguments = "-m desktop_launcher"
    root = autostart_module._build_task_tree(command, arguments, "DOMAIN\\User")
    create = Mock(return_value=None)
    monkeypatch.setattr(
        autostart_module,
        "build_autostart_action",
        lambda: (command, arguments),
    )
    monkeypatch.setattr(autostart_module, "_query_task_xml", lambda: root)
    monkeypatch.setattr(autostart_module, "_create_task", create)

    assert sync_autostart(True) is None
    create.assert_not_called()


def test_enabled_creates_missing_task(monkeypatch) -> None:
    command = "C:/App/app.exe"
    arguments = "-m desktop_launcher"
    create = Mock(return_value=None)
    monkeypatch.setattr(
        autostart_module,
        "build_autostart_action",
        lambda: (command, arguments),
    )
    monkeypatch.setattr(autostart_module, "_query_task_xml", lambda: None)
    monkeypatch.setattr(autostart_module, "_create_task", create)

    assert sync_autostart(True) is None
    create.assert_called_once_with(command, arguments)


def test_enabled_updates_stale_task(monkeypatch) -> None:
    command = "C:/App/app.exe"
    arguments = "-m desktop_launcher"
    stale = autostart_module._build_task_tree(
        "C:/Old/app.exe",
        arguments,
        "DOMAIN\\User",
    )
    create = Mock(return_value=None)
    monkeypatch.setattr(
        autostart_module,
        "build_autostart_action",
        lambda: (command, arguments),
    )
    monkeypatch.setattr(autostart_module, "_query_task_xml", lambda: stale)
    monkeypatch.setattr(autostart_module, "_create_task", create)

    assert sync_autostart(True) is None
    create.assert_called_once_with(command, arguments)


def test_enabled_query_error_returns_warning(monkeypatch) -> None:
    monkeypatch.setattr(
        autostart_module,
        "build_autostart_action",
        lambda: ("C:/App/app.exe", ""),
    )
    monkeypatch.setattr(
        autostart_module,
        "_query_task_xml",
        lambda: (_ for _ in ()).throw(OSError("boom")),
    )
    create = Mock()
    monkeypatch.setattr(autostart_module, "_create_task", create)

    warning = sync_autostart(True)

    assert warning is not None
    assert "设置开机自启动失败" in warning
    create.assert_not_called()


def test_disable_absent_task_does_nothing(monkeypatch) -> None:
    monkeypatch.setattr(autostart_module, "_task_exists", lambda: False)
    run = Mock()
    monkeypatch.setattr(autostart_module, "_run_schtasks", run)

    assert sync_autostart(False) is None
    run.assert_not_called()


def test_disable_existing_task(monkeypatch) -> None:
    monkeypatch.setattr(autostart_module, "_task_exists", lambda: True)
    run = Mock(return_value=completed(0))
    monkeypatch.setattr(autostart_module, "_run_schtasks", run)

    assert sync_autostart(False) is None
    run.assert_called_once_with("/Delete", "/TN", TASK_NAME, "/F")


def test_disable_failure_returns_warning(monkeypatch) -> None:
    monkeypatch.setattr(autostart_module, "_task_exists", lambda: True)
    monkeypatch.setattr(
        autostart_module,
        "_run_schtasks",
        lambda *args: completed(5),
    )

    warning = sync_autostart(False)

    assert warning is not None
    assert "关闭开机自启动失败" in warning


def test_create_task_writes_xml_and_cleans_temp(monkeypatch) -> None:
    captured: list[tuple[str, ...]] = []

    def fake_run(*args: str) -> subprocess.CompletedProcess[bytes]:
        captured.append(args)
        xml_path = Path(args[args.index("/XML") + 1])
        assert xml_path.is_file()
        content = xml_path.read_text(encoding="utf-16")
        assert "<Command>C:/App/app.exe</Command>" in content
        return completed(0)

    monkeypatch.setattr(autostart_module, "_current_user_id", lambda: "DOMAIN\\User")
    monkeypatch.setattr(autostart_module, "_run_schtasks", fake_run)

    assert (
        autostart_module._create_task(
            "C:/App/app.exe",
            "-m desktop_launcher",
        )
        is None
    )

    assert len(captured) == 1
    assert captured[0][0] == "/Create"
    xml_path = Path(captured[0][captured[0].index("/XML") + 1])
    assert not xml_path.exists()


def test_query_task_xml_parses_output(monkeypatch) -> None:
    tree = autostart_module._build_task_tree(
        "C:/App/app.exe",
        "",
        "DOMAIN\\User",
    )
    payload = ET.tostring(tree, encoding="unicode").encode("utf-8")
    monkeypatch.setattr(
        autostart_module,
        "_run_schtasks",
        lambda *args: completed(0, stdout=payload),
    )

    root = autostart_module._query_task_xml()

    assert root is not None
    assert autostart_module._task_matches(root, "C:/App/app.exe", "")


def test_query_task_xml_parses_ansi_output(monkeypatch) -> None:
    tree = autostart_module._build_task_tree(
        "C:/App/app.exe",
        "",
        "DOMAIN\\User",
    )
    payload = ET.tostring(tree, encoding="unicode").encode("gbk")
    monkeypatch.setattr(
        autostart_module,
        "_run_schtasks",
        lambda *args: completed(0, stdout=payload),
    )

    root = autostart_module._query_task_xml()

    assert root is not None
    assert autostart_module._task_matches(root, "C:/App/app.exe", "")
