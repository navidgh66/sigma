import sys
from pathlib import Path

# Ensure the repo root is importable so `import cli...` works under pytest.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
