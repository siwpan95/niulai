# -*- coding: utf-8 -*-
"""第四幕 · 狼袭与母亡（2100–3180s，18 min，**夜戏**）。

夜宿歪脖子树旁 -> 狼群环伺 -> 总攻 -> 妈妈引开狼群、留在树下
-> 黎明，牛群离去，牛来回望。

战斗节拍：allin CombatEngine 固定种子无头战斗（brains.wolves.build_battle_log）
产出 31 条节拍文本，驱动总攻段的镜头切换时机（每次伤害/格挡 = 一次冲撞）。

镜头表（act-local 秒，总 1080s）：
  0–120   夜宿：牛群卧伏，妈妈守夜（全景，月光）
  120–300 狼群现身树线（pack circle）
  300–480 总攻（charge/bite，节拍驱动；牛来 vs 狼王）
  480–720 妈妈引开狼群，留在歪脖子树旁（情感高潮）
  720–1080 黎明，牛群北去，牛来回望树下
"""
import math

from pyglet.math import Vec3

from .. import MASTER_SEED
from ..cast import perf
from ..cast.calf import Calf
from ..cast.quadruped import Quadruped
from ..cast.specs import MOTHER_SPEC, WOLF_SPEC
from ..brains.world import CastState, CastWorld
from ..brains import btree, phases, wolves
from ..fx import particles as fx_particles
from ..fx.layer import ParticleLayer
from ..scenery import desert, tree as tree_mod
from ..timeline import Timeline
from . import base
from .subtitles import SubtitleOverlay, SubtitleTrack

ACT = 'act4_wolves'
T_END = 1080.0

SKY = (0.11, 0.14, 0.22)          # 夜（提亮：狼群要读得出）
FOG_K = 0.0165
TINT = (0.66, 0.70, 0.84)         # 全局压暗偏蓝（月光；角色要读得出）

TREE_AT = (10.0, 64.0)      # 北岸干地（河床 z<=61 在水下，实测剖面）
CAMP = (10.0, 70.0)

LINES = (
    (496.0, 504.0, '牛妈妈', '相信我，我还会在你身后出现的。'),
    (506.0, 518.0, '牛妈妈', '以后，如果你想妈妈了，就到这棵树下来吧。这儿会有妈妈的影子，也许它，能唤起你的回忆和斗志。'),
    (740.0, 747.0, '牛来', '妈妈……'),
)


