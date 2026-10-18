# -*- coding: utf-8 -*-
"""OST 程序化变奏（P3-3a）：消除 180s 循环的重复感。

原状：三主题各是一条 180s 循环 WAV，18 分钟的 act4 要把它播 6 遍，重复感明显。

做法：从主题**派生变体族**——每条变体都是主题的合法变形（调式移位 / 倒影 /
逆行 / 节奏加密稀疏 / 八度移位 / 配器增减 / 留白），气质不变、听感不同；
再把变体按确定性顺序拼接（段间交叉淡化）铺满整幕。

两条铁律：
1. **纯函数 + 固定 seed**：`variation_pattern(theme, i)` 是 i 的纯函数，
   `stitch(..., seed)` 用 seeded Random，同输入必得同输出——现有确定性体系
   （tests/test_determinism.py）不会被破坏；
2. **零新依赖、零 GPU**：只是换音符序列与配器参数，渲染仍走 allin_engine
   的 generate_music_wav。

为什么不用生成式配乐（ACE-Step 等）：那需要 GPU，且会引入非确定性。
程序化变奏是这个工程"可复现、可审计"定位的正解；生成式留在 P3-3b 作为可选。
"""
import os
import random
import wave

import numpy as np

from .. import MASTER_SEED
from .ost import PENTA, THEMES, _phrase

N_VARIATIONS = 8          # 变体族大小（op 槽位数）
DEFAULT_SEG_SEC = 30.0    # 每个变体段的时长
DEFAULT_CROSSFADE = 1.5   # 段间交叉淡化（秒），避免拼接爆音


def _parse_degree(note):
    """'C4' / 'A5' -> 音级（可超出 0-4，跨八度）；None -> None。"""
    if note is None:
        return None
    name, oct_ = note[:-1], int(note[-1])
    if name not in PENTA:
        return None
    return PENTA.index(name) + (oct_ - 4) * 5


def variation_pattern(theme, index):
    """主题 -> 第 index 个变体的 MusicPattern（**纯函数**：同 index 必同结果）。

    手法按 index % 8 取用，参数完全由 index 决定（无随机源、无墙钟）：
      0 原型（族锚点，保证有可辨认的主题回归）
      1 调式移位 +2（明亮化）        2 节奏加密 + 高八度
      3 倒影 + 稀疏                  4 逆行 + 配器加厚
      5 低八度 + 减谐波（变薄）      6 移位 +1 且加密（紧张化）
      7 隔句留白（呼吸感）
    """
    from allin_engine.audio.music_gen import MusicPattern

    degs = [_parse_degree(n) for n in theme.notes]
    durs = list(theme.durations)
    beats = durs[0] if durs else 0.5
    octave = 0
    harm = list(getattr(theme, 'harmonics', None) or [])
    vib_r = getattr(theme, 'vibrato_rate', 0.0) or 0.0
    vib_d = getattr(theme, 'vibrato_depth', 0.0) or 0.0
    osc = theme.osc_type

    op = int(index) % N_VARIATIONS
    if op == 1:
        degs = [(d + 2) if d is not None else None for d in degs]
    elif op == 2:
        beats *= 0.75
        octave = 1
    elif op == 3:
        degs = [(4 - d) if d is not None else None for d in degs]
        beats *= 1.25
    elif op == 4:
        degs = list(reversed(degs))
        if not any(h[0] == 4.0 for h in harm):
            harm = harm + [(4.0, 0.08)]
    elif op == 5:
        octave = -1
        harm = [h for h in harm if h[0] <= 2.0]
    elif op == 6:
        degs = [(d + 1) if d is not None else None for d in degs]
        beats *= 0.75
        vib_d += 0.05
    elif op == 7:
        # 每 4 个音掐掉第 4 个 -> 留白；全休止的极端情况要兜住
        degs = [d if (i % 4 != 3) else None for i, d in enumerate(degs)]
        if all(d is None for d in degs):
            degs = [_parse_degree(n) for n in theme.notes]

    notes, durations = _phrase(degs, octave=octave, beats=beats)
    # 注意：allin_engine 内部对 vibrato_* 直接做 `> 0` 比较、对 harmonics 直接
    # 迭代，两者都**不能传 None**（实测 TypeError: '>' not supported between
    # NoneType and int）。故一律给 float / list 的零值，不给 None。
    return MusicPattern(
        name=f'{theme.name}·变奏{index}',
        notes=notes, durations=durations,
        bpm=theme.bpm, loop=theme.loop, osc_type=osc, volume=theme.volume,
        env_shape=theme.env_shape, harmonics=harm,
        vibrato_rate=float(vib_r), vibrato_depth=float(vib_d),
    )


def variation_notes(theme, index):
    """（测试友好）变体的 (notes, durations) 快照，不触发渲染。"""
    p = variation_pattern(theme, index)
    return tuple(p.notes), tuple(p.durations)


def render_variations(name, out_dir, n=N_VARIATIONS, seg_sec=DEFAULT_SEG_SEC,
                      target_peak=0.5):
    """渲染主题的前 n 个变体，返回 [path, ...]（确定性）。"""
    from allin_engine.audio.music_gen import generate_music_wav

    os.makedirs(out_dir, exist_ok=True)
    theme = THEMES[name]
    out = []
    for i in range(n):
        pat = variation_pattern(theme, i)
        p = os.path.join(out_dir, f'ost_{name}_var{i:02d}.wav')
        generate_music_wav(pat, p, duration_sec=seg_sec)
        out.append(_normalize(p, target_peak))
    return out


