# -*- coding: utf-8 -*-
"""配音混音：六幕对白轨 + OST 混合，重封装（不重渲染）。

用法：.venv\\Scripts\\python.exe scripts\\voice_mix.py [--acts act1,act2,...]
                                              [--engine sapi|edge]

引擎（P3-1a）：
- `sapi`（**默认**）：SAPI Huihui 全片同嗓 —— 原片少对白寓言的既有设定，不静默替换；
- `edge`：角色 -> 音色映射，一人一嗓（牛妈妈/牛来/牛爸爸/豹拉各一嗓，
  act5-act6 自动切成年嗓）。需联网 + ffmpeg（edge 只出 mp3，转 wav 走 ffmpeg）；
  单句失败自动回退 sapi，保证"有网更好、没网也出片"。

流程（每幕）：
1. LINES -> 对白轨（t0 精确落位，44.1k mono）；
2. OST + 对白逐样本相加（act1 无 OST，纯对白）；
3. 视频流原样 + 新音轨重封装（-c:v copy，秒级完成）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from niulai.acts import act0_prologue, act1_stand, act2_migration, \
    act3_leopard, act4_wolves, act5_finale, act6_wake
from niulai.audio import tts

FF = os.environ.get('NIULAI_FFMPEG', 'ffmpeg')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'output')
FINAL = os.path.join(OUT, 'final')
OST = os.path.join(OUT, 'ost')

# 幕 -> (场景模块, 幕时长, OST 路径或 None, 视频源, extra 氛围轨或 None)
ACTS = {
    'act0': (act0_prologue, 360.0, None,
             os.path.join(FINAL, 'act0_1080.mp4'), None),
    'act1': (act1_stand, 300.0, None,
             os.path.join(FINAL, 'act1_1080.mp4'),
             os.path.join(OST, 'foley_dawn.wav')),
    'act2': (act2_migration, 720.0,
             os.path.join(OST, 'suite_migration_720.wav'),
             os.path.join(FINAL, 'act2_1080.mp4'), None),
    'act3': (act3_leopard, 720.0,
             os.path.join(OST, 'suite_friend_720.wav'),
             os.path.join(FINAL, 'act3_1080.mp4'), None),
    'act4': (act4_wolves, 1080.0,
             os.path.join(OST, 'suite_wolves_1080.wav'),
             os.path.join(FINAL, 'act4_1080.mp4'), None),
    'act5': (act5_finale, 900.0,
             os.path.join(OST, 'suite_friend_900.wav'),
             os.path.join(FINAL, 'act5_1080.mp4'), None),
    'act6': (act6_wake, 720.0,
             os.path.join(OST, 'suite_credits_720.wav'),
             os.path.join(FINAL, 'act6_1080.mp4'),
             os.path.join(OST, 'foley_reprise.wav')),
}


def main(acts=None, engine='sapi', profile=None):
    names = acts or list(ACTS)
    # profile=pbr 时只换视频源（台词/OST 与画面 profile 无关）
    vdir = os.path.join(OUT, 'final') if profile in (None, 'raw') \
        else os.path.join(OUT, f'final_{profile}')
    ptag = '' if profile in (None, 'raw') else f'_{profile}'
    for name in names:
        mod, dur, ost, video, extra = ACTS[name]
        if profile not in (None, 'raw'):
            video = os.path.join(vdir, os.path.basename(video))
        print(f'== {name}: {len(mod.LINES)} 句台词 (engine={engine})')
        diag = os.path.join(FINAL, f'_diag_{name}.wav')
        # act=name：让 act5/act6 自动切成年嗓（牛来/豹拉长大后换音色）
        _, n = tts.build_dialogue_track(mod.LINES, dur, diag,
                                        tmpdir=os.path.join(FINAL, '_tts_tmp'),
                                        engine=engine, act=name, ffmpeg=FF)
        if ost:
            mid = os.path.join(FINAL, f'_mid_{name}.wav')
            tts.mix_tracks(ost, diag, mid)
            mixed = mid
        else:
            mixed = diag
        if extra:
            fin = os.path.join(FINAL, f'_audio_{name}.wav')
            tts.mix_tracks(mixed, extra, fin)
            mixed = fin
        # sapi 沿用既有 v4 命名（避免覆盖已交付母带）；edge 单独一份便于 AB 对比
        suffix = 'v4' if engine == 'sapi' else engine
        out_mp4 = os.path.join(vdir, f'{name}_voice_{suffix}{ptag}.mp4')
        tts.remux(video, mixed, out_mp4, ffmpeg=FF)
        print(f'  -> {out_mp4} ({n} 句合成)')
    print('VOICE_MIX_DONE')


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--acts', default=None,
                    help='comma list, default all with dialogue')
    ap.add_argument('--engine', default='sapi', choices=['sapi', 'edge'],
                    help='sapi = 全片同嗓（默认，离线）; '
                         'edge = 多角色音色（需联网 + ffmpeg）')
    ap.add_argument('--profile', default=None, choices=[None, 'raw', 'pbr'],
                    help='取哪套视频源：raw=output/final，pbr=output/final_pbr')
    args = ap.parse_args()
    main([a.strip() for a in args.acts.split(',')] if args.acts else None,
         engine=args.engine, profile=args.profile)
