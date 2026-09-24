import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FindPythonTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.bin_dir = self.root / "bin with spaces"
        self.bin_dir.mkdir()
        self.call_log = self.root / "calls"
        self.install_source = self.root / "installed-python"
        self.write_python(self.install_source, (3, 11, 0))
        self.env = dict(os.environ, PATH=str(self.bin_dir),
                        BIN_DIR=str(self.bin_dir), CALL_LOG=str(self.call_log),
                        INSTALL_SOURCE=str(self.install_source),
                        PACKAGE_EXIT="0", UPDATE_EXIT="0", SKIP_INSTALL="0")

    def write_tool(self, path, content):
        path.write_text(content)
        path.chmod(0o755)

    def write_python(self, path, version, executable=None):
        self.write_tool(path, f"""#!{sys.executable}
import sys
sys.version_info = {version!r}
sys.executable = {str(executable or path)!r}
sys.argv = sys.argv[2:]
exec(sys.argv[0])
""")

    def write_package_manager(self, name):
        self.write_tool(self.bin_dir / name, """#!/bin/bash
printf '%s\n' "$*" >> "$CALL_LOG"
echo 'Package manager output'
if [[ $1 == update ]]; then
    exit "$UPDATE_EXIT"
fi
if [[ $PACKAGE_EXIT != 0 ]]; then
    exit "$PACKAGE_EXIT"
fi
if [[ $SKIP_INSTALL == 0 ]]; then
    /bin/cp "$INSTALL_SOURCE" "$BIN_DIR/python3.11"
fi
""")

    def find_python(self, *args):
        return subprocess.run(
            ["/bin/bash", "-eu", "-c", 'source "$1"; shift; find_python "$@"',
             "bash", str(ROOT / "python-functions.sh"), *args],
            cwd=self.root, env=self.env, capture_output=True, text=True)

    def test_numeric_minimum(self):
        for version, accepted in (((3, 9, 0), False), ((3, 10, 0), False),
                                  ((3, 11, 0), True), ((3, 12, 0), True)):
            with self.subTest(version=version):
                candidate = self.bin_dir / "python3"
                self.write_python(candidate, version)
                result = self.find_python()
                self.assertEqual(result.returncode, 0 if accepted else 1, result.stderr)
                self.assertEqual(result.stdout, f"{candidate}\n" if accepted else "")

    def test_versioned_python_and_broken_candidates(self):
        self.write_tool(self.bin_dir / "python3", "#!/bin/bash\necho broken >&2\nexit 1\n")
        self.write_python(self.bin_dir / "python3.10", (3, 10, 0))
        candidate = self.bin_dir / "python3.12"
        self.write_python(candidate, (3, 12, 0))
        result = self.find_python("3.12")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"{candidate}\n")
        self.assertEqual(result.stderr, "")

    def test_searches_later_path_entries(self):
        self.write_python(self.bin_dir / "python3", (3, 9, 0))
        candidate = self.root / "python3"
        self.write_python(candidate, (3, 11, 0))
        self.env["PATH"] += f":{self.root}"
        result = self.find_python()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"{candidate}\n")

    def test_rejects_jetpack_executable_and_finds_later_python(self):
        for name in ("python3", "python3.11"):
            with self.subTest(name=name):
                self.write_python(self.bin_dir / name, (3, 11, 0),
                                  f"/opt/cycle/jetpack/system/embedded/bin/{name}")
                result = self.find_python()
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                candidate = self.root / "python3"
                self.write_python(candidate, (3, 11, 0))
                self.env["PATH"] = f"{self.bin_dir}:{self.root}"
                result = self.find_python()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f"{candidate}\n")
                self.env["PATH"] = str(self.bin_dir)
                candidate.unlink()
                (self.bin_dir / name).unlink()

    def test_missing_python_does_not_install_by_default(self):
        self.write_package_manager("yum")
        result = self.find_python()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.call_log.exists())

    def test_install_and_rediscover(self):
        for manager in ("yum", "apt-get"):
            with self.subTest(manager=manager):
                self.write_package_manager(manager)
                self.write_python(self.bin_dir / "python3", (3, 10, 0))
                result = self.find_python("3.11", "1")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f"{self.bin_dir / 'python3.11'}\n")
                self.assertIn("Package manager output", result.stderr)
                expected = "install -y -q python3.11\n"
                if manager == "apt-get":
                    expected = "update\n" + expected
                self.assertEqual(self.call_log.read_text(), expected)
                (self.bin_dir / manager).unlink()
                (self.bin_dir / "python3.11").unlink()
                self.call_log.unlink()

    def test_failed_install_or_missing_executable(self):
        self.write_package_manager("yum")
        for variable in ("PACKAGE_EXIT", "SKIP_INSTALL"):
            with self.subTest(variable=variable):
                self.env[variable] = "1"
                result = self.find_python("3.11", "1")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.call_log.read_text(), "install -y -q python3.11\n")
                self.env[variable] = "0"
                self.call_log.unlink()

    def test_failed_apt_update_does_not_install(self):
        self.write_package_manager("apt-get")
        self.env["UPDATE_EXIT"] = "1"
        result = self.find_python("3.11", "1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.call_log.read_text(), "update\n")

    def test_missing_package_manager(self):
        result = self.find_python("3.11", "1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Cannot install Python automatically", result.stderr)

    def test_invalid_minimum_does_not_install(self):
        self.write_package_manager("yum")
        result = self.find_python("invalid", "1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.call_log.exists())


class EnsurePipAndVenvTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.python_path = self.root / "python with spaces"
        self.call_log = self.root / "calls"
        self.env = dict(os.environ, PATH=str(self.root), STATE_DIR=str(self.root),
                        BOOTSTRAP="0", PACKAGE_EXIT="0", UPDATE_EXIT="0",
                        SKIP_INSTALL="0", VIRTUALENV_EXIT="0", SKIP_VIRTUALENV="0")
        self.write_tool(self.python_path, """#!/bin/bash
printf '%s\n' "$*" >> "$STATE_DIR/calls"
case "$*" in
    '-m pip --version') [[ -f "$STATE_DIR/pip" ]] ;;
    '-m virtualenv --version') [[ -f "$STATE_DIR/virtualenv" ]] ;;
    '-m pip install -q virtualenv')
        echo 'pip install output'
        [[ $VIRTUALENV_EXIT == 0 ]] || exit "$VIRTUALENV_EXIT"
        if [[ $SKIP_VIRTUALENV == 0 ]]; then
            printf ready > "$STATE_DIR/virtualenv"
        fi
        ;;
    '-m ensurepip --upgrade')
        echo 'ensurepip output'
        [[ $BOOTSTRAP == 1 ]] || exit 1
        printf ready > "$STATE_DIR/pip"
        ;;
    '-c '*) echo 3.11 ;;
    *) exit 1 ;;
esac
""")

    def write_tool(self, path, content):
        path.write_text(content)
        path.chmod(0o755)

    def write_package_manager(self, name):
        self.write_tool(self.root / name, """#!/bin/bash
printf '%s\n' "$*" >> "$STATE_DIR/calls"
echo 'Package manager output'
if [[ $1 == update ]]; then exit "$UPDATE_EXIT"; fi
if [[ $PACKAGE_EXIT != 0 ]]; then exit "$PACKAGE_EXIT"; fi
if [[ $SKIP_INSTALL == 0 ]]; then
    printf ready > "$STATE_DIR/pip"
fi
""")

    def ensure(self, *args):
        return subprocess.run(
            ["/bin/bash", "-eu", "-c", 'source "$1"; shift; ensure_pip_and_venv "$@"',
             "bash", str(ROOT / "python-functions.sh"), *args],
            cwd=self.root, env=self.env, capture_output=True, text=True)

    def test_already_available(self):
        (self.root / "pip").touch()
        (self.root / "virtualenv").touch()
        result = self.ensure(str(self.python_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertNotIn("-m ensurepip", self.call_log.read_text())
        self.assertNotIn("pip install", self.call_log.read_text())

    def test_ensurepip_bootstraps_pip(self):
        self.env["BOOTSTRAP"] = "1"
        result = self.ensure(str(self.python_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("-m ensurepip --upgrade", self.call_log.read_text())
        self.assertIn("-m pip install -q virtualenv", self.call_log.read_text())

    def test_package_fallback(self):
        for manager, packages in (("yum", "python3.11-pip"),
                                  ("apt-get", "python3-pip python3.11-venv")):
            with self.subTest(manager=manager):
                self.write_package_manager(manager)
                result = self.ensure(str(self.python_path))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertIn(f"install -y -q {packages}\n", self.call_log.read_text())
                self.assertIn("Package manager output", result.stderr)
                for name in (manager, "pip", "virtualenv", "calls"):
                    (self.root / name).unlink()

    def test_missing_virtualenv_with_existing_pip(self):
        (self.root / "pip").touch()
        result = self.ensure(str(self.python_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("-m ensurepip", self.call_log.read_text())
        self.assertIn("-m pip install -q virtualenv", self.call_log.read_text())

    def test_virtualenv_install_failure_and_failed_repair(self):
        (self.root / "pip").touch()
        for variable in ("VIRTUALENV_EXIT", "SKIP_VIRTUALENV"):
            with self.subTest(variable=variable):
                self.env[variable] = "1"
                result = self.ensure(str(self.python_path))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("virtualenv", result.stderr)
                self.env[variable] = "0"

    def test_package_failure_and_failed_repair(self):
        self.write_package_manager("apt-get")
        for variable in ("PACKAGE_EXIT", "UPDATE_EXIT", "SKIP_INSTALL"):
            with self.subTest(variable=variable):
                self.env[variable] = "1"
                result = self.ensure(str(self.python_path))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                if variable == "UPDATE_EXIT":
                    self.assertNotIn("install -y", self.call_log.read_text())
                if variable == "SKIP_INSTALL":
                    self.assertIn("still unavailable", result.stderr)
                self.env[variable] = "0"
                self.call_log.unlink()

    def test_no_package_manager(self):
        result = self.ensure(str(self.python_path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no supported package manager", result.stderr)

    def test_missing_or_invalid_interpreter(self):
        for args in ((), (str(self.root / "missing"),), ("/bin/false",)):
            with self.subTest(args=args):
                result = self.ensure(*args)
                self.assertEqual(result.returncode, 1)
                self.assertIn("working Python 3 executable", result.stderr)