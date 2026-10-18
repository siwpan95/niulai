# -*- coding: utf-8 -*-
"""fx 粒子场：allin-engine fx 接入（沙尘 / 飞沫 / 夜风寒尘）。

把 `allin_engine.fx.particle_np.NumpyParticleSystem`（2D 向量化粒子系统）
锚定到世界 z 平面，作为氛围层补"内容密度"——原片场景留白多，粒子是
不破坏粗粝美学的填充手段。

三条设计口径：

1. **确定性**（本工程铁律）：引擎 1.0.0 的 `NumpyParticleSystem` 未暴露
   seed 参数（构造即 `np.random.default_rng()` 无种子）——本模块构造后
   **注入** `default_rng(seed)`。记账：这是私有属性 `_rng` 的非常规用法，
   上游若补 seed 参数应改走正门（见 docs/REFERENCE.md）。
2. **固定步长**：dt 恒为 1/fps；`state_at(t)` 对已模拟过的时间增量推进，
   t 回退则从头重模拟（并行渲染每块独立场景对象，块内顺序一致 ->
   跨进程逐帧一致，tests/test_particles.py 钉住）。
3. **2D -> 3D 映射**：粒子 (x, y) -> 世界 (X, Y=高度)，z 为锚平面；
   发射器/力场参数全部确定性（无墙钟、无随机）。

依赖：numpy + allin-engine（MIT，siwpan 自研）。
"""

import math

import numpy as np

from allin_engine.fx.particle import Emitter, ForceField
from allin_engine.fx.particle_np import NumpyParticleSystem

from .. import MASTER_SEED


class ParticleField:
    """锚定在 z 平面的 2D 粒子场（世界坐标 X=x, Y=y）。"""

    def __init__(self, seed=MASTER_SEED, z=0.0, dt=None, fps=30,
                 max_particles=3000):
        self.seed = int(seed)
        self.z = float(z)
        self.dt = dt if dt is not None else 1.0 / float(fps)
        self.max_particles = int(max_particles)
        self._sys = None
        self._sim_t = -1.0            # 已模拟到的时刻（不含）
        self._emitters = []           # (emitter, follow) follow=世界坐标源或 None
        self._forces = []

    # ------------------------------------------------------------ 装配 --
    def add_emitter(self, emitter, follow=None):
        """follow: None 或 callable(t) -> (x, y)，每帧前更新发射点。"""
        self._emitters.append((emitter, follow))
        self._sys = None              # 装配变化 -> 下次 state_at 重建
        return self

    def emitter(self, i):
        """第 i 个发射器（场景侧可按时刻改 rate 等参数，确定性）。"""
        return self._emitters[i][0]

    def add_force(self, force):
        self._forces.append(force)
        self._sys = None
        return self

    # ------------------------------------------------------------ 模拟 --
    def _build(self):
        sys_ = NumpyParticleSystem(max_particles=self.max_particles)
        # 确定性注入（引擎无 seed 参数，见模块 docstring 记账）
        sys_._rng = np.random.default_rng(self.seed)
        for em, _ in self._emitters:
            # 发射器/力场对象跨重建复用：必须清零累积状态，
            # 否则回退重模拟会带着前向模拟的残余 _accum/_time（实测踩坑）
            em._accum = 0.0
            sys_.add_emitter(em)
        for ff in self._forces:
            ff._time = 0.0
            sys_.add_force_field(ff)
        self._sys = sys_
        self._sim_t = 0.0

    def _advance_to(self, t):
        if self._sys is None:
            self._build()
        elif t < self._sim_t - 1e-9:
            self._build()             # 时间回退（随机访问/断点续跑）-> 重模拟
        steps = int((t - self._sim_t) / self.dt + 1e-9)
        for _ in range(max(0, steps)):
            for em, follow in self._emitters:
                if follow is not None:
                    em.x, em.y = follow(self._sim_t + _ * self.dt)
            self._sys.update(self.dt)
        self._sim_t += max(0, steps) * self.dt

    def state_at(self, t):
        """t -> {'pos': (N,3) float, 'rgba': (N,4) uint8, 'count': int}。

        位置为世界坐标（z = 锚平面）；rgba 已按生命透明度衰减。
        """
        self._advance_to(float(t))
        st = self._sys.numpy_state()
        n = int(st['x'].shape[0])
        if n == 0:
            return {'pos': np.zeros((0, 3)), 'rgba': np.zeros((0, 4),
                                                             np.uint8),
                    'count': 0}
        pos = np.empty((n, 3), dtype=np.float64)
        pos[:, 0] = st['x']
        pos[:, 1] = st['y']
        pos[:, 2] = self.z
        col = np.asarray(st['color'], dtype=np.float64)
        alpha = np.clip(st['alpha'], 0.0, 1.0)
        rgba = np.empty((n, 4), dtype=np.uint8)
        rgba[:, :3] = np.clip(col, 0, 255).astype(np.uint8)
        rgba[:, 3] = (alpha * 255.0).astype(np.uint8)
        return {'pos': pos, 'rgba': rgba, 'count': n}

    @property
    def count(self):
        return 0 if self._sys is None else self._sys.count


# ---------------------------------------------------------------- 预置场 --
# 三个氛围场的参数全部是确定性常量（颜色/速率/力场强度），
# 锚 z 与发射点由各幕场景给定。

def dust_field(seed, z, follow=None, rate=90.0):
    """沙漠风沙：顺风（+X）漂移 + 噪声扰动，暖沙色。"""
    f = ParticleField(seed=seed, z=z)
    f.add_emitter(Emitter(x=0.0, y=1.2, rate=rate, spread=0.9,
                          direction=0.0, speed=5.5, life=2.6, size=3.0,
                          color=(214, 196, 164), shape='circle',
                          radius=9.0), follow=follow)
    f.add_force(ForceField('wind', strength=2.2))
    f.add_force(ForceField('noise', strength=0.55, noise_scale=7.0,
                           noise_strength=1.0))
    return f


def splash_field(seed, z, follow=None, rate=140.0):
    """涉水飞沫：向上初速 + 重力回落，冷白色。"""
    f = ParticleField(seed=seed, z=z)
    f.add_emitter(Emitter(x=0.0, y=0.35, rate=rate, spread=1.1,
                          direction=math.pi / 2, speed=3.4, life=0.85,
                          size=2.0, color=(226, 238, 244), shape='point'),
                  follow=follow)
    f.add_force(ForceField('gravity', strength=-9.0))
    f.add_force(ForceField('wind', strength=0.4))
    return f


def mote_field(seed, z, follow=None, rate=26.0):
    """夜风寒尘：慢速漂浮微尘，冷灰色（act4 夜宿 / act5 将晓）。"""
    f = ParticleField(seed=seed, z=z)
    f.add_emitter(Emitter(x=0.0, y=0.5, rate=rate, spread=3.14159,
                          direction=0.0, speed=0.5, life=5.5, size=2.0,
                          color=(178, 186, 198), shape='circle', radius=14.0),
                  follow=follow)
    f.add_force(ForceField('noise', strength=0.16, noise_scale=11.0,
                           noise_strength=1.0))
    return f
