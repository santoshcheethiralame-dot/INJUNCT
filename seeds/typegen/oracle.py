"""The client must be exactly what the generator would produce. No drift, ever."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import gen  # noqa: E402

current = (Path(__file__).resolve().parent / "client" / "generated.py").read_text(encoding="utf-8")
wanted = gen.render()
if current.strip() != wanted.strip():
    print("FAIL: client/generated.py has drifted from api/types.json")
    sys.exit(1)
print("PASS: client types match the API spec")
