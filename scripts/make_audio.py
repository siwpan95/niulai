# -*- coding: utf-8 -*-
"""音频资产生成：变奏组曲（P3-3a）+ CC0 拟音 + 镜头级拟音（P3-4）。

产出（output/ost/）：
- suite_<theme>_<sec>.wav   六条变奏组曲（8 变体确定性拼接，去 180s 循环重复感）
- prologue_ambient.wav      序幕声景（真实风 + 鸟鸣，CC0）
- foley_dawn.wav            act1 清晨氛围（CC0）
- foley_reprise.wav         act6 高飞窗鸟鸣呼应（CC0，窗 425-555s = 云雀高飞镜头）
- spots_act1..act6.wav      镜头级拟音事件轨（scene.shots 派生）

全部确定性（固定 seed / 纯 numpy / 无墙钟）。重跑安全（覆盖同路径）。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from niulai import MASTER_SEED  # noqa: E402
from niulai.audio import foley, spots  # noqa: E402
from niulai.audio.variations import render_suite_track  # noqa: E402
from niulai.timeline import ACTS  # noqa: E402

OST = os.path.join(ROOT, 'output', 'ost')

# (主题, 秒, 文件名)  —— 与各幕时长精确对齐
SUITES = [
    ('migration', 720.0, 'suite_migration_720.wav'),   # act2
    ('friend', 720.0, 'suite_friend_720.wav'),         # act3
    ('wolves', 1080.0, 'suite_wolves_1080.wav'),       # act4
    ('friend', 900.0, 'suite_friend_900.wav'),         # act5
    ('credits', 720.0, 'suite_credits_720.wav'),       # act6
    ('credits', 360.0, 'suite_credits_360.wav'),       # act7
]

SPOT_ACTS = ['act1_stand', 'act2_migration', 'act3_leopard',
             'act4_wolves', 'act5_finale', 'act6_wake']

REPRISE_WINDOW = (425.0, 555.0)    # act6「云雀高飞」镜头（420-560s）内收 10s


def act_duration(act_module_name):
    """幕名 -> 时长秒（timeline.ACTS 单一事实来源；条目名为完整幕名）。"""
    for name, t0, t1, _ in ACTS:
        if name == act_module_name:
            return t1 - t0
    raise KeyError(act_module_name)


def main():
    os.makedirs(OST, exist_ok=True)
    t_all = time.perf_counter()

    for theme, sec, fname in SUITES:
        out = os.path.join(OST, fname)
        t0 = time.perf_counter()
        render_suite_track(theme, out, sec, seed=MASTER_SEED)
        mb = os.path.getsize(out) / 1048576.0
        print(f'[audio] suite {fname}: {sec:.0f}s  {mb:.1f}MB  '
              f'({time.perf_counter() - t0:.0f}s)', flush=True)

    p = foley.render_prologue_ambient(360.0, os.path.join(OST,
                                                          'prologue_ambient.wav'))
    print(f'[audio] prologue_ambient -> {os.path.basename(p)}', flush=True)
    p = foley.render_dawn_ambient(300.0, os.path.join(OST, 'foley_dawn.wav'))
    print(f'[audio] foley_dawn -> {os.path.basename(p)}', flush=True)
    p = foley.render_song_reprise(720.0, os.path.join(OST, 'foley_reprise.wav'),
                                  window=REPRISE_WINDOW)
    print(f'[audio] foley_reprise -> {os.path.basename(p)}', flush=True)

    for act in SPOT_ACTS:
        dur = act_duration(act)
        out = os.path.join(OST, f'spots_{act}.wav')
        t0 = time.perf_counter()
        events = spots.plan_shot_spots(act, seed=MASTER_SEED)
        path, n = spots.render_spot_track(events, dur, out, seed=MASTER_SEED)
        mb = os.path.getsize(path) / 1048576.0
        print(f'[audio] spots {act}: {n} events  {mb:.1f}MB  '
              f'({time.perf_counter() - t0:.0f}s)', flush=True)

    print(f'\n[audio] ALL AUDIO ASSETS DONE '
          f'({time.perf_counter() - t_all:.0f}s)', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
