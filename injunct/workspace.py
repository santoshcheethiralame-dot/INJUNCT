"""Restore a working tree in place.

Never delete the directory: on Windows a running server holds it open, and the
ledger lives beside it.
"""
from __future__ import annotations

import shutil
from pathlib import Path

SKIP = {"__pycache__", ".injunct", ".git"}


def files(root: Path) -> set[str]:
    return {str(p.relative_to(root)).replace("\\", "/") for p in Path(root).rglob("*")
            if p.is_file() and not SKIP & set(p.parts)}


def restore(seed: Path, dst: Path) -> None:
    """Bring dst back to the seed state.

    Purge __pycache__ first. copy2 preserves the seed's mtime, so a .pyc built
    from a since-modified source can look newer than the file we just restored
    and Python will import the stale module - which silently reverts the very
    change a run is being judged on.
    """
    seed, dst = Path(seed), Path(dst)
    s_abs, d_abs = seed.resolve(), dst.resolve()
    if s_abs == d_abs or s_abs in d_abs.parents:
        # A seed is a fixture. Restoring onto it - or into it - lets a run write
        # its own results back into the thing every later run is measured
        # against, and every result after that is quietly wrong.
        raise ValueError(f"refusing to restore onto the seed itself: {d_abs}")
    dst.mkdir(parents=True, exist_ok=True)
    for cache in list(dst.rglob("__pycache__")):
        shutil.rmtree(cache, ignore_errors=True)
    want = files(seed)
    for rel in files(dst) - want:
        (dst / rel).unlink(missing_ok=True)
    for rel in want:
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(seed / rel, target)
