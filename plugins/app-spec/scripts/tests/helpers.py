"""Shared test setup: puts the scripts folder on sys.path and names the fixture apps."""

import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

FIX = Path(__file__).resolve().parent / "fixtures"


def run_cli(argv, module=None):
    """Run a script's `main` the way the command line does. `argv[0]` is the script name.

    Returns the exit code. stdout and stderr are captured and returned as the second and third value."""
    import contextlib
    import importlib
    import io

    mod = module or importlib.import_module(os.path.splitext(os.path.basename(argv[0]))[0])
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            result = mod.main(argv[1:])
            code = result or 0
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    return code, out.getvalue(), err.getvalue()
