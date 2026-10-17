# -*- coding: utf-8 -*-
"""氛围音效：**真实公版录音**（CC0 1.0）+ 交叉淡化无缝循环 + 包络。

素材（assets/sounds/，来源与许可见 SOUNDS.md）：
- 晨间鸟鸣 2:10（kvgarlic，Freesound #156826，CC0 1.0）
- 原野风声 0:15（felix.blume，Freesound #217506，CC0 1.0）

循环方法（lull 仓库 prep-audio 同款思路）：
- 交叉淡化 1.5s：junction = 尾*(1-r) + 头*r，无缝单元 = junction ++ 中段，
  拼接 N 次无接缝；
- 包络（风声随降落渐弱 / 鸣唱窗淡入淡出）为确定性 numpy 运算。
"""
import os
import subprocess
import wave

import numpy as np

SR = 44100
XFADE = 1.5                       # 交叉淡化秒数
ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'assets', 'sounds')
FF = os.environ.get('NIULAI_FFMPEG', 'ffmpeg')

BIRDS_OGG = os.path.join(ASSET_DIR, 'birds_cc0_kvgarlic.ogg')
WIND_OGG = os.path.join(ASSET_DIR, 'wind_cc0_felixblume.ogg')


def _load(ogg, sr=SR):
    """ffmpeg 解码 OGG -> 44.1k float32 mono。"""
    proc = subprocess.run(
        [FF, '-y', '-v', 'error', '-i', ogg, '-ac', '1', '-ar', str(sr),
         '-f', 'f32le', '-'], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f'decode failed: {ogg}\n{proc.stderr[-500:]}')
    return np.frombuffer(proc.stdout, dtype=np.float32)


def _seamless(data, xf=XFADE, sr=SR):
    """交叉淡化无缝循环单元（尾部与头部重叠淡化）。"""
    n = int(xf * sr)
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float64)
    junction = data[-n:] * (1.0 - ramp) + data[:n] * ramp
    return np.concatenate([junction, data[n:-n]])


def _tile(unit, duration, sr=SR):
    reps = int(duration * sr) // len(unit) + 1
    return np.tile(unit, reps)[:int(duration * sr)]


def _fade_edges(data, fade_in, fade_out, sr=SR):
    out = data.copy()
    n_in = min(int(fade_in * sr), len(out))
    n_out = min(int(fade_out * sr), len(out))
    if n_in:
        out[:n_in] *= np.linspace(0.0, 1.0, n_in)
    if n_out:
        out[-n_out:] *= np.linspace(1.0, 0.0, n_out)
    return out


def _write(path, data, sr=SR):
    pcm = (np.clip(data, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def render_prologue_ambient(duration, out_path, sr=SR):
    """序幕声景：真实风（随降落渐弱）+ 真实鸟鸣（末 25 秒静下）。"""
    wind = _load(WIND_OGG)
    birds = _load(BIRDS_OGG)
    w = _tile(_seamless(wind), duration) * 0.9
    env = 1.0 - 0.35 * np.minimum(1.0, np.arange(len(w)) / (duration * sr))
    b = _tile(_seamless(birds), duration) * 0.5
    b = _fade_edges(b, 3.0, max(0.0, duration - 22.0))
    return _write(out_path, w * env + b, sr)


def render_dawn_ambient(duration, out_path, sr=SR):
    """清晨（act1）轻氛围：微风 + 鸟鸣（低音量垫对白下）。"""
    wind = _tile(_seamless(_load(WIND_OGG)), duration) * 0.45
    birds = _tile(_seamless(_load(BIRDS_OGG)), duration) * 0.28
    birds = _fade_edges(birds, 4.0, 4.0)
    return _write(out_path, (wind + birds) * 0.8, sr)


def render_song_reprise(duration, out_path, window, sr=SR):
    """鸣唱呼应（act6 高飞窗）：窗外静音、窗内真实鸟鸣淡入淡出。"""
    birds = _tile(_seamless(_load(BIRDS_OGG)), duration) * 0.85
    buf = np.zeros(len(birds), dtype=np.float64)
    n0, n1 = min(int(window[0] * sr), len(buf)), min(int(window[1] * sr),
                                                     len(buf))
    buf[n0:n1] = birds[n0:n1]
    fade = int(4.0 * sr)
    buf[n0:n0 + fade] *= np.linspace(0.0, 1.0, fade)
    buf[n1 - fade:n1] *= np.linspace(1.0, 0.0, fade)
    return _write(out_path, buf, sr)


if __name__ == '__main__':
    os.makedirs('output/ost', exist_ok=True)
    p = render_prologue_ambient(30.0, 'output/ost/_probe_real.wav')
    with wave.open(p, 'rb') as w:
        d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    print(f'real foley probe: peak={np.abs(d).max()} '
          f'rms={np.sqrt((d.astype(np.float64) ** 2).mean()):.1f} '
          f'size={os.path.getsize(p)}')
