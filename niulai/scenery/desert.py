# -*- coding: utf-8 -*-
"""荒漠高度场 + 顶点色烘焙（序幕场景）。

地形特征（对照原片"梦境草原/荒漠"意象）：
- 大尺度沙丘（ridged fBm，振幅约 7 单位，低伏绵延）；
- 一条干河谷（wadi）斜穿场景；
- 幕末绿地（GRASS_PATCH）：牛来躺卧、云玎降落处 —— 高度整平、色相转草绿。
全部由 (world_x, world_z, seed) 纯函数决定，跨进程可复现。
"""
import array
import math

from world3d.engine.geometry import MeshData

from ..cast import perf

_MASK = 0xFFFFFFFF


def _hash01(ix, iy, seed):
    """整数格点 + seed -> [0,1) 确定性哈希（位运算，跨平台逐位相同）。"""
    h = (ix * 0x27D4EB2D) & _MASK
    h = (h ^ (iy * 0x165667B1)) & _MASK
    h = (h ^ (seed * 0x9E3779B1)) & _MASK
    h = ((h ^ (h >> 15)) * 0x2C1B3C6D) & _MASK
    h = ((h ^ (h >> 12)) * 0x297A2D39) & _MASK
    h ^= h >> 15
    return (h & 0xFFFFFF) / 16777216.0


def _value_noise(x, y, seed):
    """双线性插值值噪声（smoothstep 平滑）。"""
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    ux = fx * fx * (3.0 - 2.0 * fx)
    uy = fy * fy * (3.0 - 2.0 * fy)
    h = _hash01
    n00, n10 = h(ix, iy, seed), h(ix + 1, iy, seed)
    n01, n11 = h(ix, iy + 1, seed), h(ix + 1, iy + 1, seed)
    a = n00 + (n10 - n00) * ux
    b = n01 + (n11 - n01) * ux
    return a + (b - a) * uy


def _fbm(x, y, seed, octaves=4):
    amp, freq, total, norm = 1.0, 1.0, 0.0, 0.0
    for i in range(octaves):
        total += amp * _value_noise(x * freq, y * freq, seed + i * 7919)
        norm += amp
        amp *= 0.5
        freq *= 2.0
    return total / norm


def _mix(a, b, t):
    t = min(1.0, max(0.0, t))
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


def _smooth(e0, e1, x):
    if e1 == e0:
        return 0.0
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


# 幕末绿地（牛来躺卧处，云玎降落点附近）
GRASS_CENTER = (64.0, -18.0)
GRASS_RADIUS = 26.0
# 干河谷：沿 z = 60*sin(x*0.012) 的波形下切
WADI_AMP, WADI_FREQ = 3.2, 0.012
LIGHT_DIR = (0.42, 0.78, 0.30)


def grass_mask(wx, wz, seed=0):
    """绿地权重 [0,1]：半径内平滑过渡，边缘用噪声打糊（避免圆形贴图感）。"""
    dx, dz = wx - GRASS_CENTER[0], wz - GRASS_CENTER[1]
    d = math.sqrt(dx * dx + dz * dz)
    edge = 1.0 - _smooth(GRASS_RADIUS * 0.55, GRASS_RADIUS, d)
    if edge <= 0.0:
        return 0.0
    wobble = 0.80 + 0.20 * _fbm(wx * 0.035 + 7.0, wz * 0.035 - 3.0, seed + 99, 2)
    return min(1.0, edge * wobble)


def height_at(wx, wz, seed):
    """世界坐标 -> 高程（纯函数）。

    沙丘 = ridged fBm；河谷下切；绿地整平为低矮草滩。
    """
    dune = _fbm(wx * 0.0125 + 3.1, wz * 0.0125 - 1.7, seed, 4)
    ridge = 1.0 - abs(2.0 * dune - 1.0)                    # 折叠出沙丘脊线
    h = 7.5 * ridge ** 1.6
    # 干河谷：沿波形带下切
    cz = 60.0 * math.sin(wx * WADI_FREQ)
    h -= WADI_AMP * max(0.0, 1.0 - abs(wz - cz) / 9.0)
    # 绿地整平
    m = grass_mask(wx, wz, seed)
    plain = 0.9 + 0.5 * _fbm(wx * 0.05, wz * 0.05, seed + 613, 2)
    return h * (1.0 - m) + plain * m


