# -*- coding: utf-8 -*-
"""镜头级拟音（P3-4）：把音效从"幕级氛围"下沉到"镜头级"。

现状：`foley.py` 只做**幕级**氛围（序幕风声、清晨鸟鸣、片尾鸣唱窗），
一铺就是整幕；镜头内部的动作（蹄声、涉水、狼嚎、振翅）是空的。

本模块补上这一层，两条设计取舍：

1. **程序化合成，不引新素材**。foley 用的是真实 CC0 录音，但蹄声/涉水/狼嚎
   没有现成的公版素材可拿；新增素材要过许可记账。而本工程本来就是
   "程序化场景/角色/配乐 · 零外部素材"——用 numpy 合成点音效（低频 thump +
   噪声瞬态 / 带通噪声 / 扫频嚎叫）与该定位一致，且**零许可风险**。
   真实录音氛围层继续由 foley.py 负责，两层叠加不冲突。

2. **镜头表是单一事实来源**。音效事件由 `scene.shots`（各幕自带 t0/t1/note）
   经关键词规则派生，不另立一份时间码表——避免两处漂移（全哥铁律：单一事实来源）。

确定性：所有随机来自 `np.random.default_rng(seed)`，同 seed 同输入必得同输出。
"""
import os
import wave

import numpy as np

from .. import MASTER_SEED

SR = 44100

# ---------------------------------------------------------------- 音效合成
# 每个合成器：f(rng, sr) -> float64 ndarray（已含包络，峰值约 1.0）


def _env_ar(n, sr, attack, release):
    """ attack/release 两段包络（秒）。"""
    t = np.arange(n) / float(sr)
    a = np.clip(t / max(attack, 1e-6), 0.0, 1.0)
    r = np.clip((n / float(sr) - t) / max(release, 1e-6), 0.0, 1.0)
    return np.minimum(a, r)


def _bp_noise(x, sr, lo_hz, hi_hz):
    """简易带通：一阶高通（差分）串联一阶低通（移动平均）。够用且不引依赖。"""
    y = np.diff(x, prepend=x[0])                     # 高通
    w = max(1, int(sr / max(hi_hz, 20.0)))           # 低通窗
    if w > 1:
        k = np.ones(w) / float(w)
        y = np.convolve(y, k, mode='same')
    return y


def syn_hoof(rng, sr=SR):
    """蹄声：低频 thump(~95Hz) + 极短噪声瞬态，约 0.12s。"""
    n = int(0.12 * sr)
    t = np.arange(n) / float(sr)
    thump = np.sin(2 * np.pi * 95.0 * t) * np.exp(-t * 45.0)
    click = rng.standard_normal(n) * np.exp(-t * 180.0) * 0.35
    return thump + click


def syn_water(rng, sr=SR):
    """涉水：带通噪声 burst，约 0.45s（起手瞬态 + 尾巴）。"""
    n = int(0.45 * sr)
    t = np.arange(n) / float(sr)
    noise = _bp_noise(rng.standard_normal(n), sr, 400.0, 6000.0)
    env = np.exp(-t * 6.0) * (1.0 - np.exp(-t * 120.0))
    return noise * env * 2.2


def syn_howl(rng, sr=SR):
    """狼嚎：先上后下的扫频 + 谐波 + 轻颤音，约 1.8s。"""
    n = int(1.8 * sr)
    t = np.arange(n) / float(sr)
    base = 380.0 + 260.0 * np.sin(np.pi * t / (n / float(sr)))
    vib = 1.0 + 0.012 * np.sin(2 * np.pi * 5.5 * t)
    phase = 2 * np.pi * np.cumsum(base * vib) / float(sr)
    sig = (np.sin(phase) + 0.30 * np.sin(2 * phase)
           + 0.12 * np.sin(3 * phase))
    env = _env_ar(n, sr, 0.25, 0.6)
    return sig * env * 0.55 + rng.standard_normal(n) * env * 0.03


def syn_growl(rng, sr=SR):
    """低吼：低频噪声 + 约 25Hz 调幅，约 0.9s。"""
    n = int(0.9 * sr)
    t = np.arange(n) / float(sr)
    noise = _bp_noise(rng.standard_normal(n), sr, 60.0, 900.0)
    am = 0.65 + 0.35 * np.sin(2 * np.pi * 25.0 * t)
    return noise * am * _env_ar(n, sr, 0.15, 0.35) * 2.6


