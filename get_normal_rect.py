# -*- coding: utf-8 -*-
"""只读查询指定 hwnd 的 GetWindowPlacement normal rect。用法: python get_normal_rect.py <hwnd> <out>"""
import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.windll.user32


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", wintypes.UINT), ("flags", wintypes.UINT),
                ("showCmd", wintypes.UINT), ("ptMinPosition", wintypes.POINT),
                ("ptMaxPosition", wintypes.POINT), ("rcNormalPosition", wintypes.RECT)]


hwnd = int(sys.argv[1])
wp = WINDOWPLACEMENT()
wp.length = ctypes.sizeof(WINDOWPLACEMENT)
if user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
    rc = wp.rcNormalPosition
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write("hwnd=%d showCmd=%d normal=%dx%d@(%d,%d)\n"
                % (hwnd, wp.showCmd, rc.right - rc.left, rc.bottom - rc.top, rc.left, rc.top))
else:
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write("GetWindowPlacement failed\n")
