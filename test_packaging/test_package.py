import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from argparse import Namespace
from unittest.mock import patch

import package
import util


class CycleCloudApiTests(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chdir(self.temp_dir.name)
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(os.chdir, self.original_cwd)
        Path("blobs").mkdir()
        Path("libs").mkdir()

    def download_archive(self, command):
        self.assertEqual(command[-1],
                         "https://github.com/Azure/cyclecloud-scalelib/releases/download/"
                         "1.2.3/cyclecloud-scalelib-pkg-1.2.3.tar.gz")
        with tarfile.open(command[command.index("-o") + 1], "w:gz") as archive:
            for name in self.members:
                member = tarfile.TarInfo("cyclecloud-scalelib/packages/" + name)
                member.size = len(b"wheel contents")
                archive.addfile(member, io.BytesIO(b"wheel contents"))

    def test_uses_api_wheel_from_selected_scalelib_release(self):
        wheel = "cyclecloud_api-9.2.1-py2.py3-none-any.whl"
        self.members = ["cyclecloud-scalelib-1.2.3.tar.gz", wheel]
        Path("local-scalelib.tar.gz").touch()
        with patch.object(package, "SCALELIB_VERSION", "1.2.3"), \
                patch.object(package, "build_sdist", return_value="pbspro.tar.gz"), \
                patch.object(package, "check_call", side_effect=self.download_archive):
            packages = package.get_cycle_packages(
                Namespace(scalelib="local-scalelib.tar.gz", cyclecloud_api=None)
            )
        self.assertEqual(packages, ["pbspro.tar.gz", "local-scalelib.tar.gz", wheel])
        self.assertEqual(Path("blobs", wheel).read_bytes(), b"wheel contents")

    def test_duplicate_archive_entries_for_same_wheel_are_allowed(self):
        wheel = "cyclecloud_api-9.2.1-py2.py3-none-any.whl"
        self.members = [wheel, wheel]
        with patch.object(package, "SCALELIB_VERSION", "1.2.3"), \
                patch.object(package, "check_call", side_effect=self.download_archive):
            self.assertEqual(package.get_cyclecloud_api(None), wheel)
        self.assertEqual(Path("blobs", wheel).read_bytes(), b"wheel contents")

    def test_local_override_does_not_download(self):
        wheel = "cyclecloud_api-9.2.2-py2.py3-none-any.whl"
        Path(wheel).write_bytes(b"local wheel")
        with patch.object(package, "check_call") as download:
            self.assertEqual(package.get_cyclecloud_api(wheel), wheel)
            self.assertEqual(package.get_cyclecloud_api(str(Path("blobs", wheel))), wheel)
        download.assert_not_called()
        self.assertEqual(Path("blobs", wheel).read_bytes(), b"local wheel")

    def test_missing_or_ambiguous_api_wheel_fails(self):
        for members in ([], ["cyclecloud_api-1.whl", "cyclecloud_api-2.whl"]):
            with self.subTest(members=members):
                self.members = members
                with patch.object(package, "SCALELIB_VERSION", "1.2.3"), \
                        patch.object(package, "check_call", side_effect=self.download_archive):
                    with self.assertRaisesRegex(RuntimeError, "Expected one CycleCloud API wheel"):
                        package.get_cyclecloud_api(None)
        self.assertEqual(list(Path("blobs").iterdir()), [])

    def test_legacy_release_downloads_do_not_include_api_wheel(self):
        os.chdir(Path(package.__file__).parent)
        with patch.object(util, "run") as download:
            util.download_release_files()
        self.assertTrue(download.called)
        for call in download.call_args_list:
            self.assertFalse(call.args[0][-1].endswith(".whl"))


if __name__ == "__main__":
    unittest.main()