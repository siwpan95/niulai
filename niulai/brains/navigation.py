# -*- coding: utf-8 -*-
"""迁徙导航：allin-engine world/pathfinding 接入（A* 领队路径）。

原 `migration.migration_path` 是手搓的三段 smoothstep 折线；本模块用
allin `grid_astar` 在**程序化地形**上规划领队**陆地段**路线：

1. 迁徙走廊栅格化（cell=2.0u），可走 = 高程高于水位线（引用
   `desert.WATER_Y` 单一事实来源，河床/水塘不通）；
2. 终点吸附：渡口 (10,52) 实测在水下（h=-1.78），A* 终点取最近干地格
   （南岸水界，实测约 z=46）——入水过河段仍由原手搓编排负责；
3. A*（八向 + octile 启发）-> 视线拉直（LOS simplify）消栅格阶梯；
4. `route_point(route, progress)` 弧长参数化（分段 smoothstep，纯函数）。

确定性：栅格由 `desert.height_at`（seed 纯函数）生成，A* 无随机源 →
同 seed 两次规划逐点相同（tests/test_navigation.py 钉住）。
失败退路：A* 无路/起终点不可走 -> 返回 None，调用方回落原手搓路径
（不静默失败，check_env/测试可见）。
"""

import math

from allin_engine.world.map_data import MapData
from allin_engine.world.pathfinding import grid_astar

from .. import MASTER_SEED
from ..scenery import desert
from ..scenery.desert import WATER_Y

CELL = 2.0                       # 栅格边长（世界单位）
CORRIDOR = dict(x0=0.0, x1=76.0, z0=-24.0, z1=60.0)

START = (62.0, -16.0)            # 绿地（家）
# A* 陆地段终点 = 原手搓路径 seg2->seg3 边界（南岸水界，实测干地 h≈1.3）。
# 选它而非渡口 (10,52)（水下 h=-1.78）的理由：入水过河段是 act2 的
# 受编排节拍（_progress 在 330-470s 主动 dawdle），保持手搓；A* 终点与
# 手搓段在 progress=0.80 处逐分量衔接，牛群不跳变。
GOAL = (12.0, 44.0)
# 经停点：默认空（直线即过干河谷区域）；需要绕景时启用的分段 A* 机制。
VIA = ()


def _cell_col(x):
    return int((x - CORRIDOR['x0']) // CELL)


def _cell_row(z):
    return int((z - CORRIDOR['z0']) // CELL)


def _world_xy(col, row):
    return (CORRIDOR['x0'] + (col + 0.5) * CELL,
            CORRIDOR['z0'] + (row + 0.5) * CELL)


def build_nav_grid(seed=MASTER_SEED):
    """迁徙走廊 -> MapData（'.' 干地 / '#' 水域或界外）。"""
    cols = int((CORRIDOR['x1'] - CORRIDOR['x0']) // CELL)
    rows = int((CORRIDOR['z1'] - CORRIDOR['z0']) // CELL)
    grid = []
    for r in range(rows):
        row_chars = []
        for c in range(cols):
            x, z = _world_xy(c, r)
            h = desert.height_at(x, z, seed)
            row_chars.append('.' if h > WATER_Y else '#')
        grid.append(row_chars)
    return MapData(grid=grid, fill_char='#')


def _snap_dry(grid, col, row, max_ring=14):
    """(col,row) 不可走时，螺旋找最近可走格；找不到返回 None。"""
    if grid.in_bounds(col, row) and grid.get(col, row) == '.':
        return (col, row)
    for ring in range(1, max_ring + 1):
        for dc in range(-ring, ring + 1):
            for dr in range(-ring, ring + 1):
                if max(abs(dc), abs(dr)) != ring:
                    continue
                c, r = col + dc, row + dr
                if grid.in_bounds(c, r) and grid.get(c, r) == '.':
                    return (c, r)
    return None


def _los_clear(a, b, seed):
    """线段 a-b 是否全程在干地（按栅格精度采样，防窄水道漏检）。"""
    dist = math.hypot(b[0] - a[0], b[1] - a[1])
    steps = max(9, int(dist / (CELL * 0.5)))
    for k in range(steps + 1):
        u = k / steps
        x = a[0] + (b[0] - a[0]) * u
        z = a[1] + (b[1] - a[1]) * u
        if desert.height_at(x, z, seed) <= WATER_Y:
            return False
    return True


def _simplify(pts, seed):
    """视线拉直：能直连就跳过中间点（保首尾）。"""
    if len(pts) <= 2:
        return list(pts)
    out = [pts[0]]
    i = 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1 and not _los_clear(pts[i], pts[j], seed):
            j -= 1
        out.append(pts[j])
        i = j
    return out


def plan_migration_route(seed=MASTER_SEED, start=START, goal=GOAL, via=VIA):
    """A* 分段规划陆地段（过经停点）-> 世界坐标折线（已拉直）。

    失败返回 None（任一段无路/不可走即整体失败，调用方回落手搓路径）。
    """
    grid = build_nav_grid(seed)
    legs = []
    prev = start
    for v in via:
        legs.append((prev, v))
        prev = v
    legs.append((prev, goal))
    pts = []
    for a, b in legs:
        s = _snap_dry(grid, _cell_col(a[0]), _cell_row(a[1]))
        g = _snap_dry(grid, _cell_col(b[0]), _cell_row(b[1]))
        if s is None or g is None:
            return None
        path = grid_astar(grid, s, g, allow_diagonal=True, heuristic='octile')
        if not path:
            return None
        leg_pts = [_world_xy(c, r) for c, r in path]
        leg_pts[0] = tuple(a) if not pts else leg_pts[0]
        pts.extend(leg_pts)
    pts[0] = tuple(start)
    pts[-1] = _world_xy(*g)       # 终点 = 最后一个吸附格心（南岸干地）
    return _simplify(pts, seed)


_ROUTE_CACHE = {}


def migration_route(seed=MASTER_SEED):
    """缓存版规划（同 seed 一次）；无路回落 None（调用方走手搓路径）。"""
    key = int(seed)
    if key not in _ROUTE_CACHE:
        _ROUTE_CACHE[key] = plan_migration_route(seed)
    return _ROUTE_CACHE[key]


def route_point(route, progress):
    """progress∈[0,1] -> 折线弧长参数位置（分段 smoothstep，纯函数）。"""
    if not route:
        return None
    p = min(1.0, max(0.0, progress))
    segs = []
    total = 0.0
    for i in range(len(route) - 1):
        d = math.hypot(route[i + 1][0] - route[i][0],
                       route[i + 1][1] - route[i][1])
        segs.append(d)
        total += d
    if total <= 1e-9:
        return tuple(route[0])
    target = p * total
    acc = 0.0
    for i, d in enumerate(segs):
        if acc + d >= target or i == len(segs) - 1:
            u = 0.0 if d <= 1e-9 else min(1.0, (target - acc) / d)
            u = u * u * (3.0 - 2.0 * u)
            a, b = route[i], route[i + 1]
            return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        acc += d
    return tuple(route[-1])
