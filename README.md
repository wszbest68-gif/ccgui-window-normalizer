# ccgui-window-normalizer

A single-purpose Windows watcher that makes the [CC GUI](https://github.com) desktop app's
main window always open at a fixed, configurable size — matching another app's window
(e.g. Tencent Yuanbao) — without modifying the target program in any way.

让 CC GUI 主窗口每次启动都稳定为指定尺寸（默认 1644×930，与腾讯元宝主窗口外框一致）。
进程外适配，**不修改 CC GUI 任何文件**，按进程完整路径识别，与版本无关，不影响其自动更新。

## How it works / 原理

- `SetWinEventHook` (OUTOFCONTEXT — no DLL injection, no admin rights) listens for
  window-create / window-show events system-wide.
- When the CC GUI **main window** is detected, the very first event callback resizes it
  with `SetWindowPos` (`SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE`) — size only,
  position untouched. Measured end-to-end latency: **<1 ms** (well under the 100 ms budget).
- Main-window identification is dual-channel:
  1. **Title match** — main window title is exactly `CC GUI`;
     the About window (`关于 ccgui`), browser-agent window (`Browser Dock`) and hidden
     helper windows (untitled) never match.
  2. **Size fallback** — default logical size 1300×800 @ window DPI
     (covers the brief moment before the title is set).
- Each window handle is adjusted at most once. On startup the watcher also fixes an
  already-running CC GUI (including the normal-rect of a minimized window via
  `SetWindowPlacement`).
- Blocks in a message loop: **0 % CPU**, ~16 MB RAM (CPython).

监听窗口创建/显示事件（OUTOFCONTEXT，不注入 DLL、不需管理员），在首个事件回调内
只调尺寸、不动位置；端到端实测时延 <1ms。主窗口识别 = 标题完全匹配（主通道）+
默认尺寸换算（兜底），about / browser-agent / 隐藏辅助窗天然不误伤。消息循环阻塞，
CPU≈0，内存约 16MB。

## Requirements / 运行条件

- Windows 10/11, any DPI (per-monitor aware; tested at 120 DPI / 125 % scaling)
- Python 3.10+ (standard library only — **zero dependencies**)

## Setup / 安装

1. Put `watcher.py` and `target-size.txt` in any folder.
2. Edit `watcher.py` line `TARGET_PROCESS` if your ccgui.exe lives elsewhere.
3. Edit `target-size.txt` to your desired physical-pixel size (`width,height`).
4. Run at logon via Task Scheduler (no console window):

```powershell
$action = New-ScheduledTaskAction -Execute 'C:\Path\To\pythonw.exe' -Argument '"C:\Path\To\watcher.py"'
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName 'CCGUI Window Normalizer' -Action $action -Trigger $trigger
Start-ScheduledTask -TaskName 'CCGUI Window Normalizer'
```

## Uninstall / 卸载

```powershell
Unregister-ScheduledTask -TaskName 'CCGUI Window Normalizer' -Confirm:$false
Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process
```

Then delete the folder. Nothing else is touched.

## Files / 文件

| File | Purpose |
|---|---|
| `watcher.py` | The watcher itself (runs resident) / 守望者本体 |
| `target-size.txt` | Target size config, `width,height` in physical px / 目标尺寸配置 |
| `measure_windows.py` | Read-only window measurement for any process / 只读窗口测量 |
| `restore_measure.py` | Restore a minimized CC GUI window and measure it / 恢复并测量 |
| `find_window_by_title.py` | Find top-level windows by title keyword / 按标题找窗口 |
| `get_normal_rect.py` | Read a window's normal rect (works while minimized) / 读 normal rect |

## Known limitations / 已知限制

- If a future CC GUI version changes the main window title (`CC GUI`) *and* its default
  size (1300×800), update the constants at the top of `watcher.py`. Failure mode is
  "silently does nothing" (never touches the wrong window) and is logged.
- Multi-monitor with mixed DPI: size is applied in physical pixels of the window's
  monitor; only the primary-monitor scenario has been tested.
- The window is created visible (CC GUI has no hidden-creation hook), so the resize
  happens within the first event callback after creation. With the borderless window +
  WebView white-screen startup, no flicker or jump is perceptible in practice.
- **Window size is locked for 12 s after each launch** (guard window against CC GUI's
  persisted-size restore, which writes a DPI-confused 0.8× value into the window's
  normal rect). After the guard timer seals (~13 s), you can resize freely.
  Minimize → restore was verified to come back at the target size.
  每次启动后 12 秒内窗口尺寸被锁定（对抗 CC GUI 持久化恢复逻辑，它会把一个
  0.8 倍的 DPI 混淆值写入窗口恢复记忆），约 13 秒封缄后即可自由调整；
  最小化→恢复路径已实测恢复正常。

## License

MIT — see [LICENSE](LICENSE).
