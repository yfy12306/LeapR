"""在桌面创建「LeapR」快捷方式，指向打包好的 exe。

用法： .venv\\Scripts\\python.exe tools\\install_shortcut.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "LeapR" / "LeapR.exe"
DESKTOP = Path.home() / "Desktop"
LNK = DESKTOP / "LeapR.lnk"


def main() -> int:
    if not EXE.exists():
        print("找不到 exe，先跑 tools/build_exe.py：", EXE)
        return 1

    script = f'''
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("{LNK}")
$lnk.TargetPath = "{EXE}"
$lnk.WorkingDirectory = "{EXE.parent}"
$lnk.IconLocation = "{EXE}"
$lnk.Description = "LeapR - 离线 TXT 阅读器"
$lnk.Save()
Write-Output "ok"
'''
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("创建失败:", result.stderr.strip()[-600:])
        return 1

    print("快捷方式已创建:", LNK, "存在:", LNK.exists())
    return 0


if __name__ == "__main__":
    sys.exit(main())
