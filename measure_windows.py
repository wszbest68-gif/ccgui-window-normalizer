# -*- coding: utf-8 -*-
"""只读测量指定进程的全部顶层窗口：hwnd/可见性/DPI/标题/外框/客户区。
用法: python measure_windows.py <进程名小写不含.exe> <输出文件>
"""
import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def set_dpi_aware():
    # PER_MONITOR_AWARE_V2 = -4
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def get_process_path(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
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


def measure(proc_name, out_path):
    set_dpi_aware()
    lines = []
    targets = []

    @WNDENUMPROC
    def enum_cb(hwnd, lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if user32.GetAncestor(hwnd, 2) != hwnd:  # GA_ROOT
            return True
        path = get_process_path(pid.value)
        base = path.rsplit("\\", 1)[-1].lower() if path else ""
        if base != proc_name + ".exe":
            return True
        vis = user32.IsWindowVisible(hwnd)
        wr = wintypes.RECT()
        cr = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(wr))
        user32.GetClientRect(hwnd, ctypes.byref(cr))
        try:
            dpi = user32.GetDpiForWindow(hwnd)
        except Exception:
            dpi = 0
        tbuf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, tbuf, 256)
        lines.append(
            "hwnd=%d vis=%s dpi=%d title=[%s] win=%dx%d@(%d,%d) client=%dx%d"
            % (hwnd, vis, dpi, tbuf.value,
               wr.right - wr.left, wr.bottom - wr.top, wr.left, wr.top,
               cr.right - cr.left, cr.bottom - cr.top)
        )
        return True

    user32.EnumWindows(enum_cb, 0)
    header = "process=%s windows=%d" % (proc_name, len(lines))
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(header + "\n")
        for ln in lines:
            f.write(ln + "\n")


if __name__ == "__main__":
    measure(sys.argv[1], sys.argv[2])
