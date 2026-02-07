"""Bridge module for automating Studio 5000 / RSLogix tag search.

Copies a tag name to the clipboard and switches to the target application
window so the user can paste it where needed.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import time

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


# ---------------------------------------------------------------------------
# Clipboard via Win32 API (reliable fallback — pyperclip sometimes fails)
# ---------------------------------------------------------------------------

def _win32_copy(text: str) -> bool:
    """Copy *text* to the Windows clipboard using the Win32 API directly."""
    CF_UNICODETEXT = 13
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    if not user32.OpenClipboard(0):
        log.error("OpenClipboard failed")
        return False
    try:
        user32.EmptyClipboard()
        encoded = text.encode("utf-16-le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(0x0042, len(encoded))  # GMEM_MOVEABLE | GMEM_ZEROINIT
        if not h_mem:
            log.error("GlobalAlloc failed")
            return False
        ptr = kernel32.GlobalLock(h_mem)
        ctypes.memmove(ptr, encoded, len(encoded))
        kernel32.GlobalUnlock(h_mem)
        result = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        if not result:
            log.error("SetClipboardData failed")
            return False
        log.debug("Win32 clipboard set to: %r", text)
        return True
    finally:
        user32.CloseClipboard()


def _win32_get_clipboard() -> str:
    """Read current clipboard text via Win32 API (for verification)."""
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    if not user32.OpenClipboard(0):
        return "<could not open clipboard>"
    try:
        h_data = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_data:
            return "<empty>"
        ptr = kernel32.GlobalLock(h_data)
        if not ptr:
            return "<lock failed>"
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h_data)
    finally:
        user32.CloseClipboard()


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------

def list_windows(filter_text: str = "") -> list[str]:
    """Return titles of all visible windows, optionally filtered by substring."""
    import pygetwindow as gw

    all_windows = gw.getAllTitles()
    titles = [t for t in all_windows if t.strip()]
    if filter_text:
        filter_lower = filter_text.lower()
        titles = [t for t in titles if filter_lower in t.lower()]
    return sorted(set(titles))


def _force_foreground(hwnd: int) -> bool:
    """Aggressively bring a window to the foreground on Windows.

    Uses multiple strategies:
      1. AllowSetForegroundWindow to unlock the foreground lock.
      2. Attach our thread to both the current foreground thread AND the
         target window's thread so we inherit foreground rights.
      3. Minimize-then-restore trick as a last resort (always works).
    """
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    current_thread = kernel32.GetCurrentThreadId()
    fg_window = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg_window, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)

    log.debug("current_thread=%d fg_thread=%d target_thread=%d target_hwnd=%d",
              current_thread, fg_thread, target_thread, hwnd)

    # Unlock foreground for our process
    ASFW_ANY = ctypes.c_uint32(-1)
    user32.AllowSetForegroundWindow(ASFW_ANY)

    # Attach to foreground thread
    attached_fg = False
    if current_thread != fg_thread:
        attached_fg = bool(user32.AttachThreadInput(current_thread, fg_thread, True))
        log.debug("Attached to fg thread: %s", attached_fg)

    # Attach to target thread
    attached_target = False
    if current_thread != target_thread and fg_thread != target_thread:
        attached_target = bool(user32.AttachThreadInput(current_thread, target_thread, True))
        log.debug("Attached to target thread: %s", attached_target)

    try:
        # Restore if minimized
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.05)

        # Try SetForegroundWindow
        user32.BringWindowToTop(hwnd)
        result = user32.SetForegroundWindow(hwnd)
        log.debug("SetForegroundWindow returned %s", result)

        if not result:
            # Last resort: minimize then restore — this always grants
            # foreground rights to the restored window
            log.debug("Trying minimize-restore trick")
            SW_MINIMIZE = 6
            user32.ShowWindow(hwnd, SW_MINIMIZE)
            time.sleep(0.1)
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.1)
            user32.SetForegroundWindow(hwnd)
    finally:
        if attached_fg:
            user32.AttachThreadInput(current_thread, fg_thread, False)
        if attached_target:
            user32.AttachThreadInput(current_thread, target_thread, False)

    # Verify
    time.sleep(0.15)
    new_fg = user32.GetForegroundWindow()
    success = new_fg == hwnd
    log.debug("Foreground after attempt: hwnd=%d, match=%s", new_fg, success)
    return success


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def search_in_rslogix(
    tag_name: str,
    window_title: str = "VMware Workstation",
    delay_ms: int = 500,
) -> dict[str, bool | str]:
    """Copy tag to clipboard and switch to the target application.

    Returns a dict with ``success`` (bool) and ``message`` (str) with
    detailed debug info.
    """
    import pygetwindow as gw

    if not tag_name.strip():
        return {"success": False, "message": "Tag name is empty."}

    # --- Clipboard ---
    ok = _win32_copy(tag_name)
    log.debug("Clipboard set=%s tag=%r", ok, tag_name)

    if not ok:
        return {"success": False, "message": f"Failed to copy '{tag_name}' to clipboard."}

    # --- Window search ---
    matching = [
        w for w in gw.getWindowsWithTitle(window_title)
        if w.title.strip()
    ]

    if not matching:
        available = list_windows()
        return {
            "success": False,
            "message": (
                f"Copied '{tag_name}' to clipboard but no window matching '{window_title}'. "
                f"Available: {available[:10]}"
            ),
        }

    target = matching[0]

    # --- Activate ---
    activated = _force_foreground(target._hWnd)

    if activated:
        return {
            "success": True,
            "message": f"Copied '{tag_name}' — switched to '{target.title}'",
        }
    else:
        return {
            "success": False,
            "message": f"Copied '{tag_name}' but could not bring '{target.title}' to foreground.",
        }
