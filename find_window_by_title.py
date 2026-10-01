# -*- coding: utf-8 -*-
"""枚举全部顶层窗口，打印标题包含关键字的窗口及其进程。找幽灵窗口用。"""
import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def process_path(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return "<no access>"
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


def main(keyword, out_path):
    kw = keyword.lower()
    hits = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_cb(hwnd, lparam):
        if user32.GetAncestor(hwnd, 2) != hwnd:
            return True
        tbuf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, tbuf, 512)
        title = tbuf.value
        if kw in title.lower():
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            vis = user32.IsWindowVisible(hwnd)
            wr = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(wr))
            hits.append("hwnd=%d pid=%d vis=%s title=[%s] proc=%s rect=%dx%d@(%d,%d)"
                        % (hwnd, pid.value, vis, title, process_path(pid.value),
                           wr.right - wr.left, wr.bottom - wr.top, wr.left, wr.top))
        return True

    user32.EnumWindows(enum_cb, 0)
    with open(out_path, "a", encoding="utf-8") as f:
        f.write("keyword=%s hits=%d\n" % (keyword, len(hits)))
        for h in hits:
            f.write(h + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
