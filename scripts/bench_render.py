# -*- coding: utf-8 -*-
"""渲染基准：PNG 路径 vs raw pipe 路径（同场景同帧区间，实测吞吐）。

用法：.venv\Scripts\python.exe scripts\bench_render.py [--frames 30] [--size 1280x720]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from niulai.acts.act0_prologue import PrologueScene          # noqa: E402
from niulai.pipeline import render as pipe                   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', type=int, default=30)
    ap.add_argument('--size', default='1280x720')
    ap.add_argument('--grid', type=int, default=64)
    ap.add_argument('--ffmpeg', default=os.environ.get('NIULAI_FFMPEG', 'ffmpeg'))
    args = ap.parse_args()
    w, h = (int(x) for x in args.size.lower().split('x'))

    scene = PrologueScene(seed=20260805, grid=args.grid)
    n = args.frames

    t0 = time.perf_counter()
    pipe.render_range(scene, 0, n, 'output/bench_png', size=(w, h))
    t_png = time.perf_counter() - t0

    t0 = time.perf_counter()
    m = pipe.render_pipe(scene, 0, n, 'output/bench_pipe.mp4', size=(w, h),
                         ffmpeg=args.ffmpeg)
    t_pipe = time.perf_counter() - t0

    print(f'PNG path : {n / t_png:6.2f} fps  ({t_png:.1f}s / {n} frames)')
    print(f'raw pipe : {n / t_pipe:6.2f} fps  ({t_pipe:.1f}s / {n} frames)')
    print(f'speedup  : {t_png / t_pipe:.1f}x')
    print(f'pipe frames unique: {len(set(m.values())) == len(m)}')
    print('BENCH_DONE')
    return 0


if __name__ == '__main__':
    sys.exit(main())
