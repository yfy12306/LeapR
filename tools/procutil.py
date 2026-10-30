"""测试脚本共用的进程清理。

直接 `proc.terminate()` 经常杀不干净：pythonw / PyInstaller 启动的进程和实际
应用可能是两个进程，残留下来会变成屏幕上的"幽灵窗口"忽隐忽现，或者占着
dist 目录让下次打包失败。统一用 taskkill /T 结束整棵进程树。
"""

import subprocess


def kill_tree(pid: int) -> None:
    """结束整棵进程树。"""
    try:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            capture_output=True,
            timeout=15,
        )
    except Exception:
        pass
