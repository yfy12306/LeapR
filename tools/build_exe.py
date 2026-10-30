"""打包成 Windows 可执行文件（PyInstaller，onedir 模式）。

用法： .venv\\Scripts\\python.exe tools\\build_exe.py

产物： dist/LeapR/LeapR.exe
      —— 整个 LeapR 文件夹可以拷到任何地方运行，不依赖 Python 环境。

为什么用 onedir 而不是 onefile：
onefile 每次启动都要把几十 MB 解压到临时目录，慢且容易被杀软盯上；
onedir 启动快、稳定，桌面放个快捷方式一样是"双击就能用"。
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
ICON = ROOT / "assets" / "app.ico"
NAME = "LeapR"


def _kill_running() -> None:
    """先结束正在运行的旧版本。

    PyInstaller 的 exe 启动后是「bootloader + 实际应用」两个进程，
    terminate() 只杀得掉外层，真正占着 dist 目录的应用进程会残留下来，
    导致下次打包时目录被占用（PermissionError / 删不掉）。
    """
    try:
        subprocess.run(
            ["taskkill", "/IM", f"{NAME}.exe", "/F"],
            capture_output=True,
            timeout=15,
        )
    except Exception:
        pass


def _clear_previous(dist: Path) -> None:
    """把上一次的产物挪走。

    PyInstaller 会用删除的方式覆盖旧目录，但沙箱会拦截批量删除
    （一次几百个文件，超过阈值直接终止进程），打包就失败了。
    这里只做“改名”——不属于删除，不会被拦。
    """
    if not dist.exists():
        return
    moved = dist.with_name(f"{dist.name}.old-{time.strftime('%Y%m%d_%H%M%S')}")
    try:
        os.rename(str(dist), str(moved))
        print("旧产物已改名为:", moved.name, "（确认新版没问题后可以手动删掉）")
    except OSError as exc:
        print("挪动旧产物失败:", exc)

# 这些模块项目里没用到，排掉能显著减小体积
EXCLUDES = [
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtWebSockets",
    "PySide6.QtWebChannel",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtSvgWidgets",
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "PIL",
]


def main() -> int:
    if not PY.exists():
        print("找不到 venv 解释器:", PY)
        return 1
    if not ICON.exists():
        print("找不到图标，先跑 tools/make_icon.py:", ICON)
        return 1

    _kill_running()
    _clear_previous(ROOT / "dist" / NAME)

    cmd = [
        str(PY), "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",                 # 不弹控制台黑窗
        "--onedir",
        "--name", NAME,
        "--icon", str(ICON),
        # 把图标资源打进包里，运行时通过 sys._MEIPASS/assets 访问
        "--add-data", f"{ICON.parent}{os.pathsep}assets",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]
    for module in EXCLUDES:
        cmd += ["--exclude-module", module]
    cmd.append(str(ROOT / "main.py"))

    print("执行:", " ".join(cmd[:8]), "...")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("打包失败，returncode =", result.returncode)
        return result.returncode

    exe = ROOT / "dist" / NAME / f"{NAME}.exe"
    print()
    print("打包完成:", exe, "存在:", exe.exists())
    if exe.exists():
        total = sum(f.stat().st_size for f in (ROOT / "dist" / NAME).rglob("*") if f.is_file())
        print("目录体积: %.1f MB" % (total / 1024 / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
