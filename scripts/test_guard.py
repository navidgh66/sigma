"""Test tamper guard for sigma /loop: the implementer must not edit existing tests.

Coding agents edit tests to make them pass even when told not to (ImpossibleBench,
arXiv 2510.20270), so /loop checks it structurally: snapshot test-file hashes
before the implementer runs, check after. New test files are allowed; edited or
deleted pre-existing ones fail the attempt, and `restore` puts them back from the
copies the snapshot keeps. Stdlib only; works with or without git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", "dist", "build"}
# Top-level dirs skipped only at the project root (sigma/ holds loop workspaces and
# the snapshot files themselves; a nested package named "sigma" is real code).
_SKIP_ROOT_DIRS = {"sigma"}
_TEST_FILE = re.compile(r"(^test_.*\.py$)|(_test\.py$)|(\.(test|spec)\.[A-Za-z0-9]+$)")


def is_test_path(rel: str) -> bool:
    parts = Path(rel).parts
    if any(p in ("tests", "test", "__tests__") for p in parts[:-1]):
        return True
    return bool(_TEST_FILE.search(parts[-1])) if parts else False


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root: Path, backup_dir: Optional[Path] = None) -> Dict[str, str]:
    """Hash every test file under root; with backup_dir, also keep a copy of each."""
    out: Dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        at_root = here == root
        # Prune in place so skipped trees (node_modules, .git) are never walked.
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in _SKIP_DIRS and not (at_root and d in _SKIP_ROOT_DIRS)
        )
        for name in sorted(filenames):
            path = here / name
            rel = path.relative_to(root).as_posix()
            if not is_test_path(rel) or not path.is_file():
                continue
            try:
                out[rel] = _sha(path)
                if backup_dir is not None:
                    dest = backup_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dest)
            except OSError:
                continue
    return dict(sorted(out.items()))


def check(before: Dict[str, str], root: Path) -> List[str]:
    tampered: List[str] = []
    for rel, digest in before.items():
        path = root / rel
        try:
            if not path.is_file() or _sha(path) != digest:
                tampered.append(rel)
        except OSError:
            tampered.append(rel)
    return sorted(tampered)


def restore(before: Dict[str, str], root: Path, backup_dir: Path) -> List[str]:
    """Put back every pre-existing test that changed or vanished; return their paths.

    New test files are left alone. A file with no backup copy is skipped (and
    still reported by `check`).
    """
    restored: List[str] = []
    for rel in check(before, root):
        src = backup_dir / rel
        if not src.is_file():
            continue
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        restored.append(rel)
    return restored


def _backup_dir(snapshot_file: Path) -> Path:
    return snapshot_file.with_name(snapshot_file.name + ".d")


def cli(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="test_guard")
    p.add_argument("action", choices=["snapshot", "check", "restore"])
    p.add_argument("file", help="snapshot JSON path (backups go to <file>.d/)")
    p.add_argument("--root", default=".", help="project root (default: cwd)")
    args = p.parse_args(argv)
    root = Path(args.root).resolve()
    snap_file = Path(args.file)
    backup = _backup_dir(snap_file)
    if args.action == "snapshot":
        if backup.exists():
            shutil.rmtree(backup)
        snap_file.write_text(json.dumps(snapshot(root, backup), indent=2, sort_keys=True) + "\n")
        return 0
    before = json.loads(snap_file.read_text())
    if args.action == "restore":
        for rel in restore(before, root, backup):
            print(rel)
        return 0
    tampered = check(before, root)
    for rel in tampered:
        print(rel)
    return 1 if tampered else 0


if __name__ == "__main__":
    sys.exit(cli())
