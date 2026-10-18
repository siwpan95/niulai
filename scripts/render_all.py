# -*- coding: utf-8 -*-
"""全片重渲驱动：八幕顺序 + 分块并行 + resume + 720p 升采 1080p。

用法::

    python scripts/render_all.py                 # 全部八幕
    python scripts/render_all.py --acts act2,act4 --workers 6
    python scripts/render_all.py --skip-upscale  # 只渲染不升采

结构（对齐上一版全片口径）：
- act0-4 渲 1280x720 -> ffmpeg lanczos 升采 1920x1080（既有既定做法）；
- act5-7 渲 1920x1080 原生；
- 每幕产物 output/full/<act>.mp4，终态 output/final/actN_1080.mp4；
- 全程 --resume：中断后重跑只补缺块。

**seed 铁律**：render_parallel 的 --seed 默认 0，而工程主种子是
MASTER_SEED=20260805 —— 必须显式传，否则地形与既有全片不一致（实测踩坑）。

依赖：NIULAI_FFMPEG（或 --ffmpeg）指向真 ffmpeg（imageio-ffmpeg 自带的
静态构建即可，见 docs/增强规划_P4.md 环境节）。
"""
import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from niulai import FPS, MASTER_SEED  # noqa: E402

FF = os.environ.get('NIULAI_FFMPEG', 'ffmpeg')

# (幕, 起帧, 止帧, 分辨率)  —— 帧号与 timeline.ACTS 严格对齐（全片 154,800 帧）
ACTS = [
    ('act0_prologue', 0, 10800, '1280x720'),
    ('act1_stand', 10800, 19800, '1280x720'),
    ('act2_migration', 19800, 41400, '1280x720'),
    ('act3_leopard', 41400, 63000, '1280x720'),
    ('act4_wolves', 63000, 95400, '1280x720'),
    ('act5_finale', 95400, 122400, '1920x1080'),
    ('act6_wake', 122400, 144000, '1920x1080'),
    ('act7_credits', 144000, 154800, '1920x1080'),
]

# ⚠ profile 必须产物隔离：render_parallel 的 --resume 只看块文件是否存在，
# 不认 profile。P5 实测踩坑——pbr 全片重渲被 raw 的既有块全部跳过，等于
# 拿旧 raw 块重新升采（一帧 PBR 都没渲）。非默认 profile 一律走独立目录。
def dirs_for(profile):
    """profile -> (块根目录, 终态目录)。raw/None 沿用既有路径。"""
    tag = '' if profile in (None, 'raw') else f'_{profile}'
    return (os.path.join(ROOT, 'output', f'full{tag}'),
            os.path.join(ROOT, 'output', f'final{tag}'))


def run(cmd, **kw):
    print('  $ ' + ' '.join(str(c) for c in cmd)[:180], flush=True)
    p = subprocess.run([str(c) for c in cmd], cwd=ROOT, **kw)
    return p.returncode


def render_act(act, a, b, size, workers, profile=None):
    full_root, _ = dirs_for(profile)
    out_root = os.path.join(full_root, act)
    concat = os.path.join(full_root, f'{act}.mp4')
    t0 = time.perf_counter()
    cmd = [sys.executable, 'scripts/render_parallel.py',
           '--act', act, '--start', a, '--end', b,
           '--size', size, '--seed', MASTER_SEED,
           '--workers', workers, '--resume',
           '--ffmpeg', FF, '--concat', concat,
           '--out', out_root]
    if profile:
        cmd += ['--profile', profile]
    rc = run(cmd)
    if rc != 0:
        print(f'[render_all] FAIL {act} (rc={rc})', flush=True)
        return None
    el = time.perf_counter() - t0
    fps = (b - a) / el if el > 0 else 0.0
    print(f'[render_all] OK {act}  {(b - a)} frames in {el:.0f}s '
          f'({fps:.1f} fps aggregate)', flush=True)
    return concat


def upscale(src, dst):
    """720p -> 1080p（lanczos，参数与 render_pipe 产物对齐：h264/yuv420p/crf20）。"""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    return run([FF, '-y', '-i', src,
                '-vf', 'scale=1920:1080:flags=lanczos',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20',
                '-r', str(FPS), dst])


def remux_copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    return run([FF, '-y', '-i', src, '-c:v', 'copy', dst])


def main():
    ap = argparse.ArgumentParser(prog='render_all')
    ap.add_argument('--acts', default=None,
                    help='comma list, e.g. act2,act4 (default: all)')
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--skip-upscale', action='store_true')
    ap.add_argument('--profile', default=None,
                    choices=[None, 'raw', 'enhanced', 'pbr'])
    args = ap.parse_args()

    wanted = args.acts.split(',') if args.acts else \
        [a[0] for a in ACTS]
    _, final_dir = dirs_for(args.profile)
    os.makedirs(final_dir, exist_ok=True)
    if args.profile not in (None, 'raw'):
        print(f'[render_all] profile={args.profile} -> {final_dir}',
              flush=True)

    for act, a, b, size in ACTS:
        if act not in wanted:
            continue
        print(f'\n[render_all] === {act}  frames [{a}, {b})  {size} ===',
              flush=True)
        concat = render_act(act, a, b, size, args.workers,
                            profile=args.profile)
        if concat is None:
            return 1
        if args.skip_upscale:
            continue
        idx = act.split('_')[0]                # act0 .. act7
        dst = os.path.join(final_dir, f'{idx}_1080.mp4')
        if size == '1920x1080':
            rc = remux_copy(concat, dst)
        else:
            rc = upscale(concat, dst)
        if rc != 0:
            print(f'[render_all] FAIL finalize {act} (rc={rc})', flush=True)
            return 1
        print(f'[render_all] -> {dst}', flush=True)

    print('\n[render_all] ALL ACTS DONE', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
