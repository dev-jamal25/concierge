"""Ensures the backend/ directory is on sys.path so `import app.*` resolves
when running pytest from the repo without an editable install.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
