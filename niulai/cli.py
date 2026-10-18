# -*- coding: utf-8 -*-
"""niulai CLI：渲染 / 拼装 / 自检。

用法::

    python -m niulai render --act act0_prologue --start 0 --end 59 \
        --size 1280x720 --out output/act0 [--assemble output/act0.mp4] \
        [--ffmpeg E:/ffmpeg/bin/ffmpeg.exe]
    python -m niulai assemble --frames output/act0 --out output/act0.mp4
    python -m niulai info

控制台输出一律 ASCII（Windows GBK 代码页下中文会变问号，污染自动化解析）。
"""
import argparse
import os
import sys
import time

from . import FPS, MASTER_SEED, RESOLUTION, TOTAL_DURATION, __version__
from .acts import (act0_prologue, act1_stand, act2_migration,  # noqa: F401
                   act3_leopard, act4_wolves, act5_finale, act6_wake,
                   act7_credits)
from .pipeline import profile as pipe_profile
from .pipeline import render as pipe
from .timeline import ACT_NAMES, Timeline

SCENES = {
    'act0_prologue': act0_prologue.PrologueScene,
    'act1_stand': act1_stand.StandScene,
    'act2_migration': act2_migration.MigrationScene,
    'act3_leopard': act3_leopard.LeopardScene,
    'act4_wolves': act4_wolves.WolvesScene,
    'act5_finale': act5_finale.FinaleScene,
    'act6_wake': act6_wake.WakeScene,
    'act7_credits': act7_credits.CreditsScene,
}


def _cmd_render(args):
    scene_cls = SCENES[args.act]
    # 门禁：渲染帧区间必须落在该幕的帧区间内（防帧号错位——
    # P2 全幕曾把 act5 尾部帧号当 act6 渲染，产出 74 分钟错片后才被发现）
    tl = Timeline()
    a0, a1 = tl.act_frames(args.act)
    if args.start < a0 or args.end > a1 or args.end <= args.start:
        raise SystemExit(
            f'frame range {args.start}-{args.end} outside act {args.act} '
            f'[{a0}, {a1}) — check ACTS table (T0 x fps)')
    w, h = (int(x) for x in args.size.lower().split('x'))
    scene = scene_cls(seed=args.seed)
    profile = pipe_profile.get_profile(args.profile)
    if hasattr(scene, 'set_profile'):
        scene.set_profile(profile)
    n = args.end - args.start
    t0 = time.perf_counter()

    def progress(frame, end):
        if frame % 120 == 0:
            el = time.perf_counter() - t0
            rate = (frame - args.start) / el if el > 0 else 0.0
            print(f'[render] frame {frame}/{end}  {rate:5.1f} fps  '
                  f'eta {(end - frame) / max(rate, 1e-6):6.1f}s', flush=True)

    if args.png:
        manifest = pipe.render_range(scene, args.start, args.end, args.out,
                                     size=(w, h), fps=FPS, on_progress=progress,
                                     profile=profile)
        # 尊重 --manifest：raw pipe 分支一直遵守，PNG 分支此前硬写进 --out，
        # 导致外部（scripts/render_parallel.py 的分块清单）找不到清单。
        # 不传时行为完全不变。
        man_path = args.manifest or os.path.join(args.out, 'manifest.json')
        pipe.write_manifest(manifest, man_path,
                            meta={'act': args.act, 'seed': args.seed, 'fps': FPS,
                                  'size': [w, h], 'start': args.start,
                                  'end': args.end})
        print(f'[render] OK {n} frames in {time.perf_counter() - t0:.1f}s '
              f'-> {args.out}')
    else:
        out_mp4 = args.assemble or os.path.join(
            os.path.dirname(args.out) or '.',
            f"{args.act}_{args.start}-{args.end}.mp4")
        manifest = pipe.render_pipe(scene, args.start, args.end, out_mp4,
                                    size=(w, h), fps=FPS, ffmpeg=args.ffmpeg,
                                    on_progress=progress, audio=args.audio,
                                    profile=profile)
        el = time.perf_counter() - t0
        print(f'[render] OK {n} frames in {el:.1f}s ({n / el:.1f} fps) '
              f'-> {out_mp4}')
        if args.manifest:
            man_dir = os.path.dirname(os.path.abspath(args.manifest))
            os.makedirs(man_dir, exist_ok=True)
            pipe.write_manifest(manifest, args.manifest,
                                meta={'act': args.act, 'seed': args.seed,
                                      'fps': FPS, 'size': [w, h],
                                      'start': args.start, 'end': args.end})
            print(f'[render] manifest: {args.manifest}')
    return 0


def _cmd_assemble(args):
    out = pipe.assemble(args.frames, args.out, fps=FPS, ffmpeg=args.ffmpeg)
    size_mb = os.path.getsize(out) / 1048576.0
    print(f'[assemble] OK {out}  ({size_mb:.1f} MB)')
    return 0


def _cmd_info(args):
    tl = Timeline()
    print(f'niulai {__version__}  ({act0_prologue.__name__} scenes: '
          f'{len(SCENES)})')
    print(f'film: 86 min = {TOTAL_DURATION:.0f}s @ {FPS} fps, '
          f'{int(TOTAL_DURATION * FPS)} frames, seed {MASTER_SEED}')
    for name, start, end, desc in tl_acts():
        print(f'  {name:16s} {start:7.1f}-{end:7.1f}s  {desc}')
    return 0


def tl_acts():
    from .timeline import ACTS
    return ACTS


def main(argv=None):
    p = argparse.ArgumentParser(prog='niulai')
    p.add_argument('--version', action='version', version=__version__)
    sub = p.add_subparsers(dest='cmd', required=True)

    pr = sub.add_parser('render', help='render a frame range of one act')
    pr.add_argument('--act', default='act0_prologue', choices=sorted(SCENES))
    pr.add_argument('--start', type=int, default=0)
    pr.add_argument('--end', type=int, default=60)
    pr.add_argument('--size', default=f'{RESOLUTION[0]}x{RESOLUTION[1]}')
    pr.add_argument('--out', default='output/act0')
    pr.add_argument('--seed', type=int, default=MASTER_SEED)
    pr.add_argument('--assemble', default=None, help='also assemble MP4 to this path')
    pr.add_argument('--audio', default=None, help='soundtrack file to mux in')
    pr.add_argument('--manifest', default=None, help='write frame md5 manifest')
    pr.add_argument('--png', action='store_true',
                    help='legacy PNG-sequence path (slow); default is raw pipe')
    pr.add_argument('--ffmpeg', default=os.environ.get('NIULAI_FFMPEG', 'ffmpeg'))
    pr.add_argument('--profile', default='raw', choices=['raw', 'enhanced'],
                    help='raw=忠实粗粝（默认）；enhanced=WBOIT 透明水面 + '
                         'Bloom 后处理（引擎能力展示，默认关闭）')
    pr.set_defaults(func=_cmd_render)

    pa = sub.add_parser('assemble', help='assemble PNG sequence into MP4')
    pa.add_argument('--frames', required=True)
    pa.add_argument('--out', required=True)
    pa.add_argument('--ffmpeg', default=os.environ.get('NIULAI_FFMPEG', 'ffmpeg'))
    pa.set_defaults(func=_cmd_assemble)

    pi = sub.add_parser('info', help='print film structure')
    pi.set_defaults(func=_cmd_info)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
