# -*- coding: utf-8 -*-
"""niulai 环境自举：从零到 `python -m niulai info` 可跑。

用法::

    python scripts/bootstrap.py                      # 用当前解释器建 .venv
    python scripts/bootstrap.py --python E:/py313/python.exe
    python scripts/bootstrap.py --no-install         # 只建 venv，不装依赖
    python scripts/bootstrap.py --ffmpeg E:/ffmpeg/bin/ffmpeg.exe

步骤：探测解释器 -> 建 venv -> 装 `-e .[dev,audio,tts]` -> 探测 ffmpeg。

设计口径：
- **不做静默失败**。ffmpeg 是拼装 MP4 的硬依赖，找不到就打印可复制的下载指引，
  并以退出码 1 结束（而不是装作成功，让用户在几小时渲染后才撞墙）；
- 控制台输出一律 ASCII（Windows GBK 代码页下中文会变问号，污染自动化解析）。

P3-0 交付物。README 里旧的 `E:\\Python314\\python.exe` 已失效，本脚本不再硬编码
任何本机专属路径。
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = REPO_ROOT / '.venv'
EXTRAS = 'dev,audio,tts'

# ffmpeg 探测顺序：显式参数 -> 环境变量 -> PATH -> 常见安装位置
FFMPEG_CANDIDATES = [
    'C:/ffmpeg/bin/ffmpeg.exe',
    'D:/ffmpeg/bin/ffmpeg.exe',
    'E:/ffmpeg/bin/ffmpeg.exe',
    'C:/Program Files/ffmpeg/bin/ffmpeg.exe',
    'C:/ProgramData/chocolatey/bin/ffmpeg.exe',
]

FFMPEG_HINT = """\
[ffmpeg] NOT FOUND - it is a hard dependency (MP4 muxing). Get it:

  option A (gyan.dev static build, recommended on Windows):
      https://www.gyan.dev/ffmpeg/builds/   ->  ffmpeg-release-essentials.zip
      unzip, then either put bin/ on PATH or pass --ffmpeg <path>

  option B (package manager):
      winget install Gyan.FFmpeg
      choco install ffmpeg
      scoop install ffmpeg

  then re-run:  python scripts/bootstrap.py --ffmpeg <path>
  (or set env NIULAI_FFMPEG=<path> once, CLI picks it up automatically)
"""


def log(msg):
    print(msg, flush=True)


def venv_python(venv_dir):
    """返回 venv 内解释器路径（Windows: Scripts/python.exe；Unix: bin/python）。"""
    if os.name == 'nt':
        return venv_dir / 'Scripts' / 'python.exe'
    return venv_dir / 'bin' / 'python'


def find_ffmpeg(explicit=None):
    """按 显式参数 -> NIULAI_FFMPEG -> PATH -> 常见位置 顺序探测。"""
    if explicit:
        p = Path(explicit)
        return str(p) if p.is_file() else None
    env = os.environ.get('NIULAI_FFMPEG')
    if env and Path(env).is_file():
        return env
    which = shutil.which('ffmpeg')
    if which:
        return which
    for c in FFMPEG_CANDIDATES:
        if Path(c).is_file():
            return c
    return None


def run(cmd, cwd=None, check=True):
    log('  $ ' + ' '.join(str(c) for c in cmd))
    proc = subprocess.run([str(c) for c in cmd], cwd=str(cwd or REPO_ROOT))
    if check and proc.returncode != 0:
        raise SystemExit(f'[bootstrap] command failed ({proc.returncode}): '
                         f'{cmd[0]}')
    return proc.returncode


def main(argv=None):
    p = argparse.ArgumentParser(prog='bootstrap')
    p.add_argument('--python', default=sys.executable,
                   help='interpreter to create the venv with (default: current)')
    p.add_argument('--venv', default=str(VENV_DIR), help='venv directory')
    p.add_argument('--ffmpeg', default=None, help='explicit ffmpeg path')
    p.add_argument('--no-install', action='store_true',
                   help='create venv only, skip pip install')
    p.add_argument('--no-ffmpeg-check', action='store_true',
                   help='skip ffmpeg probe (e.g. rendering PNG sequence only)')
    args = p.parse_args(argv)

    log(f'[bootstrap] niulai repo: {REPO_ROOT}')

    # 1. 解释器
    base_py = Path(args.python)
    if not base_py.is_file():
        raise SystemExit(f'[bootstrap] python not found: {base_py}')
    log(f'[bootstrap] base python: {base_py}')
    ver = subprocess.run([str(base_py), '-V'], capture_output=True, text=True)
    log(f'[bootstrap]            {ver.stdout.strip() or ver.stderr.strip()}')
    major, minor = ver.stdout.strip().split()[1].split('.')[:2]
    if (int(major), int(minor)) < (3, 11):
        raise SystemExit('[bootstrap] requires-python >= 3.11 '
                         f'(got {major}.{minor})')

    # 2. venv
    venv = Path(args.venv)
    vpy = venv_python(venv)
    if vpy.is_file():
        log(f'[bootstrap] venv already exists: {venv} (reusing)')
    else:
        log(f'[bootstrap] creating venv: {venv}')
        if run([base_py, '-m', 'venv', venv]) != 0:
            raise SystemExit('[bootstrap] venv creation failed')

    # 3. 依赖
    if args.no_install:
        log('[bootstrap] --no-install: skipping pip install')
    else:
        log(f'[bootstrap] installing -e .[{EXTRAS}] ...')
        run([vpy, '-m', 'pip', 'install', '--upgrade', 'pip'])
        run([vpy, '-m', 'pip', 'install', '-e', f'.[{EXTRAS}]'])

    # 4. ffmpeg
    if args.no_ffmpeg_check:
        log('[bootstrap] --no-ffmpeg-check: skipping ffmpeg probe')
        ffmpeg = None
    else:
        ffmpeg = find_ffmpeg(args.ffmpeg)
        if ffmpeg:
            log(f'[bootstrap] ffmpeg OK: {ffmpeg}')
            v = subprocess.run([ffmpeg, '-version'], capture_output=True,
                               text=True)
            first = (v.stdout or v.stderr).splitlines()[:1]
            if first:
                log(f'[bootstrap]          {first[0].strip()}')
            log('[bootstrap] tip: set NIULAI_FFMPEG so the CLI picks it up '
                'without --ffmpeg')
        else:
            log(FFMPEG_HINT)
            return 1

    # 5. 收尾指引
    exe = vpy.name
    log('')
    log('[bootstrap] done. next steps:')
    log(f'  {vpy} -m niulai info')
    log(f'  {vpy} tests/test_smoke.py')
    if ffmpeg:
        log(f'  {vpy} -m niulai render --act act0_prologue --start 0 '
            f'--end 300 --size 1280x720 --out output/act0_smoke '
            f'--ffmpeg {ffmpeg}')
    else:
        log('  (render/assemble blocked until ffmpeg is installed)')
    log(f'[bootstrap] interpreter for scripts: {exe}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
