# -*- coding: utf-8 -*-
"""恢复最小化的 CC GUI 主窗口并测量其尺寸。输出到 restore-result.txt"""
import ctypes
import os
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
BASE = os.path.dirname(os.path.abspath(__file__))
TARGET_PROCESS = r"D:\CC GUI\ccgui.exe"


def process_path(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


def main():
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_cb(hwnd, lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if user32.GetAncestor(hwnd, 2) != hwnd:
            return True
        if process_path(pid.value).lower() != TARGET_PROCESS.lower():
            return True
        tbuf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, tbuf, 256)
        if tbuf.value.strip().lower() == "cc gui":
            found.append(hwnd)
        return True

    user32.EnumWindows(enum_cb, 0)
    lines = ["found %d ccgui main window(s)" % len(found)]
    for hwnd in found:
        iconic = bool(user32.IsIconic(hwnd))
        lines.append("hwnd=%d iconic=%s" % (hwnd, iconic))
        if iconic:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            time.sleep(1.2)
        wr = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(wr))
        cr = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(cr))
        lines.append("after restore: win=%dx%d@(%d,%d) client=%dx%d"
                     % (wr.right - wr.left, wr.bottom - wr.top,
                        wr.left, wr.top, cr.right - cr.left, cr.bottom - cr.top))
    with open(os.path.join(BASE, "restore-result.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
