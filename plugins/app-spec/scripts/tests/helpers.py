"""Shared test setup: puts the scripts folder on sys.path and names the fixture apps."""

import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

FIX = Path(__file__).resolve().parent / "fixtures"
