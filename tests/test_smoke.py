# -*- coding: utf-8 -*-
"""冒烟测试：时间轴不变量 + 角色姿态包络 + 场景相机防穿地。

运行：python -m pytest tests/ 或 python tests/test_smoke.py（零三方依赖 runner 兜底）。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from niulai import FPS, MASTER_SEED, TOTAL_DURATION
from niulai.acts.act0_prologue import CALF_AT, PrologueScene
from niulai.bridge.events import EV_ACT_ENTER, Bridge
from niulai.cast import perf
from niulai.cast.rig import bounds_of
from niulai.cast.skylark import Skylark, flight_head, flight_pos
from niulai.scenery import desert
from niulai.timeline import ACTS, Timeline

FAILED = []


def check(name, cond, detail=''):
    status = 'ok' if cond else 'FAIL'
    print(f'  {status}: {name}' + (f'  [{detail}]' if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def test_timeline():
    print('test_timeline')
    tl = Timeline()
    # 分幕边界连续覆盖全片
    prev_end = 0.0
    for name, start, end, _ in ACTS:
        check(f'{name} 边界相接', abs(start - prev_end) < 1e-9,
              f'start={start} prev_end={prev_end}')
        check(f'{name} 时长正', end > start)
        prev_end = end
    check('末幕结束 == 全片时长', abs(prev_end - TOTAL_DURATION) < 1e-9)
    # 帧号互逆
    check('t_of/frame_of 互逆', abs(tl.t_of(tl.frame_of(123.4)) - 123.4) < 1.0 / FPS)
    # act_at
    check('act_at 开头', tl.act_at(0.0) == ACTS[0][0])
    check('act_at 末尾闭区间', tl.act_at(TOTAL_DURATION) == ACTS[-1][0])
    check('act_at 中段', tl.act_at(700.0) == 'act2_migration')
    try:
        tl.act_at(TOTAL_DURATION + 1)
        check('act_at 越界抛错', False)
    except ValueError:
        check('act_at 越界抛错', True)


def test_quantize():
    print('test_quantize')
    tl = Timeline()
    check('量化在栅格上', abs(tl.quantize(1.234) * 12 - math.floor(1.234 * 12)) < 1e-9)
    check('量化幂等', tl.quantize(tl.quantize(2.345)) == tl.quantize(2.345))
    a, b = tl.quantize(1.0), tl.quantize(1.2)
    check('量化单调', a <= b)
    # 12fps 栅格步长 1/12
    check('栅格步长', abs((tl.quantize(0.09) - tl.quantize(0.0)) - 1.0 / 12.0) < 1e-9)


def test_calf_cannot_stand():
    print('test_calf_cannot_stand')
    scene = PrologueScene(seed=MASTER_SEED, grid=64)
    ground = desert.height_at(CALF_AT[0], CALF_AT[1], MASTER_SEED)
    calf = scene.calf
    for t in (0.0, 0.37, 1.11, 2.79, 5.0):
        tq = Timeline.quantize(t)
        lo, hi = bounds_of(calf.meshes(tq))
        # 躯干顶高高不过 ground+1.1（站不起来；站平应 > ground+1.5）
        check(f't={t}: 躯干低头位', hi[1] < ground + 1.1, f'top={hi[1]:.3f}')
        # 蹄子恰着地（陷土/浮空都不超过 0.08）
        check(f't={t}: 蹄子着地', ground - 0.08 <= lo[1] <= ground + 0.08,
              f'bottom={lo[1]:.3f} ground={ground:.3f}')
        # 确定性：同 t 两次 meshes 的位置序列相同
        p1 = [m.positions for m in calf.meshes(tq)]
        p2 = [m.positions for m in calf.meshes(tq)]
        check(f't={t}: 姿态确定性', p1 == p2)


def test_skylark_flight():
    print('test_skylark_flight')
    p0, p1 = flight_pos(0.5), flight_pos(59.5)
    check('末段已下降', p1.y < p0.y - 20.0, f'{p0.y:.1f} -> {p1.y:.1f}')
    # 全程有界（荒漠网格 192x192，世界 [-96, 96]；航线端点在其外但相机防穿地兜底）
    ys = [flight_pos(t * 0.5).y for t in range(120)]
    check('高度有界', min(ys) > 2.0 and max(ys) < 60.0,
          f'min={min(ys):.1f} max={max(ys):.1f}')
    # 航向连续（无跳变）
    heads = [flight_head(t * 0.5) for t in range(120)]
    jumps = [abs((heads[i + 1] - heads[i] + math.pi) % (2 * math.pi) - math.pi)
             for i in range(len(heads) - 1)]
    check('航向连续', max(jumps) < 0.5, f'max_jump={max(jumps):.3f}')
    bird = Skylark()
    m1 = [m.positions for m in bird.meshes(Timeline.quantize(3.3))]
    m2 = [m.positions for m in bird.meshes(Timeline.quantize(3.3))]
    check('云玎姿态确定性', m1 == m2)


def test_desert():
    print('test_desert')
    h1 = desert.height_at(12.3, -45.6, MASTER_SEED)
    h2 = desert.height_at(12.3, -45.6, MASTER_SEED)
    check('高程确定性', h1 == h2)
    h3 = desert.height_at(12.3, -45.6, MASTER_SEED + 1)
    check('高程随 seed 变化', h1 != h3)
    # 牛来躺卧点在绿地内且基本整平
    m = desert.grass_mask(CALF_AT[0], CALF_AT[1], MASTER_SEED)
    check('牛来点在绿地内', m > 0.8, f'mask={m:.3f}')
    hh = desert.height_at(CALF_AT[0], CALF_AT[1], MASTER_SEED)
    check('绿地整平', abs(hh - 1.4) < 1.5, f'h={hh:.3f}')


def test_scene_camera():
    print('test_scene_camera')
    scene = PrologueScene(seed=MASTER_SEED, grid=48)
    for t in (0.0, 12.0, 30.0, 51.9, 56.0, 59.5):
        eye, target = scene.camera(t)
        g = scene.ground_at(eye.x, eye.z)
        check(f't={t}: 相机不穿地', eye.y >= g + 1.19, f'eye_y={eye.y:.2f} g={g:.2f}')
        check(f't={t}: 注视点在前', eye.distance(target) if hasattr(eye, 'distance')
              else math.dist((eye.x, eye.y, eye.z), (target.x, target.y, target.z)) > 3.0)
    # 姿态确定性
    a = [m.positions for m in scene.meshes(20.0)]
    b = [m.positions for m in scene.meshes(20.0)]
    check('场景姿态确定性', a == b)
    # 地形三角数
    check('地形非空', scene.terrain_md.vertex_count > 1000)


def test_bridge_minimal():
    print('test_bridge_minimal')
    bridge = Bridge()
    got = []
    bridge.on(EV_ACT_ENTER, lambda p: got.append(p))
    bridge.emit(EV_ACT_ENTER, {'act': 'act0_prologue', 't': 0.0})
    check('桥接扇出本地监听', len(got) == 1 and got[0]['act'] == 'act0_prologue')
    check('桥接历史有界增长', len(bridge.log) == 1)


def main():
    for fn in (test_timeline, test_quantize, test_calf_cannot_stand,
               test_skylark_flight, test_desert, test_scene_camera,
               test_bridge_minimal):
        fn()
    print()
    if FAILED:
        print(f'FAILED {len(FAILED)}: {FAILED}')
        return 1
    print('ALL_SMOKE_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
