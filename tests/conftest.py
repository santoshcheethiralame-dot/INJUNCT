import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# A laptop's own ~/.injunct/provider.json must not reach the suite: tests that
# expect no model would quietly start spending a real quota.
os.environ["INJUNCT_CONFIG"] = str(Path(__file__).parent / "no-such-provider.json")
