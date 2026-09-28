"""Tests for python-functions.sh, using fake interpreters and package managers.

Tests use Python minor versions such as 3.60 so that real interpreters in
/usr/bin (which find_python always searches) can never satisfy them.
"""
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "python-functions.sh"

FAKE_PYTHON = """#!/bin/bash
PATH=/usr/bin:/bin
echo "$0 $*" >> "$FAKE_STATE/python.log"
case "$1" in
    -c)
        exec {real} -c "import sys; sys.version_info = ({major}, {minor}, 0); exec(sys.argv[1])" "$2"
        ;;
    -m)
        case "$2" in
            pip)
                [[ -f "$FAKE_STATE/pip" ]] || exit 1
                [[ "$3" == --version ]] && exit 0
                case "$FAKE_PIP_INSTALL" in
                    fail) exit 1 ;;
                    pep668) [[ " $* " == *" --break-system-packages "* ]] || exit 1 ;;
                esac
                touch "$FAKE_STATE/virtualenv"
                ;;
            ensurepip)
                [[ -n "$FAKE_ENSUREPIP_FAIL" ]] && exit 1
                touch "$FAKE_STATE/pip"
                ;;
            virtualenv)
                [[ -f "$FAKE_STATE/virtualenv" ]] || exit 1
                ;;
            *) exit 1 ;;
        esac
        ;;
    *) exit 1 ;;
esac
"""

FAKE_PACKAGE_MANAGER = """#!/bin/bash
PATH=/usr/bin:/bin
echo "$(basename "$0") $*" >> "$FAKE_STATE/pm.log"
[[ -n "$FAKE_PM_FAIL" ]] && exit 1
for arg in "$@"; do
    case "$arg" in
        *-pip) touch "$FAKE_STATE/pip" ;;
        python3.60|python360)
            cp "$FAKE_STATE/python-template" "$FAKE_BIN/python3.60"
            chmod +x "$FAKE_BIN/python3.60"
            ;;
    esac
done
"""