def syn_strain(rng, sr=SR):
    """发力/站起：低频上扫 + 摩擦噪声，约 0.7s。"""
    n = int(0.7 * sr)
    t = np.arange(n) / float(sr)
    f = 60.0 + 90.0 * (t / (n / float(sr)))
    phase = 2 * np.pi * np.cumsum(f) / float(sr)
    env = _env_ar(n, sr, 0.08, 0.25)
    return (np.sin(phase) * 0.8 + rng.standard_normal(n) * 0.12) * env


def syn_wing(rng, sr=SR):
    """振翅：一串噪声脉冲（5 下，间隔约 0.11s）。"""
    seg = int(0.11 * sr)
    out = np.zeros(seg * 5, dtype=np.float64)
    for i in range(5):
        a, b = i * seg, (i + 1) * seg
        t = np.arange(seg) / float(sr)
        out[a:b] = (rng.standard_normal(seg)
                    * np.exp(-t * 55.0)
                    * (1.0 if i % 2 == 0 else 0.75))
    return _bp_noise(out, sr, 300.0, 5000.0) * 1.6


def syn_wind_gust(rng, sr=SR):
    """阵风：带通噪声 + 缓慢包络，约 2.5s。"""
    n = int(2.5 * sr)
    t = np.arange(n) / float(sr)
    noise = _bp_noise(rng.standard_normal(n), sr, 120.0, 1400.0)
    env = np.sin(np.pi * np.clip(t / (n / float(sr)), 0.0, 1.0)) ** 1.5
    return noise * env * 2.0


_RAW_SYNTHS = {
    'hoof': syn_hoof, 'water': syn_water, 'howl': syn_howl,
    'growl': syn_growl, 'strain': syn_strain, 'wing': syn_wing,
    'wind_gust': syn_wind_gust,
}

SPOT_PEAK = 0.9


def _normalized(fn, peak=SPOT_PEAK):
    """统一各音效的输出峰值。

    不归一的话各合成器峰值差 3 倍（实测 water 3.26 / wing 1.53 / hoof ~1.0），
    混音时水声会把其他音效全压住；归一后相对音量才由 SHOT_RULES 的 gain 说了算。
    """
    def _f(rng, sr=SR):
        seg = np.asarray(fn(rng, sr), dtype=np.float64)
        m = float(np.abs(seg).max())
        return seg * (peak / m) if m > 1e-9 else seg
    return _f


SYNTHS = {k: _normalized(f) for k, f in _RAW_SYNTHS.items()}

# 节奏型音效的重复间隔（秒）；None = 不重复
RHYTHM_INTERVAL = {'hoof': 0.55, 'water': 0.9, 'wing': 0.42}

# ---------------------------------------------------------------- 镜头 -> 音效


# (关键词, kind, 策略, 增益)。按顺序取**第一个**命中，顺序即优先级：
# 先具体动作（跃溪/过河），后泛化环境（沙漠/风）。
SHOT_RULES = (
    # 关键词要**精确**：'溪' 会误命中"河岸惧溪"——那场戏牛群在岸边不敢下水，
    # 应该是安静的。故只认"跃溪/过河"这类确实入水的动作。
    (('跃溪', '过河'), 'water', 'rhythm', 0.50),
    (('行军', '奔向', '集结', '全群', '牛群'), 'hoof', 'rhythm', 0.55),
    (('狼', '总攻', '初袭'), 'howl', 'sparse', 0.45),
    (('现身', '夜宿'), 'growl', 'sparse', 0.40),
    (('站起', '奋力', '长大'), 'strain', 'once', 0.60),
    (('高飞', '云雀', '伤翅'), 'wing', 'rhythm', 0.40),
    (('沙丘', '干渴', '沙漠'), 'wind_gust', 'sparse', 0.35),
)


def match_kind(note):
    """镜头名 -> (kind, strategy, gain) 或 None。**纯函数**。"""
    for keys, kind, strat, gain in SHOT_RULES:
        if any(k in note for k in keys):
            return kind, strat, gain
    return None


def shots_of(act_name, seed=MASTER_SEED):
    """取幕的镜头表 [(t0, t1, note)]（幕内秒）。单一事实来源 = scene.shots。"""
    from ..cli import SCENES
    if act_name not in SCENES:
        return []
    scene = SCENES[act_name](seed=seed, grid=32)
    return [(s.t0, s.t1, s.note) for s in getattr(scene, 'shots', ())]


