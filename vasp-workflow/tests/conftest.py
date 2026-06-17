import sys
from pathlib import Path

# Make the skill's `scripts/` importable as `import vwf...`, mirroring how the
# skill is run (`PYTHONPATH=$SKILL/scripts python -m vwf ...`).
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