def _write_executable(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _fake_python_source(major: int, minor: int) -> str:
    return FAKE_PYTHON.format(real=sys.executable, major=major, minor=minor)


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.bin = tmp_path / "bin"
        self.state = tmp_path / "state"
        self.bin.mkdir()
        self.state.mkdir()
        (self.state / "python-template").write_text(_fake_python_source(3, 60))
        self.env = {
            "PATH": str(self.bin),
            "HOME": str(tmp_path),
            "FAKE_STATE": str(self.state),
            "FAKE_BIN": str(self.bin),
        }

    def python(self, name: str, major: int, minor: int, directory: Optional[Path] = None) -> Path:
        return _write_executable((directory or self.bin) / name, _fake_python_source(major, minor))

    def package_manager(self, name: str) -> None:
        _write_executable(self.bin / name, FAKE_PACKAGE_MANAGER)

    def with_pip(self) -> None:
        (self.state / "pip").touch()

    def with_virtualenv(self) -> None:
        (self.state / "virtualenv").touch()

    def log(self, name: str) -> str:
        path = self.state / name
        return path.read_text() if path.exists() else ""

    def run(self, *args: str, setup: str = "") -> subprocess.CompletedProcess:
        command = 'source "$1"; shift; %s\nfind_python "$@"\necho "PYTHON=$PYTHON"' % setup
        return subprocess.run(
            ["/bin/bash", "-c", command, "bash", str(SCRIPT), *args],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=60,
        )


def _stdout_lines(result: subprocess.CompletedProcess) -> List[str]:
    return result.stdout.strip().splitlines()


def _assert_found(result: subprocess.CompletedProcess, expected: Path) -> None:
    assert result.returncode == 0, result.stderr
    assert _stdout_lines(result) == [str(expected), "PYTHON=%s" % expected]


def _assert_failed(result: subprocess.CompletedProcess, message: str) -> None:
    assert result.returncode != 0
    assert "PYTHON=" not in result.stdout
    assert message in result.stderr


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def test_sourcing_has_no_side_effects(harness: Harness) -> None:
    result = subprocess.run(
        ["/bin/bash", "-c", 'source "$1" && echo sourced', "bash", str(SCRIPT)],
        env=harness.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    assert result.returncode == 0
    assert result.stdout == "sourced\n"
    assert result.stderr == ""


def test_defaults_to_minimum_3_11(harness: Harness) -> None:
    expected = harness.python("python3.30", 3, 30)
    _assert_found(harness.run(), expected)


def test_prefers_newest_versioned_python(harness: Harness) -> None:
    harness.python("python3", 3, 70)
    harness.python("python3.61", 3, 61)
    expected = harness.python("python3.62", 3, 62)
    _assert_found(harness.run("3.60"), expected)


def test_falls_back_to_python3(harness: Harness) -> None:
    expected = harness.python("python3", 3, 60)
    _assert_found(harness.run("3.60"), expected)


def test_skips_candidates_below_minimum(harness: Harness) -> None:
    harness.python("python3", 3, 59)
    expected = harness.python("python", 3, 60)
    _assert_found(harness.run("3.60"), expected)


def test_excludes_jetpack_embedded_bin(harness: Harness, tmp_path: Path) -> None:
    jetpack_bin = tmp_path / "jetpack" / "bin"
    harness.python("python3.65", 3, 65, directory=jetpack_bin)
    expected = harness.python("python3.60", 3, 60)
    harness.env["PATH"] = "%s/:%s" % (jetpack_bin, harness.bin)
    result = harness.run("3.60", setup='_PYTHON_EXCLUDED_DIR="%s"' % jetpack_bin)
    _assert_found(result, expected)


def test_excluded_dir_is_jetpack_embedded_bin(harness: Harness) -> None:
    result = subprocess.run(
        ["/bin/bash", "-c", 'source "$1" && echo "$_PYTHON_EXCLUDED_DIR"', "bash", str(SCRIPT)],
        env=harness.env,
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )
    assert result.stdout.strip() == "/opt/cycle/jetpack/system/embedded/bin"


def test_not_found_without_install_fails(harness: Harness) -> None:
    harness.package_manager("dnf")
    harness.python("python3", 3, 59)
    _assert_failed(harness.run("3.60", "0"), "Could not find python >= 3.60")
    assert harness.log("pm.log") == ""


@pytest.mark.parametrize(
    "manager, expected_log",
    [
        ("dnf", "dnf install -y -q python3.60 python3.60-pip\n"),
        ("yum", "yum install -y -q python3.60 python3.60-pip\n"),
        (
            "apt-get",
            "apt-get update -qq\napt-get install -y -q python3.60 python3.60-venv python3-pip\n",
        ),
        ("zypper", "zypper --non-interactive --quiet install python360 python360-pip\n"),
    ],
)
def test_installs_python_when_missing(harness: Harness, manager: str, expected_log: str) -> None:
    harness.package_manager(manager)
    _assert_found(harness.run("3.60", "1"), harness.bin / "python3.60")
    assert harness.log("pm.log") == expected_log


def test_install_failure_fails(harness: Harness) -> None:
    harness.package_manager("dnf")
    harness.env["FAKE_PM_FAIL"] = "1"
    _assert_failed(harness.run("3.60", "1"), "Failed to install python3.60")


def test_install_without_package_manager_fails(harness: Harness) -> None:
    result = harness.run("3.60", "1")
    _assert_failed(result, "Failed to install python3.60")
    assert "No supported package manager" in result.stderr


def test_custom_python_is_used_over_search(harness: Harness, tmp_path: Path) -> None:
    harness.python("python3.70", 3, 70)
    custom = harness.python("python", 3, 60, directory=tmp_path / "custom")
    _assert_found(harness.run("3.60", "1", "0", str(custom)), custom)


def test_custom_python_below_minimum_fails(harness: Harness, tmp_path: Path) -> None:
    harness.package_manager("dnf")
    custom = harness.python("python", 3, 59, directory=tmp_path / "custom")
    result = harness.run("3.60", "1", "1", str(custom))
    _assert_failed(result, "does not meet the minimum version 3.60")
    assert harness.log("pm.log") == ""


def test_custom_python_not_executable_fails(harness: Harness, tmp_path: Path) -> None:
    custom = tmp_path / "python"
    custom.write_text("")
    _assert_failed(harness.run("3.60", "0", "0", str(custom)), "is not an executable file")
    _assert_failed(harness.run("3.60", "0", "0", str(tmp_path / "missing")), "is not an executable file")


def test_skips_pip_and_virtualenv_when_not_requested(harness: Harness) -> None:
    expected = harness.python("python3.60", 3, 60)
    _assert_found(harness.run("3.60", "0", "0"), expected)
    assert " -m " not in harness.log("python.log")


def test_existing_pip_and_virtualenv_are_left_alone(harness: Harness) -> None:
    harness.package_manager("dnf")
    harness.with_pip()
    harness.with_virtualenv()
    expected = harness.python("python3.60", 3, 60)
    _assert_found(harness.run("3.60", "0", "1"), expected)
    assert harness.log("pm.log") == ""
    assert "install" not in harness.log("python.log")


def test_installs_pip_via_package_manager(harness: Harness) -> None:
    harness.package_manager("dnf")
    expected = harness.python("python3.60", 3, 60)
    _assert_found(harness.run("3.60", "0", "1"), expected)
    assert harness.log("pm.log") == "dnf install -y -q python3.60-pip\n"
    assert "ensurepip" not in harness.log("python.log")
    assert "-m pip install -q virtualenv" in harness.log("python.log")


def test_falls_back_to_ensurepip(harness: Harness) -> None:
    expected = harness.python("python3.60", 3, 60)
    result = harness.run("3.60", "0", "1")
    _assert_found(result, expected)
    assert "WARNING: Failed to install pip via the package manager" in result.stderr
    assert "-m ensurepip --upgrade" in harness.log("python.log")


def test_custom_python_uses_ensurepip_not_package_manager(harness: Harness, tmp_path: Path) -> None:
    harness.package_manager("dnf")
    custom = harness.python("python", 3, 60, directory=tmp_path / "custom")
    _assert_found(harness.run("3.60", "0", "1", str(custom)), custom)
    assert harness.log("pm.log") == ""
    assert "%s -m ensurepip --upgrade" % custom in harness.log("python.log")
    assert "%s -m pip install -q virtualenv" % custom in harness.log("python.log")


def test_pip_unavailable_fails(harness: Harness) -> None:
    harness.python("python3.60", 3, 60)
    harness.env["FAKE_ENSUREPIP_FAIL"] = "1"
    _assert_failed(harness.run("3.60", "0", "1"), "Could not install pip for")


def test_virtualenv_retries_for_externally_managed_python(harness: Harness) -> None:
    harness.with_pip()
    harness.env["FAKE_PIP_INSTALL"] = "pep668"
    expected = harness.python("python3.60", 3, 60)
    _assert_found(harness.run("3.60", "0", "1"), expected)
    assert "-m pip install -q --break-system-packages virtualenv" in harness.log("python.log")


def test_virtualenv_unavailable_fails(harness: Harness) -> None:
    harness.with_pip()
    harness.env["FAKE_PIP_INSTALL"] = "fail"
    harness.python("python3.60", 3, 60)
    _assert_failed(harness.run("3.60", "0", "1"), "Could not install virtualenv for")


@pytest.mark.parametrize(
    "args, message",
    [
        (["abc"], "Invalid min_version 'abc'"),
        (["3"], "Invalid min_version '3'"),
        (["3.11.1"], "Invalid min_version '3.11.1'"),
        (["3.11", "2"], "install_python must be 0 or 1"),
        (["3.11", "0", "yes"], "ensure_pip_and_virtualenv must be 0 or 1"),
    ],
)
def test_invalid_arguments_fail(harness: Harness, args: List[str], message: str) -> None:
    _assert_failed(harness.run(*args), message)


def test_failure_exits_calling_script(harness: Harness) -> None:
    result = subprocess.run(
        ["/bin/bash", "-c", 'source "$1"; find_python 3.60; echo after', "bash", str(SCRIPT)],
        env=harness.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    assert result.returncode == 1
    assert "after" not in result.stdout


def test_script_is_executable() -> None:
    assert os.access(str(SCRIPT), os.X_OK)
