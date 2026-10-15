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
from niulai.brains import migration, wolves
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


def test_herd_and_pack():
    print('test_herd_and_pack')
    # 全哥口径：牛群 30-50 实例化 + 狼群 8-12 行为树
    check('牛群规模 30-50', 30 <= migration.HERD_SIZE <= 50,
          f'HERD_SIZE={migration.HERD_SIZE}')
    check('狼群规模 8-12', 8 <= wolves.WOLF_COUNT <= 12,
          f'WOLF_COUNT={wolves.WOLF_COUNT}')
    # 编队确定性 + 规模
    a = migration.herd_slots(0.5)
    b = migration.herd_slots(0.5)
    check('编队确定性', a == b)
    check('编队规模', len(a) == migration.HERD_SIZE)
    # 领队沿路径、槽位在领队后方 20 单位内
    lx, lz, _ = a[0]
    for x, z, _ in a[1:]:
        d = ((x - lx) ** 2 + (z - lz) ** 2) ** 0.5
        if d > 22.0:
            check('槽位距领队', False, f'd={d:.1f}')
            break
    else:
        check('槽位距领队', True)
    # 路径端点（绿地出发、河边收尾）
    check('路径起点', migration.migration_path(0.0) == (62.0, -16.0))
    ex, ez = migration.migration_path(1.0)
    check('路径终点近渡口', abs(ex - 10.0) < 1.0 and abs(ez - 52.0) < 1.0,
          f'({ex:.1f},{ez:.1f})')


def test_battle_determinism():
    print('test_battle_determinism')
    b1 = wolves.build_battle_log()
    b2 = wolves.build_battle_log()
    check('战斗节拍确定性（同种子两次运行逐字相同）', b1 == b2)
    check('战斗节拍非空', len(b1) > 5, f'{len(b1)} beats')
    # 狼群态势：环半径有界（中心与 act4 一致 = 树下）
    for t in (0.0, 8.0, 20.0):
        pack = wolves.pack_positions(t, center=(10.0, 63.0))
        check(f'狼群 t={t} 规模', len(pack) == wolves.WOLF_COUNT)
        rs = [((x - 10.0) ** 2 + (z - 63.0) ** 2) ** 0.5 for x, z, _, _ in pack]
        check(f'狼群 t={t} 环半径', 2.0 <= max(rs) <= 22.0, f'max_r={max(rs):.1f}')


def test_subtitles():
    print('test_subtitles')
    from niulai.acts.act1_stand import LINES as L1
    from niulai.acts.subtitles import SubtitleTrack
    tr = SubtitleTrack(L1)
    check('台词起始前无字幕', tr.line_at(1.0) is None)
    sp, tx = tr.line_at(5.0)
    check('台词窗口内命中', sp == '牛妈妈' and '欢迎你' in tx)
    check('台词结束后无字幕', tr.line_at(300.0) is None)
    # 时间窗不重叠（同一时刻只显示一句）
    windows = sorted((t0, t1) for t0, t1, _, _ in L1)
    overlap = any(windows[i][1] > windows[i + 1][0] + 1e-9
                  for i in range(len(windows) - 1))
    check('台词时间窗不重叠', not overlap)


def test_ost():
    print('test_ost')
    try:
        import numpy  # noqa: F401
    except ImportError:
        print('  skip: numpy 缺失（OST 需要 audio extra）')
        return
    import os
    import tempfile
    from niulai.audio.ost import render_theme
    with tempfile.TemporaryDirectory() as tmp:
        p = render_theme('wolves', os.path.join(tmp, 't.wav'), duration_sec=5.0)
        check('OST 渲染非空', os.path.getsize(p) > 10000)


def main():
    for fn in (test_timeline, test_quantize, test_calf_cannot_stand,
               test_skylark_flight, test_desert, test_scene_camera,
               test_bridge_minimal, test_herd_and_pack,
               test_battle_determinism, test_subtitles, test_ost):
        fn()
    print()
    if FAILED:
        print(f'FAILED {len(FAILED)}: {FAILED}')
        return 1
    print('ALL_SMOKE_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
