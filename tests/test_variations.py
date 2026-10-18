# -*- coding: utf-8 -*-
"""OST 程序化变奏测试（P3-3a）。

钉住三件事：
1. **纯函数性**：同 index 两次派生必须完全相同（否则确定性体系崩了）；
2. **真的不同**：8 个变体两两不同，否则等于没变奏；
3. **不跑调**：变体音必须仍在五声音阶内（气质是"东方寓言"，变奏不能变味）。

外加拼接轨的时长、峰值、确定性。

运行：python tests/test_variations.py [--no-render]（渲染部分默认开，约 1 分钟）
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
from niulai.audio import variations as var  # noqa: E402
from niulai.audio.ost import PENTA, THEMES  # noqa: E402

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


def test_pure_function():
    print('test_pure_function')
    for tname in THEMES:
        th = THEMES[tname]
        for i in (0, 3, 7, 13):
            a = var.variation_notes(th, i)
            b = var.variation_notes(th, i)
            check(f'{tname} 变奏{i} 同 index 结果一致', a == b)


def test_variations_differ():
    print('test_variations_differ')
    for tname in THEMES:
        th = THEMES[tname]
        snaps = [var.variation_notes(th, i) for i in range(var.N_VARIATIONS)]
        uniq = len(set(snaps))
        check(f'{tname} 8 个变体互不相同', uniq == var.N_VARIATIONS,
              f'{uniq} unique / {var.N_VARIATIONS}')
        # 变体 0 是原型，必须与主题一致（族锚点）
        check(f'{tname} 变奏0 == 原型', snaps[0] == (tuple(th.notes),
                                                    tuple(th.durations)))


def test_stays_pentatonic():
    print('test_stays_pentatonic')
    for tname in THEMES:
        th = THEMES[tname]
        for i in range(var.N_VARIATIONS):
            notes, _ = var.variation_notes(th, i)
            bad = [n for n in notes
                   if n is not None and n[:-1] not in PENTA]
            check(f'{tname} 变奏{i} 全在五声音阶内', not bad, f'{bad[:3]}')
            # 全休止是退化情况，不能出现
            check(f'{tname} 变奏{i} 非全休止',
                  any(n is not None for n in notes))


def test_segment_order():
    print('test_segment_order')
    # 段数要够铺满一整轮（8 变体 x 30s = 240s）才能谈"覆盖/不重复"
    a = var._segment_order(8, 300.0, 30.0, seed=MASTER_SEED)
    b = var._segment_order(8, 300.0, 30.0, seed=MASTER_SEED)
    check('同 seed 顺序一致（确定性）', a == b)
    c = var._segment_order(8, 300.0, 30.0, seed=MASTER_SEED + 1)
    check('不同 seed 顺序不同', a != c)
    check('覆盖全部变体', set(a) == set(range(8)), f'{sorted(set(a))}')
    # 轮内不重复（首轮是 8 个变体各一次）
    check('首轮不重复', len(set(a[:8])) == 8, f'{a[:8]}')
    # 短轨只取前缀，不能越界
    short = var._segment_order(8, 10.0, 30.0, seed=MASTER_SEED)
    check('短轨段数按 ceil 计算', len(short) == int(np.ceil(10.0 / 30.0)) + 1,
          f'{len(short)}')


def test_render_and_stitch(do_render=True):
    print('test_render_and_stitch')
    if not do_render:
        print('  skip: --no-render')
        return
    tmp = tempfile.mkdtemp(prefix='niulai_var_')
    # 用 SINE 主题（友情）而非 SQUARE（狼袭）：方波每个周期都有满幅跳变，
    # "相邻跳变"指标对它无意义，测不出拼接爆音
    theme = 'friend'
    seg, total = 4.0, 20.0
    wavs = var.render_variations(theme, os.path.join(tmp, 'vars'), n=4,
                                 seg_sec=seg)
    check('渲染出 4 个变体', len(wavs) == 4)
    md5s = [md5_file(p) for p in wavs]
    check('变体文件两两不同', len(set(md5s)) == 4,
          f'{len(set(md5s))} unique')
    for i, p in enumerate(wavs):
        with wave.open(p, 'rb') as w:
            dur = w.getnframes() / float(w.getframerate())
        # 上游语义：loops = max(1, int(duration_sec / one_pass))，逐整数遍合成。
        # 故段长 = loops x one_pass —— 可能短于目标（多遍时），也可能长于目标
        # （一遍就超过目标时，如本主题 one_pass=7.5s > seg=4s）。精确钉住这个。
        pat = var.variation_pattern(THEMES[theme], i)
        one_pass = sum(pat.durations) * 60.0 / pat.bpm
        loops = max(1, int(seg / one_pass))
        expect = loops * one_pass
        check(f'{os.path.basename(p)} 时长 == {loops} 遍 x {one_pass:.2f}s',
              abs(dur - expect) < 0.05, f'{dur:.2f}s vs {expect:.2f}s')
        sr, d = var._load(p)
        check(f'{os.path.basename(p)} 峰值受控 <= 0.51',
              float(np.abs(d).max()) <= 0.51,
              f'{float(np.abs(d).max()):.3f}')

    out = os.path.join(tmp, 'suite.wav')
    var.stitch(wavs, out, total, crossfade=0.5, seed=MASTER_SEED)
    with wave.open(out, 'rb') as w:
        sr = w.getframerate()
        n = w.getnframes()
    check('拼接轨时长 == total', abs(n / float(sr) - total) < 0.05,
          f'{n / float(sr):.3f}s')
    _, d = var._load(out)
    check('拼接轨峰值归一化到 0.5', abs(float(np.abs(d).max()) - 0.5) < 0.02,
          f'{float(np.abs(d).max()):.3f}')
    check('拼接轨非全零', float(np.abs(d).max()) > 0.1)
    # 相邻样本跳变过大 = 拼接爆音；限幅在满幅的 30% 以内
    jump = float(np.abs(np.diff(d)).max())
    check('无拼接爆音（相邻跳变 < 0.3）', jump < 0.3, f'{jump:.3f}')

    # 确定性：同 seed 重拼 -> 逐字节相同
    out2 = os.path.join(tmp, 'suite2.wav')
    var.stitch(wavs, out2, total, crossfade=0.5, seed=MASTER_SEED)
    check('同 seed 拼接逐字节相同', md5_file(out) == md5_file(out2))
    out3 = os.path.join(tmp, 'suite3.wav')
    var.stitch(wavs, out3, total, crossfade=0.5, seed=MASTER_SEED + 7)
    check('换 seed 得到不同拼轨', md5_file(out) != md5_file(out3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-render', action='store_true')
    args = ap.parse_args()
    test_pure_function()
    test_variations_differ()
    test_stays_pentatonic()
    test_segment_order()
    test_render_and_stitch(do_render=not args.no_render)
    if FAILED:
        print(f'\nFAILED {len(FAILED)}: {FAILED}')
        return 1
    print('\nALL_VARIATION_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
