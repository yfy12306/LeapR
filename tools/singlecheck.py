"""验证单实例保护。

用法： .venv\\Scripts\\python.exe tools\\singlecheck.py
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "main.py"
PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def kill(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


def main() -> int:
    print("=== 启动第一个实例 ===")
    p1 = subprocess.Popen([sys.executable, str(MAIN)], cwd=str(ROOT))
    print("  pid =", p1.pid)
    time.sleep(7)
    check("第一个实例正常存活", p1.poll() is None)

    print("\n=== 启动第二个实例（应当立刻退出）===")
    t0 = time.time()
    try:
        p2 = subprocess.run([sys.executable, str(MAIN)], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=20)
        cost = time.time() - t0
        print("  返回码 %s，耗时 %.1f 秒" % (p2.returncode, cost))
        if p2.stderr.strip():
            print("  输出:", p2.stderr.strip()[:120])
        check("第二个实例立刻退出", cost < 6.0, "%.1f 秒" % cost)
        check("第二个实例返回码为 0", p2.returncode == 0, str(p2.returncode))
        check("提示了「已经在运行」",
              "已经在运行" in (p2.stderr or "") or "already" in (p2.stderr or "").lower(),
              (p2.stderr or "").strip()[:60])
    except subprocess.TimeoutExpired:
        cost = time.time() - t0
        check("第二个实例立刻退出", False, "超时 %.1f 秒（没被拦住）" % cost)
        # subprocess.run 超时时会自己结束掉子进程，这里不用再额外清理

    print("\n=== 第一个实例应当不受影响 ===")
    check("第一个实例仍存活", p1.poll() is None)

    print("\n=== 第三个实例 ===")
    t0 = time.time()
    try:
        p3 = subprocess.run([sys.executable, str(MAIN)], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=20)
        check("第三个实例同样立刻退出", time.time() - t0 < 6.0,
              "%.1f 秒" % (time.time() - t0))
    except subprocess.TimeoutExpired:
        check("第三个实例同样立刻退出", False, "超时")

    print("\n=== 清理 ===")
    kill(p1.pid)
    time.sleep(1)
    print("  已结束第一个实例")

    print("\n" + "=" * 56)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    for name in FAIL:
        print("  -", name)
    print("=" * 56)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
