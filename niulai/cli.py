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
from .acts import act0_prologue
from .pipeline import render as pipe
from .timeline import ACT_NAMES, Timeline

SCENES = {'act0_prologue': act0_prologue.PrologueScene}


def _cmd_render(args):
    scene_cls = SCENES[args.act]
    w, h = (int(x) for x in args.size.lower().split('x'))
    scene = scene_cls(seed=args.seed)
    n = args.end - args.start
    t0 = time.perf_counter()
    last = [0]

    def progress(frame, end):
        last[0] = frame
        if frame % 60 == 0:
            el = time.perf_counter() - t0
            rate = (frame - args.start) / el if el > 0 else 0.0
            print(f'[render] frame {frame}/{end}  {rate:5.1f} fps  '
                  f'eta {(end - frame) / max(rate, 1e-6):6.1f}s', flush=True)

    manifest = pipe.render_range(scene, args.start, args.end, args.out,
                                 size=(w, h), fps=FPS, on_progress=progress)
    meta = {'act': args.act, 'seed': args.seed, 'fps': FPS, 'size': [w, h],
            'start': args.start, 'end': args.end}
    man_path = os.path.join(args.out, 'manifest.json')
    pipe.write_manifest(manifest, man_path, meta=meta)
    el = time.perf_counter() - t0
    print(f'[render] OK {n} frames in {el:.1f}s -> {args.out}')
    print(f'[render] manifest: {man_path}')
    if args.assemble:
        out = pipe.assemble(args.out, args.assemble, fps=FPS, ffmpeg=args.ffmpeg)
        size_mb = os.path.getsize(out) / 1048576.0
        print(f'[assemble] OK {out}  ({size_mb:.1f} MB)')
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
    pr.add_argument('--ffmpeg', default=os.environ.get('NIULAI_FFMPEG', 'ffmpeg'))
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
