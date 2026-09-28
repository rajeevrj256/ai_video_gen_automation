"""File moves that survive Windows and OneDrive.

On Windows a rename fails with "Access is denied" (WinError 5) while any file inside is
open: OneDrive syncing the new video, an antivirus scan, or the app's own thumbnail read.
The lock is usually gone within seconds, so retry; if it never clears, copy instead of
move, so a finished video is never lost at the last step.
"""

from __future__ import annotations

import logging
import re
import shutil
import time
from pathlib import Path

log = logging.getLogger(__name__)


def move(src: Path, dst: Path, tries: int = 12, wait: float = 1.0) -> Path:
    """Rename src to dst (a file or a folder), retrying on locks, copying as a last resort."""
    for i in range(tries):
        try:
            src.rename(dst)
            return dst
        except PermissionError as exc:
            if i == tries - 1:
                log.warning("Couldn't rename %s (%s); copying instead", src.name, exc)
            else:
                time.sleep(wait * min(4, 1 + i // 3))  # 1s, then 2s, 3s, 4s...
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
        shutil.rmtree(src, ignore_errors=True)  # whatever is still locked stays behind, harmlessly
    else:
        shutil.copy2(src, dst)
        try:
            src.unlink()
        except OSError:
            pass
    return dst


def rebase(obj, folder: Path):
    """Point absolute paths saved in a checkpoint at `folder` again. A project moved to
    another place (out of OneDrive, say) keeps the old paths in its checkpoints; every file
    lives inside the video's own folder, so the part after that folder's name still holds."""
    if isinstance(obj, dict):
        return {k: rebase(v, folder) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rebase(v, folder) for v in obj]
    if isinstance(obj, str) and (obj[1:3] in (":\\", ":/") or obj.startswith("/")):
        parts = re.split(r"[\\/]", obj)
        if folder.name in parts:
            i = len(parts) - 1 - parts[::-1].index(folder.name)
            return str(folder.joinpath(*parts[i + 1:]))
    return obj