def _slope_at(heights, n, step, i, j):
    il, ir = max(0, i - 1), min(n - 1, i + 1)
    jd, ju = max(0, j - 1), min(n - 1, j + 1)
    dx = (heights[j * n + ir] - heights[j * n + il]) / ((ir - il) * step)
    dz = (heights[ju * n + i] - heights[jd * n + i]) / ((ju - jd) * step)
    return dx, dz


def _vertex_color(h, slope, lam, jitter, mask):
    """(高程, 坡度, 面向光, 抖动, 绿地权重) -> 烘焙 RGB。

    分层：沙 -> 深沙（谷/阴影） -> 岩（陡处）；绿地权重把色相推向草绿。
    最后乘 0.34 + 0.90*lam 把光照烘进顶点色（与 terrain_flyover 同手法）。
    """
    if mask > 0.5:
        c = _mix(perf.GRASS_PATCH_DARK, perf.GRASS_PATCH, _smooth(0.85, 1.6, h))
    else:
        c = _mix(perf.DESERT_SAND, perf.DESERT_SAND_DARK, _smooth(0.0, 3.5, h))
        c = _mix(c, perf.DESERT_WADI, _smooth(0.25, 0.85, slope))
        c = _mix(c, perf.DESERT_ROCK, _smooth(0.9, 1.8, slope))
    k = 0.34 + 0.90 * lam
    j = 0.88 + 0.24 * jitter
    return (min(1.0, c[0] * k * j), min(1.0, c[1] * k * j), min(1.0, c[2] * k * j), 1.0)


def build_terrain(seed, grid=192, step=1.0):
    """建静态地形 MeshData（positions + colors，非索引三角形汤）。

    返回 (MeshData, heights)。192x192 格 = 73k 三角，只在装配时算一次。
    """
    n = grid
    ox = oz = -0.5 * (n - 1) * step
    heights = [0.0] * (n * n)
    for j in range(n):
        wz = oz + j * step
        base = j * n
        for i in range(n):
            heights[base + i] = height_at(ox + i * step, wz, seed)

    lx, ly, lz = LIGHT_DIR
    ll = math.sqrt(lx * lx + ly * ly + lz * lz)
    cols = [(0.0, 0.0, 0.0, 1.0)] * (n * n)
    for j in range(n):
        for i in range(n):
            dx, dz = _slope_at(heights, n, step, i, j)
            nx, ny, nz = -dx, 1.0, -dz
            nl = math.sqrt(nx * nx + ny * ny + nz * nz)
            lam = max(0.0, (nx * lx + ny * ly + nz * lz) / (nl * ll))
            slope = 1.0 - 1.0 / nl
            wx, wz = ox + i * step, oz + j * step
            cols[j * n + i] = _vertex_color(
                heights[j * n + i], slope, lam,
                _hash01(i, j, seed + 4241), grass_mask(wx, wz, seed))

    pos = array.array('f')
    col = array.array('f')
    for j in range(n - 1):
        z0, z1 = oz + j * step, oz + (j + 1) * step
        row = j * n
        for i in range(n - 1):
            x0, x1 = ox + i * step, ox + (i + 1) * step
            a, b = row + i, row + i + 1
            c, d = a + n, b + n
            for k in (a, b, d, a, d, c):
                pos.extend((x0 if k in (a, c) else x1,
                            heights[k],
                            z0 if k in (a, b) else z1))
                col.extend(cols[k])
    return MeshData(pos.tolist(), colors=col.tolist(), name='desert'), heights
