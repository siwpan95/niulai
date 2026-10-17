# -*- coding: utf-8 -*-
"""配音混音：六幕对白轨（SAPI Huihui 同嗓设定）+ OST 混合，重封装（不重渲染）。

用法：.venv\\Scripts\\python.exe scripts\\voice_mix.py [--acts act1,act2,...]

流程（每幕）：
1. LINES -> 对白轨（t0 精确落位，44.1k mono）；
2. OST + 对白逐样本相加（act1 无 OST，纯对白）；
3. 视频流原样 + 新音轨重封装（-c:v copy，秒级完成）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from niulai.acts import act1_stand, act2_migration, act3_leopard, act4_wolves, \
    act5_finale, act6_wake
from niulai.audio import tts

FF = os.environ.get('NIULAI_FFMPEG', 'ffmpeg')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'output')
FINAL = os.path.join(OUT, 'final')
OST = os.path.join(OUT, 'ost')

# 幕 -> (场景模块, 幕时长, OST 路径或 None, 视频源, extra 氛围轨或 None)
ACTS = {
    'act1': (act1_stand, 300.0, None,
             os.path.join(FINAL, 'act1_stand_10800-19800.mp4'),
             os.path.join(OST, 'foley_dawn.wav')),
    'act2': (act2_migration, 720.0,
             os.path.join(OST, 'loop_ost_migration_21600f.wav'),
             os.path.join(FINAL, 'act2_migration_19800-41400.mp4'), None),
    'act3': (act3_leopard, 720.0,
             os.path.join(OST, 'loop_ost_friend_21600f.wav'),
             os.path.join(FINAL, 'act3_leopard_41400-63000_1080.mp4'), None),
    'act4': (act4_wolves, 1080.0,
             os.path.join(OST, 'loop_ost_wolves_32400f.wav'),
             os.path.join(FINAL, 'act4_wolves_63000-95400_1080.mp4'), None),
    'act5': (act5_finale, 900.0,
             os.path.join(OST, 'loop_ost_friend_27000f.wav'),
             os.path.join(FINAL, 'act5_1080.mp4'), None),
    'act6': (act6_wake, 720.0,
             os.path.join(OST, 'loop_ost_credits_21600f.wav'),
             os.path.join(FINAL, 'act6_1080.mp4'),
             os.path.join(OST, 'foley_reprise.wav')),
}


def main(acts=None):
    names = acts or list(ACTS)
    for name in names:
        mod, dur, ost, video, extra = ACTS[name]
        print(f'== {name}: {len(mod.LINES)} 句台词')
        diag = os.path.join(FINAL, f'_diag_{name}.wav')
        _, n = tts.build_dialogue_track(mod.LINES, dur, diag,
                                        tmpdir=os.path.join(FINAL, '_tts_tmp'))
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
        out_mp4 = os.path.join(FINAL, f'{name}_voice_v4.mp4')
        tts.remux(video, mixed, out_mp4, ffmpeg=FF)
        print(f'  -> {out_mp4} ({n} 句合成)')
    print('VOICE_MIX_DONE')


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--acts', default=None,
                    help='comma list, default all with dialogue')
    args = ap.parse_args()
    main([a.strip() for a in args.acts.split(',')] if args.acts else None)