class WolvesScene:
    """第四幕场景。"""

    NAME = ACT
    SKY = SKY
    FOG_K = FOG_K
    TINT = TINT

    def __init__(self, seed=MASTER_SEED, grid=192):
        self.timeline = Timeline()
        self.T0 = self.timeline.act_bounds(self.NAME)[0]  # 幕起点（全片秒）
        self.seed = seed
        self.ground = lambda x, z: desert.height_at(x, z, seed)
        self.terrain_md, _ = desert.build_terrain(seed, grid, 1.0)
        self.river_md = desert.build_river(seed)
        self.tree_md = tree_mod.build_crooked_tree(
            TREE_AT[0], TREE_AT[1], self.ground, seed)
        self.calf = Calf()
        self.mother = Quadruped(MOTHER_SPEC)
        self.pack = [Quadruped(WOLF_SPEC) for _ in range(wolves.WOLF_COUNT)]
        self.herd = [Quadruped(MOTHER_SPEC) for _ in range(6)]
        self.cast = CastWorld()
        self.cast.register('niulai')
        self.cast.register('mother')
        for i in range(wolves.WOLF_COUNT):
            self.cast.register(f'wolf{i}')
        # P5-5：狼群行为树正式挂 allin ECS（BrainComponent + BlackboardComponent）
        self._wolf_rig = btree.BrainRig(
            self.cast, [f'wolf{i}' for i in range(wolves.WOLF_COUNT)],
            btree.WOLF_TREE_SPEC)
        for i in range(6):
            self.cast.register(f'herd{i}')
        self._sub = SubtitleOverlay(SubtitleTrack(LINES))
        # 氛围粒子（allin fx）：夜风寒尘，锚在树下战区 z 平面
        self._motes = fx_particles.mote_field(
            seed + 13, z=TREE_AT[1] - 5.0,
            follow=lambda t: (TREE_AT[0] + 2.0, 1.1))
        self._mote_layer = ParticleLayer(self._motes, point_size=2.0)
        # 战斗节拍（固定种子，确定性）
        self.beats = wolves.build_battle_log()
        self.shots = self._build_shots()
        self.use_instancing = True     # 群体戏 GPU 实例化（等价性测试可关）

    # ---------------------------------------------------------------- 走位 --
    def _mother_stamina(self, t):
        """妈妈体力 1.0 -> 0.0（BT charge 条件的世界状态输入，纯函数）。

        300s 总攻起随消耗下降；480s 引开狼群后急坠；700s 牺牲归零。
        """
        # 阶段边界统一来自 brains/phases（world3d fsm 时间轴）
        ph = phases.phase_at(t)
        if ph == 'circle':
            return 1.0
        if ph == 'charge':
            return 1.0 - (t - 300.0) / 180.0 * 0.45
        if ph == 'chase':
            return 0.55 - (t - 480.0) / 220.0 * 0.55
        return 0.0

    def _wolf_pack(self, t):
        """狼群态势（行为树决策，meshes/crowd 两路共用同一上下文）。

        P5-5：决策经**挂 ECS 实体的行为树**（BrainRig）产出——黑板是
        单一事实来源；世界状态：妈妈体力曲线 / 总攻窗(300-480) /
        牺牲段(480-700) / 狼群环心到妈妈的距离；jitter 每 5 只狼
        半径 +3u 出几何纵深。
        """
        mx, mz = self._mother_xy(t)
        center = (TREE_AT[0], TREE_AT[1] - 1.0)
        herd_dist = math.hypot(mx - center[0], mz - center[1])
        inputs = [dict(t=t, mother_stamina=self._mother_stamina(t),
                       herd_dist=herd_dist,
                       assault=phases.assault(t),
                       mother_falling=phases.mother_falling(t),
                       bite_window=t >= 12.0)
                  for _ in range(wolves.WOLF_COUNT)]
        bbs = self._wolf_rig.tick(inputs)
        stances = [bb.get('stance', 'circle') for bb in bbs]
        return wolves.pack_positions(
            t, center=center, stances=stances,
            jitter=lambda i: i % 5 == 0)
    def _mother_xy(self, t):
        """妈妈：守夜(营地) -> 引狼(向河北去) -> 留在树下。"""
        ph = phases.phase_at(t)
        if ph in ('circle', 'charge'):
            return (TREE_AT[0] + 2.5, TREE_AT[1] - 7.0)
        if ph == 'chase':
            u = base.smooth((t - 480.0) / 220.0)
            return (TREE_AT[0] + 2.5 + 26.0 * u, TREE_AT[1] - 7.0 + 6.0 * u)
        # 牺牲后：回到树下（卧）
        return (TREE_AT[0] + 2.0, TREE_AT[1] - 4.0)

    def _mother_mode(self, t):
        ph = phases.phase_at(t)
        if ph in ('circle', 'charge'):
            return 'stand'
        if ph == 'chase':
            return 'run'
        return 'lie'

    # ---------------------------------------------------------------- 镜头 --
    def _build_shots(self):
        tree_c = (TREE_AT[0], self.ground(*TREE_AT) + 4.5, TREE_AT[1])

        def cam_night(u, t):
            c = (CAMP[0], self.ground(*CAMP) + 1.2, CAMP[1])
            ang = 0.9 + 0.2 * math.sin(u * 0.05)
            return base.orbit_eye(c, ang, 20.0, 6.5), c

        def cam_appear(u, t):
            c = tree_c
            ang = 1.4 + 0.3 * math.sin(u * 0.06)
            return base.orbit_eye(c, ang, 24.0, 5.0), c

        def cam_fight(u, t):
            # 总攻：以战斗节拍切换机位（每节拍换一次角度/距离）。
            # 距离必须 > 狼群环半径 + 余量，否则相机扎进狼群（实测踩坑）
            beat = int(u * 1.2) % max(1, len(self.beats))
            ang = 0.4 + 0.9 * math.sin(beat * 1.7)
            dist = 17.0 + 4.0 * math.cos(beat * 2.3)
            c = (TREE_AT[0] + 2.5, self.ground(TREE_AT[0], TREE_AT[1]) + 1.6,
                 TREE_AT[1] - 2.5)
            return base.orbit_eye(c, ang, dist, 4.5), c

        def cam_sacrifice(u, t):
            mx, mz = self._mother_xy(t)
            c = (mx, self.ground(mx, mz) + 1.0, mz)
            ang = 2.4 + 0.2 * math.sin(u * 0.07)
            return base.orbit_eye(c, ang, 7.5, 2.2), c

        def cam_dawn(u, t):
            c = (TREE_AT[0], self.ground(*TREE_AT) + 4.0, TREE_AT[1])
            ang = 0.7 + 0.25 * math.sin(u * 0.05)
            return base.orbit_eye(c, ang, 17.0, 4.5), c

        return [
            base.Shot(0.0, 120.0, cam_night, '夜宿'),
            base.Shot(120.0, 300.0, cam_appear, '狼群现身'),
            base.Shot(300.0, 480.0, cam_fight, '总攻'),
            base.Shot(480.0, 720.0, cam_sacrifice, '母亲牺牲'),
            base.Shot(720.0, T_END, cam_dawn, '黎明回望'),
        ]

    # ---------------------------------------------------------------- 相机 --
    def camera(self, t):
        shot, u = base.pick_shot(self.shots, t)
        eye, tgt = shot.camera(u, t)
        g = self.ground(eye[0], eye[2]) + 1.0
        if eye[1] < g:
            eye = (eye[0], g, eye[2])
        return eye, tgt

    # ---------------------------------------------------------------- 姿装 --
    def meshes(self, t):
        tq = Timeline.quantize(t, perf.ANIM_FPS)
        # 妈妈
        mx, mz = self._mother_xy(t)
        mmode = self._mother_mode(t)
        base.place_quad(self.mother, mx, mz,
                        math.atan2(mz - TREE_AT[1], mx - TREE_AT[0]), self.ground)
        # 牛来：总攻段在妈妈附近奔逃；牺牲段呆立树下；黎明段回望
        if 300.0 <= t < 480.0:
            nx = TREE_AT[0] + 3.0 + 2.0 * math.sin(t * 1.3)
            nz = TREE_AT[1] + 2.0 + 1.5 * math.cos(t * 1.1)
        elif 480.0 <= t < 720.0:
            nx, nz = TREE_AT[0] + 3.5, TREE_AT[1] + 3.0
        else:
            nx, nz = TREE_AT[0] + 4.0, TREE_AT[1] + 5.0
        self.calf.origin = Vec3(nx, self.ground(nx, nz) + 0.61, nz)
        self.calf.yaw = math.atan2(TREE_AT[1] - nz, TREE_AT[0] - nx)
        # 狼群（300s 后进入；总攻后随妈妈引开方向远去）
        # 态势经行为树决策（brains/btree）：世界状态（妈妈体力/总攻窗）驱动
        # circle -> stalk -> charge -> bite -> chase，不再硬编时间阈值。
        pack = self._wolf_pack(t)
        if 480.0 <= t < 700.0:
            # 被引开的狼群追妈妈
            for i, (_, _, yaw, _) in enumerate(pack):
                ang = (i / len(pack)) * math.tau
                pack[i] = (mx + math.cos(ang) * 9.0, mz + math.sin(ang) * 7.0,
                           yaw, 'run')
        for i, (wx, wz, wyaw, wmode) in enumerate(pack):
            if not self.use_instancing:
                base.place_quad(self.pack[i], wx, wz, wyaw, self.ground)
                self.cast.set_pose(f'wolf{i}', wx, self.pack[i].origin.y, wz,
                                   wyaw, mode=wmode)
        self._pack = pack
        # 背景牛群：夜伏（lie）/ 黎明散去（instancing 开时由 crowd() 画）
        herd_mode = 'lie' if t < 720.0 else 'stand'
        if not self.use_instancing:
            for i, q in enumerate(self.herd):
                ang = (i / len(self.herd)) * math.tau
                hx = CAMP[0] + math.cos(ang) * 5.0
                hz = CAMP[1] + math.sin(ang) * 4.0
                base.place_quad(q, hx, hz, -1.7, self.ground)
                self.cast.set_pose(f'herd{i}', hx, q.origin.y, hz, q.yaw,
                                   mode=herd_mode)
        # 妈妈状态事件（牺牲瞬间通过桥接层广播一次）
        if t >= 700.0 and self.cast.entities['mother'].get(
                CastState).state == 'alive':
            self.cast.set_state('mother', 'fallen')
        out = [self.terrain_md, self.river_md, self.tree_md]
        out.extend(self.mother.meshes(tq, mode=mmode, speed=1.2))
        out.extend(self.calf.meshes(tq))
        if not self.use_instancing:
            for i, (_, _, _, wmode) in enumerate(pack):
                if t >= 300.0:
                    out.extend(self.pack[i].meshes(tq, mode=wmode, speed=1.3))
            for q in self.herd:
                out.extend(q.meshes(tq, mode=herd_mode))
        self.cast.set_pose('niulai', nx, self.calf.origin.y, nz, self.calf.yaw)
        self.cast.set_pose('mother', mx, self.mother.origin.y, mz,
                           self.mother.yaw, mode=mmode)
        return out

    def crowd(self, t):
        """群体戏实例化：卧伏牛群 + 狼群（两组同规格同姿态）。"""
        if not self.use_instancing:
            return None
        tq = Timeline.quantize(t, perf.ANIM_FPS)
        groups = []
        # 牛群
        herd_mode = 'lie' if t < 720.0 else 'stand'
        pose = self.herd[0].meshes_identity(tq, mode=herd_mode)
        bases = []
        for i, q in enumerate(self.herd):
            ang = (i / len(self.herd)) * math.tau
            hx = CAMP[0] + math.cos(ang) * 5.0
            hz = CAMP[1] + math.sin(ang) * 4.0
            base.place_quad(q, hx, hz, -1.7, self.ground)
            bases.append(tuple(q._base_matrix()))
            self.cast.set_pose(f'herd{i}', hx, q.origin.y, hz, q.yaw,
                               mode=herd_mode)
        groups.append((pose, bases))
        # 狼群（300s 后进入；480-700s 追妈妈）
        pack = self._wolf_pack(t)
        if 480.0 <= t < 700.0:
            mx, mz = self._mother_xy(t)
            for i, (_, _, yaw, _) in enumerate(pack):
                ang = (i / len(pack)) * math.tau
                pack[i] = (mx + math.cos(ang) * 9.0, mz + math.sin(ang) * 7.0,
                           yaw, 'run')
        if t >= 300.0:
            wmode = pack[0][3]
            pose = self.pack[0].meshes_identity(tq, mode=wmode, speed=1.3)
            bases = []
            for i, (wx, wz, wyaw, _) in enumerate(pack):
                base.place_quad(self.pack[i], wx, wz, wyaw, self.ground)
                bases.append(tuple(self.pack[i]._base_matrix()))
                self.cast.set_pose(f'wolf{i}', wx, self.pack[i].origin.y, wz,
                                   wyaw, mode=wmode)
            groups.append((pose, bases))
        return groups

    # ---------------------------------------------------------------- 粒子 --
    def particles(self, t):
        """氛围粒子层（allin fx）：夜风寒尘。"""
        self._mote_layer.update(t)
        return [self._mote_layer]

    def overlays(self, t):
        return [self._sub.at(t)]