def _load(path):
    with wave.open(path, 'rb') as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        raw = np.frombuffer(w.readframes(n), dtype=np.int16)
    data = raw.astype(np.float64) / 32768.0
    if ch > 1:                      # 混音统一按单声道处理
        data = data.reshape(-1, ch).mean(axis=1)
    return sr, data


def _save(path, sr, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or '.', exist_ok=True)
    pcm = (np.clip(data, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def _normalize(path, target_peak):
    """原地峰值归一化（generate_music_wav 输出接近满幅，混音前必须压）。"""
    sr, data = _load(path)
    peak = float(np.abs(data).max())
    if peak > 1e-9:
        data = data * (target_peak / peak)
    return _save(path, sr, data)


def _segment_order(n_variations, total_sec, seg_sec, seed=MASTER_SEED):
    """变体的播放顺序：多轮确定性洗牌。

    每轮把全部变体洗一遍再接上——轮内不重复、轮间顺序不同，
    把"每 seg_sec 就重来"的重复周期打散成 n_variations * seg_sec。
    """
    need = int(np.ceil(total_sec / float(seg_sec))) + 1
    rnd = random.Random(seed)
    order = []
    while len(order) < need:
        batch = list(range(n_variations))
        rnd.shuffle(batch)
        order.extend(batch)
    return order[:need]


def stitch(wavs, out_path, total_sec, crossfade=DEFAULT_CROSSFADE,
           seed=MASTER_SEED, target_peak=0.5):
    """把变体段拼接铺满 total_sec（段间交叉淡化，不留爆音）。

    确定性：顺序由 (seed, 段数) 唯一决定，无随机源泄漏。
    """
    if not wavs:
        raise ValueError('no variation wavs to stitch')
    segs = []
    sr0 = None
    for p in wavs:
        sr, d = _load(p)
        sr0 = sr0 or sr
        if sr != sr0:               # 采样率不一致就按第一个线性重采样
            n_new = int(round(len(d) * sr0 / float(sr)))
            d = np.interp(np.linspace(0, len(d) - 1, n_new),
                          np.arange(len(d)), d)
        segs.append(d)
    cf = int(crossfade * sr0)
    total = int(round(total_sec * sr0))
    buf = np.zeros(total + cf, dtype=np.float64)
    seg_sec = len(segs[0]) / float(sr0)
    order = _segment_order(len(segs), total_sec, seg_sec, seed=seed)

    pos = 0
    for idx in order:
        if pos >= total:
            break
        seg = segs[idx]
        n_cf = min(cf, len(seg) // 2)
        fade = np.ones(len(seg), dtype=np.float64)
        if n_cf > 0:
            ramp = np.linspace(0.0, 1.0, n_cf)
            fade[:n_cf] = ramp
            fade[-n_cf:] = ramp[::-1]
        end = min(pos + len(seg), len(buf))
        buf[pos:end] += seg[:end - pos] * fade[:end - pos]
        pos += max(1, len(seg) - n_cf)

    buf = buf[:total]
    # 结尾淡出：最后一段通常是被截断的（loops 按整数遍算，段长不等），
    # 硬切会在片尾留一声"咔"。
    tail = min(int(0.25 * sr0), max(1, len(buf) // 4))
    if tail > 1:
        buf[-tail:] *= np.linspace(1.0, 0.0, tail)
    peak = float(np.abs(buf).max())
    if peak > 1e-9:
        buf = buf * (target_peak / peak)
    return _save(out_path, sr0, buf)


def render_suite_track(name, out_path, total_sec, n=N_VARIATIONS,
                       seg_sec=DEFAULT_SEG_SEC, crossfade=DEFAULT_CROSSFADE,
                       seed=MASTER_SEED, work_dir=None, target_peak=0.5):
    """一条龙：渲染变体族 -> 拼接铺满整幕。返回最终音轨路径。"""
    tmp_dir = work_dir or os.path.join(
        os.path.dirname(os.path.abspath(out_path)), '_vars')
    wavs = render_variations(name, tmp_dir, n=n, seg_sec=seg_sec,
                             target_peak=target_peak)
    return stitch(wavs, out_path, total_sec, crossfade=crossfade, seed=seed,
                  target_peak=target_peak)


def _main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(
        prog='niulai.audio.variations',
        description='渲染主题变奏族并拼接成整幕音轨（替代简单循环）')
    ap.add_argument('--theme', default='migration', choices=sorted(THEMES))
    ap.add_argument('--seconds', type=float, required=True,
                    help='目标音轨时长（秒），如 act4 = 1080')
    ap.add_argument('--out', required=True)
    ap.add_argument('--variations', type=int, default=N_VARIATIONS)
    ap.add_argument('--seg-sec', type=float, default=DEFAULT_SEG_SEC)
    ap.add_argument('--crossfade', type=float, default=DEFAULT_CROSSFADE)
    ap.add_argument('--seed', type=int, default=MASTER_SEED)
    ap.add_argument('--keep-vars', action='store_true',
                    help='保留中间变体 WAV（默认可删）')
    a = ap.parse_args(argv)
    work = os.path.join(os.path.dirname(os.path.abspath(a.out)), '_vars')
    p = render_suite_track(a.theme, a.out, a.seconds, n=a.variations,
                           seg_sec=a.seg_sec, crossfade=a.crossfade,
                           seed=a.seed, work_dir=work)
    print(f'[variations] {a.theme} x {a.variations} variations -> {p} '
          f'({os.path.getsize(p) / 1048576.0:.2f} MB, {a.seconds:.1f}s)')
    return 0


if __name__ == '__main__':
    raise SystemExit(_main())
