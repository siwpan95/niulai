# -*- coding: utf-8 -*-
"""niulai 环境体检：一次性把"能不能跑全片"问清楚。

用法::

    python scripts/check_env.py            # 自动找 .venv
    python scripts/check_env.py --venv .venv
    python scripts/check_env.py --disk-gb 50   # 全片渲染所需临时空间阈值

判定分级：
- **FAIL**：阻塞渲染/拼装，必须先修（缺依赖 / 缺 ffmpeg / 磁盘不够）；
- **WARN**：不影响主流程，但会降级（缺 TTS 引擎 / 未跑在 venv 内）；
- **PASS**：正常。

退出码：有 FAIL -> 1；否则 0（便于 CI 与 bootstrap 串接）。

控制台输出一律 ASCII（Windows GBK 代码页下中文会变问号，污染自动化解析）。
"""
import argparse
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# (import name, pip name, hard?)
DEPENDENCIES = [
    ('world3d', '3dworld', True),
    ('allin_engine', 'allin-engine', True),
    ('pyglet', 'pyglet (via 3dworld)', True),
    ('numpy', 'numpy[audio]', False),
    ('scipy', 'scipy[audio]', False),
    ('edge_tts', 'edge-tts[tts]', False),
]

FFMPEG_CANDIDATES = [
    'C:/ffmpeg/bin/ffmpeg.exe',
    'D:/ffmpeg/bin/ffmpeg.exe',
    'E:/ffmpeg/bin/ffmpeg.exe',
    'C:/Program Files/ffmpeg/bin/ffmpeg.exe',
    'C:/ProgramData/chocolatey/bin/ffmpeg.exe',
]


class Report:
    def __init__(self):
        self.rows = []

    def add(self, item, status, detail=''):
        self.rows.append((item, status, detail))

    @property
    def failed(self):
        return any(s == 'FAIL' for _, s, _ in self.rows)

    def render(self):
        width = max(len(r[0]) for r in self.rows) if self.rows else 10
        out = []
        for item, status, detail in self.rows:
            out.append(f'  [{status:4s}] {item.ljust(width)}  {detail}')
        return '\n'.join(out)


def find_ffmpeg():
    env = os.environ.get('NIULAI_FFMPEG')
    if env and Path(env).is_file():
        return env, 'NIULAI_FFMPEG'
    which = shutil.which('ffmpeg')
    if which:
        return which, 'PATH'
    for c in FFMPEG_CANDIDATES:
        if Path(c).is_file():
            return c, 'known location'
    return None, ''


def ffmpeg_version(path):
    try:
        p = subprocess.run([path, '-version'], capture_output=True, text=True,
                           timeout=15)
        line = (p.stdout or p.stderr).splitlines()
        return line[0].strip() if line else 'unknown'
    except Exception as e:                                  # pragma: no cover
        return f'unreadable ({e})'


def free_gb(path):
    """目标路径所在盘的剩余空间（GB）。

    路径尚未创建时（全新 clone 下 output/ 不存在）回退到最近的已存在祖先，
    否则会误报 "cannot stat" —— 那是脚本的缺陷，不是环境的问题。
    返回 (gb, 实际统计的路径)。
    """
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        total, used, free = shutil.disk_usage(str(p))
        return free / (1024 ** 3), str(p)
    except Exception:                                       # pragma: no cover
        return None, str(p)


def main(argv=None):
    p = argparse.ArgumentParser(prog='check_env')
    p.add_argument('--venv', default=str(REPO_ROOT / '.venv'))
    p.add_argument('--disk-gb', type=float, default=50.0,
                   help='required free disk for a full-film render (GB)')
    p.add_argument('--out', default=str(REPO_ROOT / 'output'),
                   help='output dir whose drive is checked for free space')
    args = p.parse_args(argv)

    rep = Report()

    # 1. interpreter
    ver = sys.version_info
    ok_py = (ver.major, ver.minor) >= (3, 11)
    rep.add('python', 'PASS' if ok_py else 'FAIL',
            f'{ver.major}.{ver.minor}.{ver.micro} ({sys.executable})'
            + ('' if ok_py else '  -- requires >= 3.11'))

    # 2. venv
    in_venv = (getattr(sys, 'base_prefix', sys.prefix) != sys.prefix)
    venv = Path(args.venv)
    vpy = (venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))
    if in_venv:
        rep.add('venv', 'PASS', f'running inside {sys.prefix}')
    elif vpy.is_file():
        rep.add('venv', 'WARN',
                f'exists at {venv} but not activated -- run: {vpy}')
    else:
        rep.add('venv', 'WARN',
                f'no venv at {venv} -- run: python scripts/bootstrap.py')

    # 3. dependencies
    for imp, pipname, hard in DEPENDENCIES:
        try:
            m = importlib.import_module(imp)
            v = getattr(m, '__version__', '')
            rep.add(pipname.split('[')[0], 'PASS', v or 'imported')
        except Exception as e:
            rep.add(pipname.split('[')[0], 'FAIL' if hard else 'WARN',
                    f'import failed: {type(e).__name__}')

    # 4. package import（工程自身）
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import niulai                                       # noqa: F401
        from niulai import FPS, TOTAL_DURATION              # noqa: F401
        rep.add('niulai pkg', 'PASS',
                f'{TOTAL_DURATION:.0f}s @ {FPS}fps '
                f'= {int(TOTAL_DURATION * FPS)} frames')
    except Exception as e:
        rep.add('niulai pkg', 'FAIL', f'import failed: {e}')

    # 5. ffmpeg
    ff, src = find_ffmpeg()
    if ff:
        rep.add('ffmpeg', 'PASS', f'{ff}  ({src})')
        rep.add('ffmpeg ver', 'PASS', ffmpeg_version(ff)[:72])
    else:
        rep.add('ffmpeg', 'FAIL',
                'not found (PATH / NIULAI_FFMPEG / known locations) -- '
                'blocks MP4 muxing')

    # 6. disk
    gb, probed = free_gb(args.out)
    if gb is None:
        rep.add('disk', 'WARN', f'cannot stat {probed}')
    else:
        ok = gb >= args.disk_gb
        rep.add('disk', 'PASS' if ok else 'WARN',
                f'{gb:.1f} GB free (probed {probed}; '
                f'want >= {args.disk_gb:.0f} GB for a full render)')

    print('[check_env] niulai environment report')
    print(rep.render())
    n_fail = sum(1 for _, s, _ in rep.rows if s == 'FAIL')
    n_warn = sum(1 for _, s, _ in rep.rows if s == 'WARN')
    print(f'[check_env] summary: {len(rep.rows) - n_fail - n_warn} PASS, '
          f'{n_warn} WARN, {n_fail} FAIL')
    if n_fail:
        print('[check_env] blocked: fix FAIL items, or run '
              'scripts/bootstrap.py first')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
