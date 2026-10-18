# -*- coding: utf-8 -*-
"""牛群迁徙：确定性编队（领队路径 + 跟随槽位）+ ECS 镜像。

编队模型（对照原片"跟着大部队一路迁徙"）：
- 领队（牛爸爸不在场的年长母牛）沿迁徙路径前进；
- 槽位 = 领队后方 3 列 x N 行的网格，每槽带确定性抖动（哈希）；
- 整体 progress = f(t)（纯函数），任一帧可复现。

领队路径（2026-10-18 起双轨）：
- progress < LAND_END：**allin A-star 规划**（brains/navigation.py，陆地段，
  终点 (12,44) 与本函数手搓段在 p=0.80 逐分量衔接）；
- progress >= LAND_END：原手搓三段 smoothstep（入水过河段，act2 受编排节拍）；
- A* 不可用（无路等）时全段回落手搓路径，不静默失败。
"""
import math

from .. import MASTER_SEED
from . import navigation

HERD_SIZE = 36                     # 30-50 头（全哥口径）
COLS, ROWS = 6, 6
SLOT_DX, SLOT_DZ = 2.6, 3.4        # 槽间距（列 x / 行 z）
LAND_END = 0.80                    # A* 陆地段进度上限（衔接手搓入水段）


def _hash01(i, salt):
    """槽位确定性抖动 [0,1)。"""
    h = ((i + 1) * 0x27D4EB2D) & 0xFFFFFFFF
    h = (h ^ (salt * 0x9E3779B1)) & 0xFFFFFFFF
    h ^= h >> 15
    return (h & 0xFFFFFF) / 16777216.0


def migration_path(progress):
    """progress∈[0,1] -> 领队世界位置 (x, z)。

    陆地段走 allin A* 规划折线（brains/navigation）；入水段/退路走
    原手搓三段 smoothstep 拼接口（确定性）。
    """
    p = min(1.0, max(0.0, progress))
    if p < LAND_END:
        route = navigation.migration_route(MASTER_SEED)
        if route is not None:
            pt = navigation.route_point(route, p / LAND_END)
            if pt is not None:
                return pt

    def seg(a, b, u):
        u = u * u * (3.0 - 2.0 * u)
        return a + (b - a) * u

    if p < 0.45:
        u = p / 0.45
        x = seg(62.0, 26.0, u)
        z = seg(-16.0, 14.0, u)
    elif p < 0.8:
        u = (p - 0.45) / 0.35
        x = seg(26.0, 12.0, u)
        z = seg(14.0, 44.0, u)
    else:
        u = (p - 0.8) / 0.2
        x = seg(12.0, 10.0, u)
        z = seg(44.0, 52.0, u)
    return x, z


def herd_slots(progress, count=HERD_SIZE):
    """progress -> [(x, z, yaw)] 编队（领队 + 跟随槽位，含确定性抖动）。"""
    lx, lz = migration_path(progress)
    ahead_x, ahead_z = migration_path(min(1.0, progress + 0.02))
    lead_yaw = math.atan2(ahead_z - lz, ahead_x - lx)
    out = [(lx, lz, lead_yaw)]
    for i in range(count - 1):
        col, row = i % COLS, i // COLS
        # 槽位在领队后方（局部 -X）展开成网格
        bx = lx - math.cos(lead_yaw) * (2.2 + row * SLOT_DX) \
            - math.sin(lead_yaw) * ((col - (COLS - 1) / 2.0) * SLOT_DZ)
        bz = lz - math.sin(lead_yaw) * (2.2 + row * SLOT_DX) \
            + math.cos(lead_yaw) * ((col - (COLS - 1) / 2.0) * SLOT_DZ)
        jx = (_hash01(i, 11) - 0.5) * 1.6
        jz = (_hash01(i, 29) - 0.5) * 1.6
        out.append((bx + jx, bz + jz, lead_yaw))
    return out


def river_progress(t_local, duration):
    """渡河进度 0..1（过溪戏：惧怕 -> 蛇逼近 -> 慌乱跳过 -> 全群过河）。"""
    u = min(1.0, max(0.0, t_local / duration))
    if u < 0.35:
        return 0.0                              # 岸边畏惧
    if u < 0.55:
        return (u - 0.35) / 0.2 * 0.15          # 牛来慌乱跳过（独行）
    return 0.15 + (u - 0.55) / 0.45 * 0.85      # 全群陆续过河
