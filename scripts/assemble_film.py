# -*- coding: utf-8 -*-
"""全片装配：逐幕混音（OST 组曲 + CC0 拟音 + 镜头拟音）-> mux -> 八幕 concat。

用法（render_all.py 全部完成后）::

    python scripts/assemble_film.py            # 混音 + mux + concat + 验收
    python scripts/assemble_film.py --no-mix   # 跳过混音（复用已有 actN_audio.wav）

混音口径：
- 各轨 numpy 相加（非 ffmpeg amix，可逐样本控增益 + 峰值校验）；
- 采样率统一 44.1k mono（scipy resample_poly，scipy 已在依赖里）；
- 峰值硬校验：混完 > 0.98 即报错退出（不静默削波）；
- 每幕音轨精确对齐幕时长（pad/trim 到帧精确样本数）。

依赖：NIULAI_FFMPEG；output/final/act0..act7_1080.mp4（render_all 产物）；
output/ost/ 全套资产（make_audio.py 产物）。
"""
import argparse
import os
import subprocess
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FF = os.environ.get('NIULAI_FFMPEG', 'ffmpeg')
OUT = os.path.join(ROOT, 'output')
FINAL = os.path.join(OUT, 'final')
MIXED = os.path.join(OUT, 'mixed')
OST = os.path.join(OUT, 'ost')
SR = 44100

GAIN_OST, GAIN_SPOTS, GAIN_FOLEY = 0.62, 0.45, 0.55

# 幕 -> (时长秒, [(wav 相对 output/ost/, 增益)])  —— 单一事实来源与 ACTS 对齐
RECIPES = {
    'act0': (360.0, [('prologue_ambient.wav', GAIN_FOLEY)]),
    'act1': (300.0, [('foley_dawn.wav', GAIN_FOLEY)]),
    'act2': (720.0, [('suite_migration_720.wav', GAIN_OST),
                     ('spots_act2_migration.wav', GAIN_SPOTS)]),
    'act3': (720.0, [('suite_friend_720.wav', GAIN_OST),
                     ('spots_act3_leopard.wav', GAIN_SPOTS)]),
    'act4': (1080.0, [('suite_wolves_1080.wav', GAIN_OST),
                      ('spots_act4_wolves.wav', GAIN_SPOTS)]),
    'act5': (900.0, [('suite_friend_900.wav', GAIN_OST),
                     ('spots_act5_finale.wav', GAIN_SPOTS)]),
    'act6': (720.0, [('suite_credits_720.wav', GAIN_OST),
                     ('foley_reprise.wav', GAIN_FOLEY),
                     ('spots_act6_wake.wav', GAIN_SPOTS)]),
    'act7': (360.0, [('suite_credits_360.wav', GAIN_OST)]),
}


def run(cmd):
    p = subprocess.run([str(c) for c in cmd], cwd=ROOT,
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f'cmd failed: {" ".join(str(c) for c in cmd)[:160]}\n'
                           f'{p.stderr[-800:]}')
    return p


def load_wav(path):
    """WAV -> (sr, float64 mono)。多声道取均值。"""
    with wave.open(path, 'rb') as w:
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32767.0
    if w.getnchannels() > 1:
        data = data.reshape(-1, w.getnchannels()).mean(axis=1)
    return sr, data


def resample_to(data, sr, target=SR):
    if sr == target:
        return data
    from scipy.signal import resample_poly
    g = _gcd(sr, target)
    return resample_poly(data, target // g, sr // g)


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def mix_act(act, dur, tracks):
    """多轨相加 -> 精确幕长 -> 峰值校验 -> 写 WAV。"""
    os.makedirs(MIXED, exist_ok=True)
    n_target = int(round(dur * SR))
    buf = np.zeros(n_target, dtype=np.float64)
    for rel, gain in tracks:
        path = os.path.join(OST, rel)
        if not os.path.isfile(path):
            raise FileNotFoundError(f'missing audio asset: {path}')
        sr, data = load_wav(path)
        data = resample_to(data, sr)[:n_target]
        buf[:len(data)] += data * gain
    peak = float(np.abs(buf).max()) if len(buf) else 0.0
    if peak > 0.98:
        raise RuntimeError(f'{act} mix peak {peak:.3f} > 0.98 — 调低增益重混')
    print(f'  {act}: {len(tracks)} 轨  peak={peak:.3f}  '
          f'{n_target / SR:.2f}s', flush=True)
    out = os.path.join(MIXED, f'{act}_audio.wav')
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((buf * 32767.0).astype(np.int16).tobytes())
    return out


def mux_audio(video, audio, out):
    run([FF, '-y', '-i', video, '-i', audio,
         '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-shortest', out])
    return out


def concat_films(parts, out):
    lst = os.path.join(MIXED, '_film.txt')
    with open(lst, 'w', encoding='utf-8') as f:
        for p in parts:
            f.write(f"file '{p}'\n")
    run([FF, '-y', '-f', 'concat', '-safe', '0', '-i', lst,
         '-c', 'copy', '-movflags', '+faststart', out])
    return out


def probe(path):
    p = subprocess.run([FF, '-i', path], capture_output=True, text=True)
    info = {'duration': None, 'video': None, 'audio': None}
    for line in p.stderr.splitlines():
        if 'Duration:' in line:
            info['duration'] = line.split('Duration:')[1].split(',')[0].strip()
        if 'Video:' in line and info['video'] is None:
            info['video'] = line.strip()[:110]
        if 'Audio:' in line and info['audio'] is None:
            info['audio'] = line.strip()[:110]
    return info


def main():
    ap = argparse.ArgumentParser(prog='assemble_film')
    ap.add_argument('--no-mix', action='store_true')
    ap.add_argument('--out', default=os.path.join(
        OUT, '牛来_86分钟_全片_1080p.mp4'))
    args = ap.parse_args()

    os.makedirs(MIXED, exist_ok=True)
    parts = []
    for idx in [f'act{i}' for i in range(8)]:
        dur, tracks = RECIPES[idx]
        video = os.path.join(FINAL, f'{idx}_1080.mp4')
        if not os.path.isfile(video):
            raise FileNotFoundError(f'missing act video: {video}')
        wav = os.path.join(MIXED, f'{idx}_audio.wav')
        if not args.no_mix or not os.path.isfile(wav):
            print(f'[assemble] mix {idx}:', flush=True)
            wav = mix_act(idx, dur, tracks)
        muxed = os.path.join(MIXED, f'{idx}_muxed.mp4')
        mux_audio(video, wav, muxed)
        parts.append(muxed)

    print('[assemble] concat 八幕 ->', flush=True)
    film = concat_films(parts, args.out)
    mb = os.path.getsize(film) / 1048576.0
    info = probe(film)
    print(f'[assemble] OK {film}  ({mb:.0f} MB)', flush=True)
    print(f"  duration: {info['duration']}")
    print(f"  {info['video']}")
    print(f"  {info['audio']}")

    # 验收：总时长必须 86:00 级（±1s）
    d = info['duration'] or ''
    if d:
        h, m, s = (float(x) for x in d.split(':'))
        total = h * 3600 + m * 60 + s
        if abs(total - 5160.0) > 1.0:
            print(f'[assemble] FAIL: total {total:.2f}s != 5160s ±1')
            return 1
        print(f'[assemble] VERIFY OK: {total:.2f}s (target 5160.00s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
