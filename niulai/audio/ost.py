# -*- coding: utf-8 -*-
"""程序化 OST：三主题（迁徙 / 友情 / 狼袭），allin_engine.audio 渲染 WAV。

主题即 MusicPattern（声明式旋律）+ generate_music_wav 离线渲染。
与 3dworld kkrieger_audio 的"程序化配乐"同路线 —— 零音频素材文件。
"""
import os

from allin_engine.audio.music_gen import (EnvShape, MusicPattern, OscType,
                                          generate_music_wav)

# 五声音阶（宫调式近似）—— 东方寓言气质
PENTA = ['C', 'D', 'E', 'G', 'A']


def _phrase(degrees, octave=0, beats=1.0):
    """音级 -> (notes, durations)（可加休止 None）。"""
    notes, durs = [], []
    for d in degrees:
        if d is None:
            notes.append(None)
        else:
            notes.append(f'{PENTA[d % 5]}{4 + octave + d // 5}')
        durs.append(beats)
    return notes, durs


THEME_MIGRATION = MusicPattern(
    name='迁徙', notes=[], durations=[],
    bpm=96, loop=True, osc_type=OscType.TRIANGLE, volume=0.16,
    env_shape=EnvShape.PAD, harmonics=[(2.0, 0.25), (3.0, 0.1)],
)

THEME_FRIEND = MusicPattern(
    name='友情', notes=[], durations=[],
    bpm=72, loop=True, osc_type=OscType.SINE, volume=0.18,
    env_shape=EnvShape.PAD, vibrato_rate=4.5, vibrato_depth=0.12,
)

THEME_WOLVES = MusicPattern(
    name='狼袭', notes=[], durations=[],
    bpm=132, loop=True, osc_type=OscType.SQUARE, volume=0.13,
    env_shape=EnvShape.PLUCK, harmonics=[(2.0, 0.3)],
)

# 旋律填充（音级序列；None = 休止）
THEME_MIGRATION.notes, THEME_MIGRATION.durations = _phrase(
    [0, 2, 4, 2, None, 1, 3, 4, None, 0, 4, 3, 2, None, 1, 0], beats=0.5)
THEME_FRIEND.notes, THEME_FRIEND.durations = _phrase(
    [4, None, 3, 2, 1, None, 0, None, 2, None, 1, 0], beats=0.75)
THEME_WOLVES.notes, THEME_WOLVES.durations = _phrase(
    [0, 0, 1, 0, None, 0, 1, 2, 1, 0], beats=0.25)

# ---- 片尾主题（致敬《雨后清风有香》气质的程序化民谣；非原曲）----
THEME_CREDITS = MusicPattern(
    name='雨后清风', notes=[], durations=[],
    bpm=64, loop=True, osc_type=OscType.SINE, volume=0.20,
    env_shape=EnvShape.PAD, vibrato_rate=4.0, vibrato_depth=0.10,
    harmonics=[(2.0, 0.20), (3.0, 0.08)],
)
THEME_CREDITS.notes, THEME_CREDITS.durations = _phrase(
    [0, None, 2, None, 4, None, 3, 2, None, 1, None, 0, None, None], beats=0.9)

THEMES = {'migration': THEME_MIGRATION, 'friend': THEME_FRIEND,
          'wolves': THEME_WOLVES, 'credits': THEME_CREDITS}


def render_theme(name, out_path, duration_sec=30.0):
    """渲染主题 WAV（确定性：旋律/包络全静态，无随机源）。"""
    pattern = THEMES[name]
    return generate_music_wav(pattern, out_path, duration_sec=duration_sec)


def render_all(out_dir, duration_sec=30.0):
    """渲染全部主题，返回 {name: path}。"""
    os.makedirs(out_dir, exist_ok=True)
    out = {}
    for name in THEMES:
        p = os.path.join(out_dir, f'ost_{name}.wav')
        render_theme(name, p, duration_sec)
        out[name] = p
    return out


if __name__ == '__main__':
    paths = render_all('output/ost')
    for k, v in paths.items():
        print(k, v, os.path.getsize(v))
