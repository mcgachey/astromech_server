#!/usr/bin/env python3
"""Package built firmware into dist/<role>/<version>/ for the controller.

Reads .pio/build/<env>/flash_info.json (written by scripts/flash_info.py) and
copies the images next to a manifest.json that the controller validates
(role, version, flash parameters, file offsets and sha256).

    package.py [--dist DIR] [--force] [env ...]      (default: droid beacon)
"""
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_VERSION = 1


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def package(env: str, dist: Path, force: bool) -> Path:
    info_path = ROOT / ".pio" / "build" / env / "flash_info.json"
    if not info_path.exists():
        raise SystemExit(f"{info_path} missing: run `pio run -e {env}` first")
    info = json.loads(info_path.read_text())
    if info["role"] != env:
        raise SystemExit(f"{info_path}: role {info['role']!r} != env {env!r}")

    files = []
    for image in info["images"]:
        src = Path(image["path"])
        if not src.exists():
            raise SystemExit(f"missing image {src}")
        files.append({"name": src.name, "offset": image["offset"], "src": src})

    out = dist / info["role"] / info["version"]
    app_sha = sha256(next(f["src"] for f in files if f["name"] == "firmware.bin"))
    existing = out / "manifest.json"
    if existing.exists() and not force:
        old = json.loads(existing.read_text())
        old_app = next((f["sha256"] for f in old["files"] if f["name"] == "firmware.bin"), None)
        if old_app != app_sha:
            raise SystemExit(
                f"{info['role']} {info['version']} already packaged with a different "
                f"firmware.bin; bump version/{env}.txt (or pass --force)"
            )

    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for f in files:
        shutil.copyfile(f["src"], out / f["name"])
        entries.append(
            {
                "name": f["name"],
                "offset": f["offset"],
                "size": f["src"].stat().st_size,
                "sha256": sha256(f["src"]),
            }
        )
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "role": info["role"],
        "version": info["version"],
        "build_id": info["build_id"],
        "chip": info["chip"],
        "flash_mode": info["flash_mode"],
        "flash_freq": info["flash_freq"],
        "flash_size": info["flash_size"],
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": entries,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("envs", nargs="*", default=["droid", "beacon"])
    ap.add_argument("--dist", type=Path, default=ROOT / "dist")
    ap.add_argument("--force", action="store_true", help="overwrite an existing version")
    args = ap.parse_args()
    for env in args.envs:
        out = package(env, args.dist, args.force)
        print(f"packaged {out.relative_to(args.dist.parent) if out.is_relative_to(args.dist.parent) else out}")


if __name__ == "__main__":
    sys.exit(main())
