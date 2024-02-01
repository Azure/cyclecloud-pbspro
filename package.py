import argparse
import configparser
import glob
import os
import shutil
import sys
import tarfile
import tempfile
from argparse import Namespace
from subprocess import check_call
from typing import Dict, List, Optional

SCALELIB_VERSION = "1.0.2"
CYCLECLOUD_API_VERSION = "8.3.1"


def build_sdist() -> str:
    cmd = [sys.executable, "setup.py", "sdist"]
    check_call(cmd, cwd=os.path.abspath("pbspro"))
    sdists = glob.glob("pbspro/dist/cyclecloud-pbspro-*.tar.gz")
    assert len(sdists) == 1, "Found %d sdist packages, expected 1" % len(sdists)
    path = sdists[0]
    fname = os.path.basename(path)
    dest = os.path.join("libs", fname)
    if os.path.exists(dest):
        os.remove(dest)
    shutil.move(path, dest)
    return fname


def get_cycle_libs(args: Namespace) -> List[str]:
    ret = [build_sdist()]

    scalelib_file = "cyclecloud-scalelib-{}.tar.gz".format(SCALELIB_VERSION)
    cyclecloud_api_file = f"cyclecloud_api-{CYCLECLOUD_API_VERSION}-py2.py3-none-any.whl"

    scalelib_url = f"https://github.com/Azure/cyclecloud-scalelib/archive/refs/tags/{SCALELIB_VERSION}.tar.gz"

    cyclecloud_api_url = f"https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins/{cyclecloud_api_file}"
    to_download = {
        scalelib_file: (args.scalelib, scalelib_url),
        cyclecloud_api_file: (args.cyclecloud_api, cyclecloud_api_url),
    }

    for lib_file in to_download:
        arg_override, url = to_download[lib_file]
        if arg_override:
            if not os.path.exists(arg_override):
                print(arg_override, "does not exist", file=sys.stderr)
                sys.exit(1)
            fname = os.path.basename(arg_override)
            orig = os.path.abspath(arg_override)
            dest = os.path.abspath(os.path.join("libs", fname))
            if orig != dest:
                shutil.copyfile(orig, dest)
            ret.append(fname)
        else:
            dest = os.path.join("libs", lib_file)
            check_call(["curl", "-L", "-k", "-s", "-f", "-o", dest, url])
            ret.append(lib_file)
            print("Downloaded", lib_file, "to")

    return ret


def execute() -> None:
    expected_cwd = os.path.abspath(os.path.dirname(__file__))
    os.chdir(expected_cwd)

    if not os.path.exists("libs"):
        os.makedirs("libs")

    argument_parser = argparse.ArgumentParser(
        "Builds CycleCloud GridEngine project with all dependencies.\n"
        + "If you don't specify local copies of scalelib or cyclecloud-api they will be downloaded from github."
    )
    argument_parser.add_argument("--scalelib", default=None)
    argument_parser.add_argument("--cyclecloud-api", default=None)
    args = argument_parser.parse_args()

    cycle_libs = get_cycle_libs(args)

    parser = configparser.ConfigParser()
    ini_path = os.path.abspath("project.ini")

    with open(ini_path) as fr:
        parser.read_file(fr)

    version = parser.get("project", "version")
    if not version:
        raise RuntimeError("Missing [project] -> version in {}".format(ini_path))

    if not os.path.exists("dist"):
        os.makedirs("dist")

    tf = tarfile.TarFile.gzopen(
        "dist/cyclecloud-pbspro-pkg-{}.tar.gz".format(version), "w"
    )

    build_dir = tempfile.mkdtemp("cyclecloud-pbspro")

    def _add(name: str, path: Optional[str] = None, mode: Optional[int] = None) -> None:
        path = path or name
        tarinfo = tarfile.TarInfo("cyclecloud-pbspro/" + name)
        tarinfo.size = os.path.getsize(path)
        tarinfo.mtime = int(os.path.getmtime(path))
        if mode:
            tarinfo.mode = mode

        with open(path, "rb") as fr:
            tf.addfile(tarinfo, fr)

    packages = []
    for dep in cycle_libs:
        dep_path = os.path.abspath(os.path.join("libs", dep))
        _add("packages/" + dep, dep_path)
        packages.append(dep_path)

    check_call(["pip", "download"] + packages, cwd=build_dir)

    print("Using build dir", build_dir)
    by_package: Dict[str, List[str]] = {}
    for fil in os.listdir(build_dir):
        toks = fil.split("-", 1)
        package = toks[0]
        if "pyyaml" in fil.lower():
            print("Ignoring pyyaml as it is not needed and is platform specific")
            os.remove(os.path.join(build_dir, fil))
            continue
        if "itsdangerous" in fil.lower():
            print("Ignoring itsdangerous as it is not needed and is platform specific")
            os.remove(os.path.join(build_dir, fil))
            continue
        if package == "cyclecloud":
            package = "{}-{}".format(toks[0], toks[1])
        if package not in by_package:
            by_package[package] = []
        by_package[package].append(fil)

    for package, fils in by_package.items():
        
        if len(fils) > 1:
            print("WARNING: Ignoring duplicate package found:", package, fils)
            assert False

    for fil in os.listdir(build_dir):
        path = os.path.join(build_dir, fil)
        _add("packages/" + fil, path)

    _add("install.sh", mode=os.stat("install.sh")[0])
    _add("initialize_pbs.sh", mode=os.stat("initialize_pbs.sh")[0])
    _add("initialize_default_queues.sh", mode=os.stat("initialize_default_queues.sh")[0])
    _add("generate_autoscale_json.sh", mode=os.stat("generate_autoscale_json.sh")[0])
    _add("server_dyn_res_wrapper.sh", mode=os.stat("server_dyn_res_wrapper.sh")[0])
    _add("autoscale_hook.py", "pbspro/conf/autoscale_hook.py")
    _add("logging.conf", "pbspro/conf/logging.conf")


if __name__ == "__main__":
    execute()
