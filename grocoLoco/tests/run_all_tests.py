"""
Helper script so PyCharm can run the entire test suite
with a single click.

You can right-click this file in PyCharm → "Run run_all_tests".
"""

import pytest
import sys
from pathlib import Path

# Ensure project root is added to PYTHONPATH
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    # -q = quiet, remove if you want full verbose output
    pytest.main(["-q"])
