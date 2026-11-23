#!/usr/bin/env python3
"""Bump the PATCH version of a firmware env when its sources changed.

For each env, fingerprint the files that go into that firmware and compare with
version/.<env>.stamp ("<version> <hash>", written by the last run):

  no stamp, version not in dist/ adopt the current state, no bump
  no stamp, version in dist/     bump PATCH (can't tell if it changed; a spare
                                 number is cheaper than a failed package step)
  hash unchanged                 nothing to do
  hash changed, txt == stamp     bump PATCH in version/<env>.txt
  hash changed, txt != stamp     version was edited by hand: keep it

    bump_version.py [--root DIR] [--lib DIR] [env ...]      (default: droid beacon)

Run by `make build` (BUMP=0 skips it). MAJOR/MINOR stay manual.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")
SKIP_DIRS = {"__pycache__", ".pio", ".git"}


def files_under(base: Path):
    if base.is_file():
        yield base
    elif base.is_dir():
        for p in sorted(base.rglob("*")):
            if p.is_file() and not SKIP_DIRS & set(p.relative_to(base).parts):
                yield p


def fingerprint(root: Path, lib: Path, env: str) -> str:
    inputs = [
        ("fw", root, root / "src" / "common"),
        ("fw", root, root / "src" / env),
        ("fw", root, root / "platformio.ini"),
        ("fw", root, root / "scripts" / "version.py"),
        ("lib", lib, lib / "src"),
        ("lib", lib, lib / "library.json"),
    ]
    h = hashlib.sha256()
    for label, anchor, base in inputs:
        for p in files_under(base):
            # Relative paths, so moving the checkout doesn't change the hash.
            h.update(f"{label}/{p.relative_to(anchor)}\0".encode())
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def bump(root: Path, lib: Path, env: str) -> None:
    vfile = root / "version" / f"{env}.txt"
    stamp = root / "version" / f".{env}.stamp"
    version = vfile.read_text().strip()
    m = SEMVER.fullmatch(version)
    if not m:
        raise SystemExit(f"{vfile}: '{version}' is not MAJOR.MINOR.PATCH")
    digest = fingerprint(root, lib, env)

    old = stamp.read_text().split() if stamp.exists() else None
    if not old or len(old) != 2:
        if not (root / "dist" / env / version).exists():
            stamp.write_text(f"{version} {digest}\n")
            print(f"{env} {version} (version stamp created)")
            return
        old_version, old_digest = version, None  # already released: assume changed
    else:
        old_version, old_digest = old
    if old_digest == digest:
        return
    if old_version != version:
        stamp.write_text(f"{version} {digest}\n")
        print(f"{env} {version} (edited by hand, not bumped)")
        return
    major, minor, patch = map(int, m.groups())
    new = f"{major}.{minor}.{patch + 1}"
    vfile.write_text(new + "\n")
    stamp.write_text(f"{new} {digest}\n")
    print(f"{env} {version} -> {new} (sources changed)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("envs", nargs="*", default=["droid", "beacon"])
    ap.add_argument("--root", type=Path, default=ROOT, help="esp32 project dir")
    ap.add_argument(
        "--lib", type=Path, default=None, help="libastromech/esp32 dir (default ../../libastromech/esp32)"
    )
    args = ap.parse_args()
    root = args.root.resolve()
    lib = (args.lib or root / ".." / ".." / "libastromech" / "esp32").resolve()
    for env in args.envs:
        bump(root, lib, env)


if __name__ == "__main__":
    sys.exit(main())
