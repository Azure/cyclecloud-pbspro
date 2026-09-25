import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LocalReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo with spaces"
        self.repo.mkdir()
        self.script = self.repo / "docker-package.sh"
        shutil.copyfile(ROOT / "docker-package.sh", self.script)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.env = dict(os.environ, PATH=f"{self.bin_dir}:/usr/bin:/bin",
                        CALL_LOG=str(self.root / "calls.json"))
        self.write_tool("docker", "#!/bin/sh\nexit ${DOCKER_EXIT:-0}\n")
        self.write_tool("act", """#!/usr/bin/python3
import json
import os
from pathlib import Path
import sys
import zipfile

args = sys.argv[1:]
Path(os.environ['CALL_LOG']).write_text(json.dumps({'args': args, 'cwd': os.getcwd()}))
if os.environ.get('ACT_EXIT'):
    sys.exit(int(os.environ['ACT_EXIT']))
if os.environ.get('NO_ARTIFACT'):
    sys.exit(0)
target = Path(args[args.index('--artifact-server-path') + 1]) / '1/release-artifacts'
target.mkdir(parents=True)
with zipfile.ZipFile(target / 'release-artifacts.zip', 'w') as archive:
    archive.writestr('package.tar.gz', 'new package')
    archive.writestr('api.whl', 'new wheel')
""")
        (self.repo / "blobs").mkdir()
        (self.repo / "blobs/package.tar.gz").write_text("old package")
        (self.repo / "blobs/unrelated.txt").write_text("keep")

    def write_tool(self, name, content):
        path = self.bin_dir / name
        path.write_text(content)
        path.chmod(0o755)

    def run_wrapper(self, *args):
        return subprocess.run(["bash", str(self.script), *args], cwd=self.root,
                              env=self.env, text=True, capture_output=True)

    def test_build_only_from_repo_root_and_export_as_current_user(self):
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        call = json.loads(Path(self.env["CALL_LOG"]).read_text())
        self.assertEqual(call["cwd"], str(self.repo))
        args = call["args"]
        self.assertEqual(args[0], "workflow_dispatch")
        for option, expected in (
            ("--job", "build"),
            ("--workflows", ".github/workflows/release.yml"),
            ("--env", "ACT=true"),
            ("--secret-file", "/dev/null"),
            ("--env-file", "/dev/null"),
            ("--var-file", "/dev/null"),
            ("--input-file", "/dev/null"),
            ("--container-architecture", "linux/amd64"),
        ):
            self.assertEqual(args[args.index(option) + 1], expected)
        self.assertIn("--bind=false", args)
        self.assertIn("--use-gitignore=true", args)
        self.assertIn("--container-daemon-socket=-", args)
        self.assertFalse(Path(args[args.index("--artifact-server-path") + 1]).exists())
        self.assertEqual((self.repo / "blobs/package.tar.gz").read_text(), "new package")
        self.assertEqual((self.repo / "blobs/api.whl").stat().st_uid, os.getuid())
        self.assertEqual((self.repo / "blobs/unrelated.txt").read_text(), "keep")
        self.assertEqual(self.run_wrapper().returncode, 0)

    def test_failed_build_preserves_outputs_and_exit_code(self):
        self.env["ACT_EXIT"] = "42"
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 42)
        self.assertEqual((self.repo / "blobs/package.tar.gz").read_text(), "old package")
        args = json.loads(Path(self.env["CALL_LOG"]).read_text())["args"]
        self.assertFalse(Path(args[args.index("--artifact-server-path") + 1]).exists())

    def test_missing_artifact_fails_without_replacing_outputs(self):
        self.env["NO_ARTIFACT"] = "1"
        result = self.run_wrapper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected one release-artifacts.zip", result.stderr)
        self.assertEqual((self.repo / "blobs/package.tar.gz").read_text(), "old package")

    def test_docker_failure_prevents_act(self):
        self.env["DOCKER_EXIT"] = "1"
        self.assertNotEqual(self.run_wrapper().returncode, 0)
        self.assertFalse(Path(self.env["CALL_LOG"]).exists())

    def test_missing_act_has_actionable_error(self):
        (self.bin_dir / "act").unlink()
        result = self.run_wrapper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("act is required", result.stderr)

    def test_help_and_unsupported_arguments_do_not_run_act(self):
        self.assertEqual(self.run_wrapper("--help").returncode, 0)
        self.assertEqual(self.run_wrapper("../cyclecloud-scalelib").returncode, 2)
        self.assertFalse(Path(self.env["CALL_LOG"]).exists())


@unittest.skipUnless(os.environ.get("PBSPRO_TEST_ACT") == "1",
                     "Set PBSPRO_TEST_ACT=1 to run two real Docker workflow builds")
class LocalReleaseIntegrationTests(unittest.TestCase):
    def test_dirty_working_tree_ignored_outputs_and_repeat_build(self):
        with tempfile.TemporaryDirectory(prefix="pbspro-act-test-") as directory:
            repo = Path(directory) / "checkout"
            subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(repo)],
                           check=True)
            subprocess.run(["git", "remote", "set-url", "origin",
                            "https://github.com/Azure/cyclecloud-pbspro"], cwd=repo, check=True)
            files = subprocess.check_output(
                ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                cwd=ROOT, text=True).split("\0")
            for name in filter(None, files):
                source = ROOT / name
                if source.is_file():
                    target = repo / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
            install_script = repo / "install.sh"
            install_script.write_bytes(install_script.read_bytes() + b"\ntrue\n")
            for name in ("pbspro/dist/stale.tar.gz", "blobs/cyclecloud_api-stale.whl",
                         "venv/created", "libs/stale.tar.gz"):
                target = repo / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"ignored stale input")
            for attempt in range(2):
                result = subprocess.run([str(repo / "docker-package.sh")], cwd=directory,
                                        text=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
                self.assertEqual(result.returncode, 0, result.stdout[-12000:])
                self.assertNotIn("Run Main Create Release", result.stdout)
                packages = list((repo / "blobs").glob("cyclecloud-pbspro-pkg-*.tar.gz"))
                self.assertEqual(len(packages), 1)
                self.assertEqual(packages[0].stat().st_uid, os.getuid())
                with tarfile.open(packages[0]) as archive:
                    actual = archive.extractfile("cyclecloud-pbspro/install.sh").read()
                    self.assertEqual(actual, install_script.read_bytes())
                    self.assertFalse(any("stale" in name for name in archive.getnames()))
                self.assertEqual((repo / "blobs/cyclecloud_api-stale.whl").read_bytes(),
                                 b"ignored stale input")
                print(f"Real workflow build {attempt + 1}: dirty source included; stale inputs excluded",
                      flush=True)


if __name__ == "__main__":
    unittest.main()