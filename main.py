"""LeapR —— 离线 TXT 阅读器入口。

设计目标：界面上只有文字。窗口可以完全透明，此时屏幕上看到的就只有小说内容。
"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core.config import load_config, resource_path
from core.fonts import FontManager
from ui.main_window import ReaderWindow


def _activate_existing() -> None:
    """把已经在运行的那个实例叫到前面来。"""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "LeapR")
        if hwnd:
            user32.ShowWindow(hwnd, 5)              # SW_SHOW
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _single_instance_guard() -> bool:
    """单实例保护：已有实例在跑就返回 False，本次应当直接退出。

    没有这道保护时，重复启动（双击 .py、连点两次快捷方式、上次没退干净）会留下
    多个进程，每个都建一层透明窗口、都去抢老板键监听。用户看到的就是：
    窗口叠在一起、鼠标扫过时几层显隐不同步地乱闪、还时不时弹 Windows 错误框。
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        ERROR_ALREADY_EXISTS = 183
        # 命名互斥体；句柄故意不关闭，随进程一起消失
        ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\LeapR.SingleInstance")
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            _activate_existing()
            return False
        return True
    except Exception:
        return True          # 拿不准的时候不要挡住用户用


def main() -> int:
    if not _single_instance_guard():
        print("LeapR 已经在运行了，本次启动退出（已把已有窗口调到前面）",
              file=sys.stderr)
        return 0

    # 任务栏归组 ID（必须在 QApplication 之前设置）
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LeapR.1")
        except Exception:
            pass

    # 高 DPI：跟随系统缩放，避免文字发虚
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("LeapR")
    app.setApplicationDisplayName("LeapR")
    # 关掉窗口不退出程序：窗口关闭和"隐藏到托盘"是同一件事，真正退出走托盘菜单
    app.setQuitOnLastWindowClosed(False)

    icon_path = resource_path("assets/app.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    cfg = load_config()

    # 外部字体必须在 QApplication 之后注册
    fonts = FontManager(cfg.get("font_files", []))

    window = ReaderWindow(cfg, fonts)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
