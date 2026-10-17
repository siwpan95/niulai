# -*- coding: utf-8 -*-
"""程序化氛围音效（foley）：风 + 云雀啼鸣 —— 序幕/清晨/高飞复用的声景。

全片唯一没有声音的是序幕（6 分钟纯静音，导演指出的疏漏）。原片开场是
荒漠风 + 云雀鸣唱。本模块用 numpy 确定性合成（固定种子，可复现）：

- 风声：棕噪声 → 一阶低通 → 阵风包络（多正弦慢调制）；
- 云雀鸣唱：上行扫频短音（2.4→4.8kHz 指数调频）成短语，
  短语按确定性调度散布（或限定在时间窗内 —— 第六幕高飞呼应用）。
"""
import os
import wave

import numpy as np

SR = 44100
TAU = 2.0 * np.pi


# ---------------------------------------------------------------- 风 --
def render_wind(duration, sr=SR, seed=7, level=0.5):
    """棕噪声低通风。level=随时间衰减的函数 t->[0,1]（可选）。"""
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    brown = np.cumsum(rng.standard_normal(n))
    brown = brown / (np.abs(brown).max() + 1e-9)
    # 一阶低通（IIR 在 numpy 里用 lfilter 等价式：scipy 可选，避免依赖用朴素递推）
    a = 0.012
    lp = np.empty(n, dtype=np.float64)
    acc = 0.0
    for i in range(n):
        acc += a * (brown[i] - acc)
        lp[i] = acc
    t = np.arange(n) / float(sr)
    # 阵风：三个慢正弦调制（确定性相位）
    gust = 0.55 + 0.25 * np.sin(TAU * 0.05 * t) + \
        0.12 * np.sin(TAU * 0.11 * t + 1.3) + \
        0.08 * np.sin(TAU * 0.19 * t + 2.1)
    env = gust if not callable(level) else gust * \
        np.array([level(ti) for ti in t])
    return lp * env * 0.55


# ------------------------------------------------------------ 云雀啼鸣 --
def _chirp(sr, f0, f1, dur):
    """上行扫频短音（指数调频 + 菱形包络）。"""
    n = int(dur * sr)
    t = np.arange(n) / float(sr)
    k = np.log(f1 / f0) / dur
    phase = TAU * f0 / k * (np.exp(k * t) - 1.0)
    env = np.minimum(t / (dur * 0.15), (dur - t) / (dur * 0.15) + 0.0)
    env = np.clip(env, 0.0, 1.0)
    return np.sin(phase) * env * 0.5


def skylark_phrase(sr=SR, seed=11):
    """一个鸣唱短语：4-7 个上行短音（2.4-4.8kHz），确定性。"""
    rng = np.random.default_rng(seed)
    n_chirps = int(rng.integers(4, 8))
    out = []
    t = 0.0
    for i in range(n_chirps):
        f0 = 2400.0 + rng.uniform(0, 600)
        f1 = f0 + 1800.0 + rng.uniform(0, 900)
        dur = 0.12 + rng.uniform(0, 0.13)
        c = _chirp(sr, f0, f1, dur)
        out.append(np.concatenate([np.zeros(int(t * sr)), c]))
        t += dur + 0.04 + rng.uniform(0, 0.06)
    length = max(len(x) for x in out)
    buf = np.zeros(length)
    for x in out:
        buf[:len(x)] += x
    return buf * 0.8


def render_skylark_song(duration, sr=SR, seed=5, window=None):
    """鸣唱调度：短语散布全程（window=(t0,t1) 时只在窗内鸣唱）。"""
    rng = np.random.default_rng(seed)
    buf = np.zeros(int(duration * sr))
    t = 2.0 + rng.uniform(0, 2.0)
    while t < duration:
        in_win = window is None or (window[0] <= t < window[1])
        if in_win:
            ph = skylark_phrase(sr, seed=int(seed * 97 + t * 13))
            start = int(t * sr)
            end = min(len(buf), start + len(ph))
            if start < len(buf):
                buf[start:end] += ph[:end - start]
        t += 3.0 + rng.uniform(0, 5.0)
    return np.clip(buf, -1.0, 1.0) * 0.35


# ---------------------------------------------------------------- 声景 --
def _write(path, data, sr=SR):
    pcm = (np.clip(data, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def render_prologue_ambient(duration, out_path, sr=SR):
    """序幕声景：高空风（随时间略降）+ 全程鸣唱（尾 30 秒静下来）。"""
    t_end = duration
    wind = render_wind(duration, sr, seed=7,
                       level=lambda t: 1.0 - 0.35 * min(1.0, t / t_end))
    song = render_skylark_song(duration, sr, seed=5, window=(0.0, t_end - 25.0))
    data = (wind * 1.25 + song * 1.25)          # 高空风更响、鸣唱更亮
    return _write(out_path, data, sr)


def render_dawn_ambient(duration, out_path, sr=SR):
    """清晨（act1）轻氛围：微风 + 稀疏鸣唱（音量减半，垫在对白下）。"""
    wind = render_wind(duration, sr, seed=21, level=0.5)
    song = render_skylark_song(duration, sr, seed=33) * 0.5
    return _write(out_path, (wind * 0.6 + song) * 0.6, sr)


def render_song_reprise(duration, out_path, window, sr=SR):
    """鸣唱呼应（act6 高飞窗 420-560s）：窗外静音、窗内鸣唱。"""
    song = render_skylark_song(duration, sr, seed=19, window=window)
    return _write(out_path, song * 1.6, sr)


if __name__ == '__main__':
    os.makedirs('output/ost', exist_ok=True)
    for fn in (render_prologue_ambient, render_dawn_ambient):
        p = fn(30.0, f'output/ost/_probe_{fn.__name__}.wav')
        with wave.open(p, 'rb') as w:
            d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        print(f'{fn.__name__}: peak={np.abs(d).max()} '
              f'rms={np.sqrt((d.astype(np.float64) ** 2).mean()):.1f} '
              f'size={os.path.getsize(p)}')
