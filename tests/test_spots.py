# -*- coding: utf-8 -*-
"""镜头级拟音测试（P3-4）。

重点钉住两件事：
1. **规则精确性**——"河岸惧溪"不能铺水声（那场戏牛群在岸边不敢下水），
   这是先撞出来再收窄的回归点；
2. **确定性**——事件表与渲染结果都必须只依赖 seed。

运行：python tests/test_spots.py [--no-render]
"""
import argparse
import hashlib
import os
import sys
import tempfile
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from niulai import MASTER_SEED  # noqa: E402
from niulai.audio import spots  # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    status = 'ok' if cond else 'FAIL'
    print(f'  {status}: {name}' + (f'  [{detail}]' if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def md5_file(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def test_match_kind():
    print('test_match_kind')
    cases = [
        ('蛇逼跃溪', 'water'),
        ('全群过河', 'water'),
        ('沙漠行军', 'hoof'),
        ('奔向牛群', 'hoof'),
        ('集结', 'hoof'),
        ('狼群现身', 'howl'),
        ('狼群初袭', 'howl'),
        ('总攻', 'howl'),
        ('夜宿', 'growl'),
        ('奋力站起', 'strain'),
        ('云雀高飞', 'wing'),
        ('近景：云玎伤翅', 'wing'),
        ('干渴', 'wind_gust'),
        ('沙丘剪影', 'wind_gust'),
    ]
    for note, expect in cases:
        hit = spots.match_kind(note)
        got = hit[0] if hit else None
        check(f'{note} -> {expect}', got == expect, f'got {got}')
    # 不该命中的（安静戏、纯对白戏）
    for note in ('河岸惧溪', '全景：妈妈与牛来', '妈妈离去，梦境过渡',
                 '初遇', '分奶', '约法三章', '团圆大全景'):
        check(f'{note} -> 无音效', spots.match_kind(note) is None,
              f'got {spots.match_kind(note)}')
    # 水声规则优先于蹄声（过河时是水声，不是蹄声）
    check('过河优先 water 而非 hoof',
          spots.match_kind('全群过河')[0] == 'water')


def test_synths():
    print('test_synths')
    rng = np.random.default_rng(MASTER_SEED)
    for kind, fn in spots.SYNTHS.items():
        seg = np.asarray(fn(rng, 22050), dtype=np.float64)
        check(f'{kind} 非空', seg.size > 0)
        check(f'{kind} 有限值', bool(np.all(np.isfinite(seg))))
        check(f'{kind} 有声音（峰值>0.05）', float(np.abs(seg).max()) > 0.05,
              f'{float(np.abs(seg).max()):.3f}')
        check(f'{kind} 不过载（峰值<=1.5）', float(np.abs(seg).max()) <= 1.5,
              f'{float(np.abs(seg).max()):.3f}')
    # 确定性：同 seed 必须逐样本相同
    a = np.asarray(spots.syn_hoof(np.random.default_rng(7), 22050))
    b = np.asarray(spots.syn_hoof(np.random.default_rng(7), 22050))
    check('同 seed 合成逐样本相同', np.array_equal(a, b))
    c = np.asarray(spots.syn_hoof(np.random.default_rng(8), 22050))
    check('换 seed 合成不同', not np.array_equal(a, c))


def test_plan_events(do_plan=True):
    print('test_plan_events')
    if not do_plan:
        print('  skip: --no-render')
        return
    act = 'act2_migration'
    shots = spots.shots_of(act, seed=MASTER_SEED)
    check('act2 有镜头表', len(shots) > 0, f'{len(shots)}')
    ev = spots.plan_shot_spots(act, seed=MASTER_SEED)
    check('派生出事件', len(ev) > 0, f'{len(ev)}')
    check('事件按时间有序', all(ev[i][0] <= ev[i + 1][0]
                                for i in range(len(ev) - 1)))
    # 每个事件必须落在某个镜头区间内（不能飘到镜头外）
    outside = [e for e in ev
               if not any(s0 <= e[0] < s1 for s0, s1, _ in shots)]
    check('事件都落在镜头区间内', not outside,
          f'{outside[:3]}')
    # 惧溪镜头内不得有水声（先撞出来的回归点）
    fear = [(s0, s1) for s0, s1, n in shots if '惧溪' in n]
    if fear:
        s0, s1 = fear[0]
        wet = [e for e in ev if e[1] == 'water' and s0 <= e[0] < s1]
        check('惧溪镜头内无水声', not wet, f'{wet[:3]}')
    # 确定性
    ev2 = spots.plan_shot_spots(act, seed=MASTER_SEED)
    check('同 seed 事件表一致', ev == ev2)
    ev3 = spots.plan_shot_spots(act, seed=MASTER_SEED + 1)
    check('换 seed 事件表不同', ev != ev3)


def test_render_track():
    print('test_render_track')
    tmp = tempfile.mkdtemp(prefix='niulai_spots_')
    dur = 8.0
    events = [(0.5, 'hoof', 0.55), (1.5, 'water', 0.5), (3.0, 'howl', 0.45),
              (6.0, 'strain', 0.6), (7.5, 'wing', 0.4)]
    out = os.path.join(tmp, 'spots.wav')
    path, n = spots.render_spot_track(events, dur, out, seed=MASTER_SEED)
    check('放置数 == 事件数', n == len(events), f'{n}')
    with wave.open(path, 'rb') as w:
        sr = w.getframerate()
        frames = w.getnframes()
    check('时长正确', abs(frames / float(sr) - dur) < 0.02,
          f'{frames / float(sr):.3f}s')
    _, d = _load(path)
    check('峰值归一化到 0.45',
          abs(float(np.abs(d).max()) - 0.45) < 0.02,
          f'{float(np.abs(d).max()):.3f}')
    check('非全零', float(np.abs(d).max()) > 0.1)
    # 越界事件不崩（超出轨长的直接丢弃）
    out2 = os.path.join(tmp, 'spots_overflow.wav')
    p2, n2 = spots.render_spot_track([(7.9, 'howl', 0.5)], dur, out2,
                                     seed=MASTER_SEED)
    check('越界事件不崩', os.path.isfile(p2))
    # 确定性
    out3 = os.path.join(tmp, 'spots2.wav')
    spots.render_spot_track(events, dur, out3, seed=MASTER_SEED)
    check('同 seed 渲染逐字节相同', md5_file(out) == md5_file(out3))
    out4 = os.path.join(tmp, 'spots3.wav')
    spots.render_spot_track(events, dur, out4, seed=MASTER_SEED + 3)
    check('换 seed 渲染结果不同', md5_file(out) != md5_file(out4))


def _load(path):
    with wave.open(path, 'rb') as w:
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return sr, data.astype(np.float64) / 32768.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-render', action='store_true',
                    help='skip plan_shot_spots (needs scene construction)')
    args = ap.parse_args()
    test_match_kind()
    test_synths()
    test_plan_events(do_plan=not args.no_render)
    test_render_track()
    if FAILED:
        print(f'\nFAILED {len(FAILED)}: {FAILED}')
        return 1
    print('\nALL_SPOT_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
