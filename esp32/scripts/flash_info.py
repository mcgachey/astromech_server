"""PlatformIO post-build script: record how PlatformIO itself would flash this env.

Writes <build dir>/flash_info.json with the chip, flash parameters and the
(offset, file) pairs for the extra images and the app. scripts/package.py uses
it so the flash offsets are never hardcoded.
"""
import json
from pathlib import Path

Import("env")  # noqa: F821  (provided by PlatformIO/SCons)


def write_info(source, target, env):  # noqa: ARG001
    build_dir = Path(env.subst("$BUILD_DIR"))
    board = env.BoardConfig()
    images = [
        {"offset": str(off), "path": str(Path(env.subst(path)))}
        for off, path in env.get("FLASH_EXTRA_IMAGES", [])
    ]
    images.append(
        {
            "offset": env.subst("$ESP32_APP_OFFSET"),
            "path": str(build_dir / "firmware.bin"),
        }
    )
    info = {
        "role": env.subst("$PIOENV"),
        "version": env.subst("$FW_VERSION"),
        "build_id": env.subst("$FW_BUILD_ID"),
        "chip": board.get("build.mcu", "esp32"),
        "flash_mode": env.subst("${__get_board_flash_mode(__env__)}"),
        "flash_freq": env.subst("${__get_board_f_image(__env__)}"),
        "flash_size": board.get("upload.flash_size", "4MB"),
        "images": images,
    }
    (build_dir / "flash_info.json").write_text(json.dumps(info, indent=2) + "\n")


env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", write_info)  # noqa: F821