def plan_shot_spots(act_name, seed=MASTER_SEED):
    """镜头表 -> 音效事件 [(t_local, kind, gain)]（幕内秒，按时间排序）。

    策略：
    - once   : 镜头中点一个
    - rhythm : 按固定间隔铺满（蹄声/涉水/振翅）
    - sparse : 确定性撒 2-4 个（嚎叫/低吼/阵风）
    """
    rng = np.random.default_rng(seed)
    events = []
    for t0, t1, note in shots_of(act_name, seed=seed):
        hit = match_kind(note)
        if hit is None:
            continue
        kind, strat, gain = hit
        span = max(0.0, t1 - t0)
        if strat == 'once':
            events.append((t0 + span * 0.5, kind, gain))
        elif strat == 'rhythm':
            # 等间隔会听成节拍器，故间隔加 ±15% 确定性抖动
            base = RHYTHM_INTERVAL.get(kind, 0.6)
            t = t0 + base * 0.5
            while t < t1:
                events.append((t, kind, gain))
                t += base * float(rng.uniform(0.85, 1.15))
        else:                                    # sparse：长镜头多撒几个
            k = int(np.clip(span / 45.0, 2, 8))
            for _ in range(k):
                frac = float(rng.uniform(0.12, 0.88))
                events.append((t0 + span * frac, kind, gain))
    return sorted(events)


def render_spot_track(events, duration, out_path, sr=SR, seed=MASTER_SEED,
                      target_peak=0.45):
    """事件表 -> 整幕音效轨 WAV（确定性）。"""
    rng = np.random.default_rng(seed)
    buf = np.zeros(int(round(duration * sr)), dtype=np.float64)
    n_placed = 0
    for t, kind, gain in events:
        fn = SYNTHS.get(kind)
        if fn is None:
            continue
        seg = np.asarray(fn(rng, sr), dtype=np.float64)
        if seg.size == 0:
            continue
        start = int(t * sr)
        end = min(len(buf), start + seg.size)
        if start >= len(buf) or start < 0:
            continue
        # 每个点也做音量抖动，避免同一音效重复出现时听出"复制粘贴"
        buf[start:end] += seg[:end - start] * gain * float(
            rng.uniform(0.75, 1.0))
        n_placed += 1
    peak = float(np.abs(buf).max())
    if peak > 1e-9:
        buf = buf * (target_peak / peak)
    pcm = (np.clip(buf, -1.0, 1.0) * 32767.0).astype(np.int16)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or '.',
                exist_ok=True)
    with wave.open(out_path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return out_path, n_placed


def render_act_spots(act_name, duration, out_path, sr=SR, seed=MASTER_SEED,
                     target_peak=0.45):
    """一条龙：镜头表 -> 事件 -> 整幕音效轨。"""
    events = plan_shot_spots(act_name, seed=seed)
    return render_spot_track(events, duration, out_path, sr=sr, seed=seed,
                             target_peak=target_peak), len(events)


def _main(argv=None):
    import argparse

    from ..timeline import ACTS
    ap = argparse.ArgumentParser(
        prog='niulai.audio.spots',
        description='镜头级拟音：从 scene.shots 派生音效事件并渲染成轨')
    ap.add_argument('--act', required=True)
    ap.add_argument('--out', default=None)
    ap.add_argument('--seed', type=int, default=MASTER_SEED)
    ap.add_argument('--dry-run', action='store_true',
                    help='只打印事件表，不渲染')
    a = ap.parse_args(argv)
    events = plan_shot_spots(a.act, seed=a.seed)
    dur = None
    for name, t0, t1, _ in ACTS:
        if name == a.act:
            dur = t1 - t0
    print(f'[spots] {a.act}: {len(events)} events '
          f'(duration {dur}s)')
    for t, kind, gain in events[:40]:
        print(f'  {t:8.2f}s  {kind:9s} gain={gain}')
    if len(events) > 40:
        print(f'  ... {len(events) - 40} more')
    if a.dry_run or not events:
        return 0
    out = a.out or os.path.join('output', 'ost', f'spots_{a.act}.wav')
    path, n = render_spot_track(events, dur, out, seed=a.seed)
    print(f'[spots] -> {path} ({n} spots, '
          f'{os.path.getsize(path) / 1048576.0:.2f} MB)')
    return 0


if __name__ == '__main__':
    raise SystemExit(_main())
