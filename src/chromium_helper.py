"""
Playwright Chromium helper — check and install the browser used for X post screenshots.

`python -m playwright install` is not available inside the packaged exe, so the
installer is run through Playwright's bundled node driver instead.
"""

import logging
import os
import re
import subprocess
import sys
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

STATUS_INSTALLED = "Installed"
STATUS_NOT_INSTALLED = "Not installed"
STATUS_NO_PLAYWRIGHT = "Playwright library missing"


def ensure_browsers_path() -> None:
    """Use the shared per-user browser folder (LOCALAPPDATA/ms-playwright) on Windows.

    Inside the packaged exe Playwright otherwise looks in its own bundled
    .local-browsers folder, which never contains a browser.
    """
    if sys.platform == 'win32' and os.environ.get('PLAYWRIGHT_BROWSERS_PATH') in (None, '', '0'):
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~/AppData/Local')
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = os.path.join(base, 'ms-playwright')


ensure_browsers_path()


def check_chromium() -> Tuple[bool, str]:
    """Return (usable, status). Launches headless Chromium, as screenshots do. Blocking."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, STATUS_NO_PLAYWRIGHT

    try:
        with sync_playwright() as pw:
            pw.chromium.launch(headless=True).close()
        return True, STATUS_INSTALLED
    except Exception as e:
        logger.info(f"Chromium check failed: {e}")
        return False, STATUS_NOT_INSTALLED


def install_chromium(on_output: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
    """Download Chromium via Playwright's driver. Blocking; takes a few minutes.

    on_output receives each line the installer prints. Returns (ok, message).
    """
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env
    except ImportError:
        return False, STATUS_NO_PLAYWRIGHT

    node, cli = compute_driver_executable()
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    tail = []
    try:
        proc = subprocess.Popen(
            [node, cli, 'install', 'chromium'],
            env=get_driver_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', creationflags=creationflags,
        )
        for line in proc.stdout:
            line = _ANSI_RE.sub('', line).strip()
            if not line:
                continue
            tail = (tail + [line])[-5:]
            logger.info(f"[chromium install] {line}")
            if on_output:
                on_output(line)
        code = proc.wait()
    except Exception as e:
        return False, f"Install failed: {e}"

    if code != 0:
        return False, f"Install failed (exit {code}): {' | '.join(tail)}"
    return True, "Chromium installed"
