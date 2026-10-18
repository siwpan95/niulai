# -*- coding: utf-8 -*-
"""粒子场测试（allin fx 接入）：确定性 + 步进等价 + 边界。

关键性质（本工程铁律在粒子上的落地）：
1. **同 t 同状态**：state_at(t) 两次调用逐字节相同；
2. **增量 == 全新**：一个场从 0 步进到 t，另一个场新建直接 state_at(t)，
   两者状态相同（随机访问/断点续跑/并行分块都靠这条）；
3. **回退重模拟**：t 回退后从头模拟，结果与正向一致；
4. 边界：count <= max_particles、坐标有限、rate=0 不产粒子。

运行：python tests/test_particles.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from niulai.fx import particles as fx  # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    status = 'ok' if cond else 'FAIL'
    print(f'  {status}: {name}' + (f'  [{detail}]' if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def _same(s1, s2):
    if s1['count'] != s2['count']:
        return False
    if s1['count'] == 0:
        return True
    return (np.array_equal(s1['pos'], s2['pos'])
            and np.array_equal(s1['rgba'], s2['rgba']))


def test_dust_determinism():
    print('test_dust_determinism')
    f = fx.dust_field(seed=20260805, z=10.0)
    s1 = f.state_at(3.0)
    s2 = f.state_at(3.0)
    check('同 t 两次相同', _same(s1, s2))
    check('有粒子', s1['count'] > 0, f"count={s1['count']}")
    check('坐标有限', bool(np.isfinite(s1['pos']).all()))
    check('z 锚定', bool(np.all(s1['pos'][:, 2] == 10.0)))
    check('count 不超容量', s1['count'] <= f.max_particles)


def test_incremental_equals_fresh():
    print('test_incremental_equals_fresh')
    f1 = fx.dust_field(seed=7, z=0.0)
    for k in range(1, 61):                 # 0 -> 2s 逐步进
        f1.state_at(k / 30.0)
    s_inc = f1.state_at(2.0)
    f2 = fx.dust_field(seed=7, z=0.0)
    s_new = f2.state_at(2.0)               # 新建直接到 2s
    check('增量 == 全新', _same(s_inc, s_new),
          f"{s_inc['count']} vs {s_new['count']}")
    # 回退重模拟
    s_back = f1.state_at(1.0)
    f3 = fx.dust_field(seed=7, z=0.0)
    s_fresh1 = f3.state_at(1.0)
    check('回退后重模拟一致', _same(s_back, s_fresh1))


def test_rate_gate():
    print('test_rate_gate')
    f = fx.splash_field(seed=11, z=48.5)
    f.emitter(0).rate = 0.0                # 窗外：不产粒子
    s = f.state_at(2.0)
    check('rate=0 无粒子', s['count'] == 0, f"count={s['count']}")
    f.emitter(0).rate = 100.0              # 窗内：产粒子
    s2 = f.state_at(2.5)
    check('rate>0 有粒子', s2['count'] > 0)


def test_lifecycle():
    print('test_lifecycle')
    f = fx.mote_field(seed=5, z=3.0)
    s0 = f.state_at(0.0)
    check('t=0 无粒子', s0['count'] == 0)
    s1 = f.state_at(1.0)
    check('t=1 有粒子', s1['count'] > 0)
    alpha = s1['rgba'][:, 3].astype(np.int32)
    check('透明度在 0-255', bool(((alpha >= 0) & (alpha <= 255)).all()))


def main():
    test_dust_determinism()
    test_incremental_equals_fresh()
    test_rate_gate()
    test_lifecycle()
    if FAILED:
        print(f'\nFAILED {len(FAILED)}: {FAILED}')
        return 1
    print('\nALL_PARTICLE_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
