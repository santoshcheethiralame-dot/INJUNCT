"""Three lists that must agree: the files, the registry, and the docs table."""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

on_disk = set()
for f in sorted((HERE / "plugins").glob("*.py")):
    m = re.search(r'^NAME\s*=\s*"([^"]+)"', f.read_text(encoding="utf-8"), re.M)
    if m:
        on_disk.add(m.group(1))

import registry  # noqa: E402
declared = set(registry.REGISTRY)

doc_rows = set(re.findall(r"^\|\s*([a-z_]+)\s*\|", (HERE / "docs" / "plugins.md").read_text(encoding="utf-8"), re.M))
doc_rows.discard("name")

problems = []
if on_disk != declared:
    problems.append(f"registry.py disagrees with plugins/: {on_disk ^ declared}")
if on_disk != doc_rows:
    problems.append(f"docs/plugins.md disagrees with plugins/: {on_disk ^ doc_rows}")

if problems:
    print("FAIL: " + "; ".join(problems))
    sys.exit(1)
print(f"PASS: {len(on_disk)} plugins, registry and docs agree")
