# -*- coding: utf-8 -*-
"""全片主时间轴：固定帧率 + 固定步长 + 确定性量化。

三条铁律：
1. **一切姿态是 t 的纯函数**——不允许跨帧累积状态（除镜头平滑等显式声明的例外，
   且平滑量也必须由 t 解析求出，见 acts/act0_prologue.py 的相机）。这是离线逐帧
   渲染可复现（同 seed 两次渲染逐帧 md5 相同）的根基。
2. **粗粝感量化**：动画按 12fps 量化（quantize），复刻原片"僵硬卡顿"的质感；
   量化是确定性的（floor），不引入浮点漂移。
3. **分幕边界**在 ACTS 里单一事实来源；测试钉住"边界连续覆盖全片"。
"""
import math

from . import FPS, MASTER_SEED, TOTAL_DURATION

# 分幕表：(起始秒, 结束秒, 说明)。顺序即幕序；边界必须首尾相接（测试断言）。
# 时长分配依据 docs/分幕脚本.md（对照原片 86 分钟结构）。
ACTS = (
    ("act0_prologue", 0.0, 360.0, "序幕·荒漠飞雀：云玎 5 分钟长镜头，落在牛来身旁入梦"),
    ("act1_stand", 360.0, 660.0, "第一幕·站不起来：草原清晨，初生牛犊双腿无力"),
    ("act2_migration", 660.0, 1380.0, "第二幕·迁徙与过溪：牛群迁徙，惧蛇慌乱过溪"),
    ("act3_leopard", 1380.0, 2100.0, "第三幕·豹拉：结识、分奶、约法三章、分离"),
    ("act4_wolves", 2100.0, 3180.0, "第四幕·狼袭与母亡：夜袭总攻，妈妈留在歪脖子树"),
    ("act5_finale", 3180.0, 4080.0, "第五幕·传承与决战：岁月更迭，豹拉断后，战吼引开盗猎者"),
    ("act6_wake", 4080.0, 4800.0, "第六幕·梦醒而立：惊醒，奋力站起，奔向牛群见父亲"),
    ("act7_credits", 4800.0, 5160.0, "片尾：大团圆定格 + 字幕 + 片尾曲《雨后清风有香》"),
)

ACT_NAMES = tuple(name for name, _, _, _ in ACTS)


class Timeline:
    """主时间轴：帧号 <-> 时刻、分幕边界、粗粝量化。"""

    def __init__(self, fps=FPS, seed=MASTER_SEED, duration=TOTAL_DURATION):
        self.fps = fps
        self.seed = seed
        self.duration = duration

    def t_of(self, frame):
        """帧号 -> 时刻（秒）。"""
        return frame / float(self.fps)

    def frame_of(self, t):
        """时刻 -> 帧号（向下取整，与 t_of 互为近似逆）。"""
        return int(math.floor(t * self.fps))

    @staticmethod
    def quantize(t, anim_fps=12.0):
        """粗粝量化：把连续时刻吸附到 anim_fps 的帧栅格（floor，确定性）。

        原片"人物动作僵硬卡顿"来自低帧率手搓动画；我们用 12fps 栅格复刻它。
        """
        return math.floor(t * anim_fps) / anim_fps

    def act_bounds(self, name):
        for act_name, start, end, _ in ACTS:
            if act_name == name:
                return start, end
        raise KeyError(f"unknown act: {name!r}")

    def act_frames(self, name):
        """该幕的帧号区间 [start_frame, end_frame)（半开）。"""
        start, end = self.act_bounds(name)
        return self.frame_of(start), self.frame_of(end)

    def act_at(self, t):
        """时刻 -> 幕名（闭区间判定；超出全片范围抛错）。"""
        if not (0.0 <= t <= self.duration):
            raise ValueError(f"t={t} out of film range [0, {self.duration}]")
        for name, start, end, _ in ACTS:
            if start <= t < end:
                return name
        return ACTS[-1][0]      # t == duration 落在最后一幕的闭端
