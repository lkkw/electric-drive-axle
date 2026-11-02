from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from desktop import (
    DOTNET_RUNTIME_CONFIG_XML,
    HOST,
    configure_clr_startup,
    ensure_dotnet_config_file,
    prepare_dotnet_runtime,
    reserve_local_port,
    unblock_bundled_files,
    verify_dotnet_bridge,
)


def test_reserve_local_port_uses_loopback_and_os_assigned_port() -> None:
    listener, port = reserve_local_port()

    try:
        host, bound_port = listener.getsockname()
        assert host == HOST
        assert port == bound_port
        assert port > 0
    finally:
        listener.close()


def test_ensure_dotnet_config_file_writes_valid_xml(tmp_path: Path) -> None:
    exe_path = tmp_path / "Electric-Drive-Axle.exe"
    exe_path.write_bytes(b"")

    config_path = ensure_dotnet_config_file(exe_path)

    assert config_path == tmp_path / "Electric-Drive-Axle.exe.config"
    assert config_path.is_file()
    content = config_path.read_text(encoding="utf-8")
    assert content == DOTNET_RUNTIME_CONFIG_XML

    root = ET.fromstring(content)
    remote_sources = root.find("./runtime/loadFromRemoteSources")
    assert remote_sources is not None
    assert remote_sources.attrib.get("enabled") == "true"


def test_ensure_dotnet_config_file_falls_back_when_exe_dir_unavailable(tmp_path: Path) -> None:
    blocked_parent = tmp_path / "blocked_dir"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    unwritable_exe = blocked_parent / "Electric-Drive-Axle.exe"
    fallback_dir = tmp_path / "fallback_data"

    config_path = ensure_dotnet_config_file(unwritable_exe, fallback_dir=fallback_dir)

    assert config_path == fallback_dir / "clr_runtime.config"
    assert config_path.is_file()
    assert "loadFromRemoteSources" in config_path.read_text(encoding="utf-8")


def test_unblock_bundled_files_scans_binaries_safely(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "_internal" / "pythonnet" / "runtime"
    runtime_dir.mkdir(parents=True)
    dll_file = runtime_dir / "Python.Runtime.dll"
    dll_file.write_bytes(b"MZ")

    if sys.platform == "win32":
        ads_path = f"{dll_file}:Zone.Identifier"
        try:
            Path(ads_path).write_text("[ZoneTransfer]\r\nZoneId=3\r\n", encoding="ascii")
        except OSError:
            pass

    removed = unblock_bundled_files(tmp_path)
    assert removed >= 0
    if sys.platform == "win32":
        assert not Path(f"{dll_file}:Zone.Identifier").exists()


def test_prepare_dotnet_runtime_and_verify_bridge(tmp_path: Path) -> None:
    prepare_dotnet_runtime(tmp_path)
    if sys.platform == "win32":
        config_path = ensure_dotnet_config_file(tmp_path / "App.exe", fallback_dir=tmp_path)
        assert config_path is not None
        assert configure_clr_startup(config_path) is True
        verify_dotnet_bridge()
