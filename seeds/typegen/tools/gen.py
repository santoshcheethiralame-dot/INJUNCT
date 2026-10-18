"""The client types are generated. Nobody writes them by hand."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PY = {"int": "int", "str": "str", "bool": "bool", "float": "float"}


def render() -> str:
    spec = json.loads((HERE / "api" / "types.json").read_text(encoding="utf-8"))
    out = ["# GENERATED FILE - run tools/gen.py, do not edit by hand", ""]
    for name, fields in spec.items():
        out.append(f"class {name}:")
        out.append("    __slots__ = (" + ", ".join(f'"{f}"' for f in fields) + ",)")
        for f, t in fields.items():
            out.append(f"    {f}: {PY[t]}")
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    (HERE / "client" / "generated.py").write_text(render(), encoding="utf-8")
    print("generated")
