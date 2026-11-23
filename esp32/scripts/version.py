"""PlatformIO pre-build script: inject the per-env firmware version.

Reads version/<env>.txt (semver) and the git state, and defines
FIRMWARE_VERSION and FIRMWARE_BUILD_ID for the firmware (see Version.h).
"""
import re
import subprocess
from pathlib import Path

Import("env")  # noqa: F821  (provided by PlatformIO/SCons)

project = Path(env["PROJECT_DIR"])  # noqa: F821
name = env["PIOENV"]  # noqa: F821
version_file = project / "version" / f"{name}.txt"
version = version_file.read_text().strip()
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise SystemExit(f"{version_file}: '{version}' is not MAJOR.MINOR.PATCH")


def git(*args):
    try:
        return subprocess.check_output(
            ["git", *args], cwd=project, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


build_id = git("rev-parse", "--short", "HEAD") or "nogit"
if git("status", "--porcelain", "--", ".") not in (None, ""):
    build_id += "-dirty"

# Shared with scripts/flash_info.py so packaging records what was compiled.
env.Replace(FW_VERSION=version, FW_BUILD_ID=build_id)  # noqa: F821
env.Append(  # noqa: F821
    CPPDEFINES=[
        ("FIRMWARE_VERSION", env.StringifyMacro(version)),  # noqa: F821
        ("FIRMWARE_BUILD_ID", env.StringifyMacro(build_id)),  # noqa: F821
    ]
)
