# -*- coding: utf-8 -*-
"""
CC GUI 启动窗口规格化守望者 (ccgui-window-normalizer)
单一职责：监测 D:\\CC GUI\\ccgui.exe 主窗口创建事件，在窗口可见后的第一个
事件回调内将其客户区外框调整为目标尺寸（默认与元宝主窗口外框一致）。
- 不修改 CC GUI 任何文件；按进程完整路径识别，与版本无关
- SetWinEventHook OUTOFCONTEXT：不注入 DLL、不需要管理员
- 只匹配主窗口默认尺寸(1300x800 逻辑像素)，about(360x240) 与
  browser-agent(1280x900) 窗口天然不匹配，不受影响
- 只调尺寸、不动位置（SWP_NOMOVE），每个窗口只调一次
- 消息循环阻塞等待，CPU 占用为零
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

# ---------------- 配置 ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "target-size.txt")
LOG_PATH = os.path.join(BASE_DIR, "watcher.log")
PID_PATH = os.path.join(BASE_DIR, "watcher.pid")
TARGET_PROCESS = r"D:\CC GUI\ccgui.exe"
DEFAULT_TARGET = (1644, 930)  # 元宝主窗口外框物理像素(实测 2026-10-01, dpi=120)
MAIN_LOGICAL_W, MAIN_LOGICAL_H = 1300.0, 800.0  # CC GUI 主窗口默认逻辑尺寸
SIZE_TOLERANCE = 12  # 物理像素容差

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

EVENT_OBJECT_CREATE = 0x8000
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_LOCATIONCHANGE = 0x800B
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0001
POST_ADJUST_GUARD_MS = 12000  # 守卫窗：CC GUI 前端在启动后数秒才恢复持久化尺寸，
                              # 12s 内每次被改走都拉回；超过视为用户手动操作，绝不干预
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
GA_ROOT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ALREADY_EXISTS = 183

WINEVENTPROC = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
    wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("rcNormalPosition", wintypes.RECT),
    ]


def log(msg):
    line = "%s.%03d %s\n" % (
        time.strftime("%Y-%m-%d %H:%M:%S"),
        int((time.time() % 1) * 1000), msg)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def load_target():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            txt = f.read().strip().split("#")[0].strip()
        w, h = txt.replace("x", ",").split(",")[:2]
        w, h = int(w), int(h)
        if 400 <= w <= 7680 and 300 <= h <= 4320:
            return (w, h)
    except Exception:
        pass
    return DEFAULT_TARGET


TARGET_W, TARGET_H = load_target()

_pid_path_cache = {}
_adjusted = set()
_adjust_time = {}   # hwnd -> GetTickCount() when adjusted
_sealed = set()     # hwnd 已最终确认（守卫期结束或已补救），之后绝不干预
_seen_mismatch = set()


def set_dpi_aware():
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def process_path(pid):
    if pid in _pid_path_cache:
        return _pid_path_cache[pid]
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    path = ""
    if h:
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                path = buf.value
        finally:
            kernel32.CloseHandle(h)
    _pid_path_cache[pid] = path
    if len(_pid_path_cache) > 256:
        _pid_path_cache.clear()
    return path


def is_ccgui_main_window(hwnd):
    """主窗口识别（双通道）：
    主通道=标题完全匹配 "CC GUI"（实测；about="关于 ccgui"、browser-agent="Browser Dock"、
    隐藏辅助窗=空标题，均不匹配）。注意 CC GUI 实际有窗口尺寸持久化（可恢复为非默认尺寸），
    故不能只依赖尺寸白名单。
    兜底=默认尺寸 1300x800 逻辑 @ 窗口DPI（兼容 CREATE 早期标题未就绪）。"""
    if user32.GetAncestor(hwnd, GA_ROOT) != hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if process_path(pid.value).lower() != TARGET_PROCESS.lower():
        return False
    tbuf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, tbuf, 256)
    if tbuf.value.strip().lower() == "cc gui":
        return True
    wr = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(wr)):
        return False
    w = wr.right - wr.left
    h = wr.bottom - wr.top
    try:
        dpi = user32.GetDpiForWindow(hwnd)
    except Exception:
        dpi = 96
    if not dpi:
        dpi = 96
    exp_w = round(MAIN_LOGICAL_W * dpi / 96.0)
    exp_h = round(MAIN_LOGICAL_H * dpi / 96.0)
    if abs(w - exp_w) <= SIZE_TOLERANCE and abs(h - exp_h) <= SIZE_TOLERANCE:
        return True
    if hwnd not in _seen_mismatch and w > 400 and h > 300:
        _seen_mismatch.add(hwnd)
        log("seen ccgui top-level window %dx%d (expected ~%dx%d), not main default, skip"
            % (w, h, exp_w, exp_h))
    return False


def apply_size(hwnd, reason, event_time=0):
    if hwnd in _adjusted:
        return
    r = user32.SetWindowPos(hwnd, 0, 0, 0, TARGET_W, TARGET_H,
                            SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)
    now = kernel32.GetTickCount()
    latency = (now - event_time) & 0xFFFFFFFF if event_time else -1
    if r:
        _adjusted.add(hwnd)
        _adjust_time[hwnd] = now
        log("ADJUSTED hwnd=%d -> %dx%d reason=%s latency=%sms"
            % (hwnd, TARGET_W, TARGET_H, reason, latency))
    else:
        log("SetWindowPos FAILED hwnd=%d err=%d reason=%s"
            % (hwnd, kernel32.GetLastError(), reason))


def guard_check(hwnd, event_time):
    """调整后守卫：CC GUI 存在"创建后恢复持久化尺寸"逻辑（含逻辑/物理 DPI 混淆），
    会覆盖 CREATE 时的调整。守卫期(3s)内发现尺寸被改走则补救一次并封缄；
    守卫期后任何变动视为用户手动操作，绝不干预。"""
    if hwnd not in _adjusted or hwnd in _sealed:
        return
    now = kernel32.GetTickCount()
    dt = (now - _adjust_time.get(hwnd, now)) & 0xFFFFFFFF
    if dt > POST_ADJUST_GUARD_MS:
        _sealed.add(hwnd)
        return
    wr = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(wr)):
        _sealed.add(hwnd)
        return
    w = wr.right - wr.left
    h = wr.bottom - wr.top
    if abs(w - TARGET_W) <= 2 and abs(h - TARGET_H) <= 2:
        return
    r = user32.SetWindowPos(hwnd, 0, 0, 0, TARGET_W, TARGET_H,
                            SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)
    # 不 sealed：守卫窗内允许多次补救（覆盖逻辑可能分多步/多次执行）；
    # _adjust_time 保持首次调整时间，窗长硬顶 12s，超时后 sealed 不再干预
    if r:
        latency = (now - event_time) & 0xFFFFFFFF if event_time else -1
        log("RE-ADJUSTED hwnd=%d %dx%d -> %dx%d (guard %dms) latency=%sms"
            % (hwnd, w, h, TARGET_W, TARGET_H, dt, latency))
    else:
        log("RE-ADJUST FAILED hwnd=%d err=%d" % (hwnd, kernel32.GetLastError()))


def fix_existing():
    """启动时矫正已在运行的 CC GUI 主窗口（含最小化状态的 normal rect）。"""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_cb(hwnd, lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if user32.GetAncestor(hwnd, GA_ROOT) != hwnd:
            return True
        if process_path(pid.value).lower() != TARGET_PROCESS.lower():
            return True
        tbuf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, tbuf, 256)
        if tbuf.value.strip().lower() == "cc gui":
            found.append(hwnd)
        return True

    user32.EnumWindows(enum_cb, 0)
    for hwnd in found:
        if user32.IsIconic(hwnd):
            wp = WINDOWPLACEMENT()
            wp.length = ctypes.sizeof(WINDOWPLACEMENT)
            if user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
                rc = wp.rcNormalPosition
                nw = TARGET_W
                nh = TARGET_H
                cur_w = rc.right - rc.left
                cur_h = rc.bottom - rc.top
                if abs(cur_w - nw) > 1 or abs(cur_h - nh) > 1:
                    wp.rcNormalPosition.right = rc.left + nw
                    wp.rcNormalPosition.bottom = rc.top + nh
                    if user32.SetWindowPlacement(hwnd, ctypes.byref(wp)):
                        _adjusted.add(hwnd)
                        log("ADJUSTED(minimized normal-rect) hwnd=%d -> %dx%d"
                            % (hwnd, nw, nh))
        else:
            wr = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(wr))
            w = wr.right - wr.left
            h = wr.bottom - wr.top
            if abs(w - TARGET_W) > 1 or abs(h - TARGET_H) > 1:
                apply_size(hwnd, "existing")


@WINEVENTPROC
def win_event_cb(hook, event, hwnd, idObject, idChild, eventThread, eventTime):
    try:
        if idObject != 0 or idChild != 0:  # OBJID_WINDOW only
            return
        if event == EVENT_OBJECT_LOCATIONCHANGE:
            guard_check(hwnd, eventTime)
            return
        if hwnd in _adjusted:
            return
        if is_ccgui_main_window(hwnd):
            apply_size(hwnd, "create" if event == EVENT_OBJECT_CREATE else "show",
                       eventTime)
    except Exception as e:
        log("callback error: %r" % (e,))


def ensure_single_instance():
    name = "Global\\CCGUIWindowNormalizerMutex"
    kernel32.CreateMutexW(None, True, name)
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        log("another instance already running, exit")
        return False
    return True


def main():
    set_dpi_aware()
    if not ensure_single_instance():
        return
    with open(PID_PATH, "w") as f:
        f.write(str(os.getpid()))
    log("watcher start pid=%d target=%dx%d config=%s"
        % (os.getpid(), TARGET_W, TARGET_H, CONFIG_PATH))

    fix_existing()

    hook1 = user32.SetWinEventHook(
        EVENT_OBJECT_CREATE, EVENT_OBJECT_CREATE, 0,
        win_event_cb, 0, 0,
        WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS)
    hook2 = user32.SetWinEventHook(
        EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW, 0,
        win_event_cb, 0, 0,
        WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS)
    hook3 = user32.SetWinEventHook(
        EVENT_OBJECT_LOCATIONCHANGE, EVENT_OBJECT_LOCATIONCHANGE, 0,
        win_event_cb, 0, 0,
        WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS)
    if not hook1 and not hook2 and not hook3:
        log("SetWinEventHook failed err=%d" % kernel32.GetLastError())
        return
    log("hooks installed create=%s show=%s locchange=%s"
        % (bool(hook1), bool(hook2), bool(hook3)))

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

    if hook1:
        user32.UnhookWinEvent(hook1)
    if hook2:
        user32.UnhookWinEvent(hook2)
    if hook3:
        user32.UnhookWinEvent(hook3)
    log("watcher exit")


if __name__ == "__main__":
    main()
