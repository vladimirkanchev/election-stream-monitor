"""Repository-level pytest bootstrap for src-based imports.

Keep `src/` on `sys.path` for the full test run so collection works
consistently in local shells and CI runners.
"""

from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
