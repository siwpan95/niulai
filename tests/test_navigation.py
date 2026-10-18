# -*- coding: utf-8 -*-
"""迁徙导航测试（allin pathfinding 接入）：路线有效 + 确定性 + 衔接。

纯离线（地形是 seed 纯函数，A* 无随机源）。

运行：python tests/test_navigation.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from niulai import MASTER_SEED  # noqa: E402
from niulai.brains import migration, navigation  # noqa: E402
from niulai.scenery import desert  # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    status = 'ok' if cond else 'FAIL'
    print(f'  {status}: {name}' + (f'  [{detail}]' if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def test_route_valid():
    print('test_route_valid')
    route = navigation.plan_migration_route()
    check('路线存在', route is not None)
    check('至少 2 点', route is not None and len(route) >= 2)
    check('起点精确', route is not None
          and math.hypot(route[0][0] - navigation.START[0],
                         route[0][1] - navigation.START[1]) < 1e-9)
    # 终点干地（吸附格）
    gx, gz = route[-1]
    check('终点干地', desert.height_at(gx, gz, MASTER_SEED)
          > desert.WATER_Y, f'h={desert.height_at(gx, gz, MASTER_SEED):.3f}')
    # 全程干地（2u 采样）
    wet = 0
    for i in range(len(route) - 1):
        a, b = route[i], route[i + 1]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        for k in range(int(d / 2.0) + 1):
            u = k * 2.0 / d if d else 0.0
            if desert.height_at(a[0] + (b[0] - a[0]) * u,
                                a[1] + (b[1] - a[1]) * u,
                                MASTER_SEED) <= desert.WATER_Y:
                wet += 1
    check('全程无涉水采样', wet == 0, f'wet={wet}')


def test_route_deterministic():
    print('test_route_deterministic')
    r1 = navigation.plan_migration_route()
    r2 = navigation.plan_migration_route()
    check('两次规划逐点相同', r1 == r2)
    navigation._ROUTE_CACHE.clear()
    r3 = navigation.migration_route()
    check('缓存版同内容', r3 == r1)


def test_route_point():
    print('test_route_point')
    route = navigation.migration_route()
    p0 = navigation.route_point(route, 0.0)
    p1 = navigation.route_point(route, 1.0)
    check('p=0 即起点', math.hypot(p0[0] - route[0][0],
                                 p0[1] - route[0][1]) < 1e-9)
    check('p=1 即终点', math.hypot(p1[0] - route[-1][0],
                                 p1[1] - route[-1][1]) < 1e-9)
    check('进度钳位', navigation.route_point(route, -1.0) == p0)
    check('进度钳位上界', navigation.route_point(route, 2.0) == p1)
    # 单调推进（弧长参数化的基本性质）
    prev = -1.0
    mono = True
    for k in range(21):
        p = navigation.route_point(route, k / 20.0)
        d = math.hypot(p[0] - route[0][0], p[1] - route[0][1])
        if d < prev - 1e-6:
            mono = False
        prev = d
    check('推进单调', mono)


def test_migration_handoff():
    print('test_migration_handoff')
    before = migration.migration_path(migration.LAND_END - 1e-4)
    after = migration.migration_path(migration.LAND_END)
    jump = math.hypot(before[0] - after[0], before[1] - after[1])
    check('A*/手搓衔接跳变 < 2u', jump < 2.0, f'jump={jump:.3f}')
    # 终点仍是渡口（入水段保留手搓）
    end = migration.migration_path(1.0)
    check('终点渡口', abs(end[0] - 10.0) < 0.01 and abs(end[1] - 52.0) < 0.01)


def test_fallback():
    print('test_fallback')
    orig = navigation.migration_route
    navigation._ROUTE_CACHE.clear()
    navigation.migration_route = lambda seed=MASTER_SEED: None
    try:
        p = migration.migration_path(0.3)
        check('A* 不可用时回落手搓路径',
              abs(p[0] - 62.0 + 36.0 * 0) >= 0 and isinstance(p, tuple))
        # 手搓路径在 p=0.3 的期望值（seg1 内）
        u = 0.3 / 0.45
        u = u * u * (3.0 - 2.0 * u)
        ex = 62.0 + (26.0 - 62.0) * u
        ez = -16.0 + (14.0 + 16.0) * u
        check('回落值与手搓一致', abs(p[0] - ex) < 1e-9 and abs(p[1] - ez) < 1e-9)
    finally:
        navigation.migration_route = orig
        navigation._ROUTE_CACHE.clear()


def main():
    test_route_valid()
    test_route_deterministic()
    test_route_point()
    test_migration_handoff()
    test_fallback()
    if FAILED:
        print(f'\nFAILED {len(FAILED)}: {FAILED}')
        return 1
    print('\nALL_NAVIGATION_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
