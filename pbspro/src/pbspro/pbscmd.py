import json
import os
from json.decoder import JSONDecodeError
from shutil import which
from subprocess import PIPE, CalledProcessError, check_output
from typing import Dict, List

from hpc.autoscale import hpclogging as logging

from pbspro.parser import PBSProParser

QSTAT_BIN = which("qstat") or ""
QMGR_BIN = which("qmgr") or ""
PBSNODES_BIN = which("pbsnodes") or ""


class PBSCMD:
    def __init__(self, parser: PBSProParser) -> None:
        super().__init__()
        self.parser = parser
        if not QSTAT_BIN or not QMGR_BIN or not PBSNODES_BIN:
            raise RuntimeError(f"Could not find qstat, qmgr and pbsnodes in the PATH. Current path is {os.environ['PATH']}")

    def qstat(self, *args: str) -> str:
        cmd = [QSTAT_BIN] + list(args)
        return self._check_output(cmd)

    def qstat_json(self, *args: str) -> Dict:
        if "-F" not in args:
            args = ("-F", "json") + args

        response = self.qstat(*args)
        # For some reason both json and regular format are printed...
        expr = response
        # fix invalid json output like the following
        # "pset":"group_id=""",
        expr = expr.replace('"""', '"')
        attempts = 1000
        while "{" in expr and attempts > 0:
            attempts -= 1
            expr = expr[expr.index("{") :]
            try:
                return json.loads(expr)
            except JSONDecodeError as e:
                logging.error(e)
        raise RuntimeError("Could not parse qstat json output: '{}'".format(response))

    def qmgr(self, *args: str) -> str:
        cmd = [QMGR_BIN, "-c"] + [" ".join([str(x) for x in args])]
        return self._check_output(cmd)

    def qmgr_parsed(self, *args: str) -> List[Dict[str, str]]:
        raw_output = self.qmgr(*args)
        return self.parser.parse_key_value(raw_output)

    def pbsnodes(self, *args: str) -> str:
        cmd = [PBSNODES_BIN] + list(args)
        try:
            return self._check_output(cmd)
        except CalledProcessError as e:
            stderr = e.stderr.decode()
            if "Server has no node list" in stderr:
                return ""
            raise

    def pbsnodes_parsed(self, *args: str) -> List[Dict[str, str]]:
        raw_output = self.pbsnodes(*args)
        return self.parser.parse_key_value(raw_output)

    def _check_output(self, cmd: List[str]) -> str:
        logger = logging.getLogger("pbspro.driver")

        logger.info("Running: %s", " ".join(cmd))

        try:
            ret = check_output(cmd, stderr=PIPE).decode()
            logger.info("Response: %s", ret)
            return ret
        except CalledProcessError as e:
            logger.debug(str(e))
            raise
