# -*- coding: utf-8 -*-
"""夜袭阶段：world3d ``fsm`` 时间轴状态机（P6）。

原先 act4 把「总攻窗 / 引开窗」写成散落的
``300.0 <= t < 480.0``、``480.0 <= t < 700.0`` —— 同一个时间轴在
行为树输入、妈妈走位、狼群节奏三处各写了一遍，改一处必漏两处。

现在时间轴只有一份声明（``NIGHT_KEYS``），由 world3d 的
``fsm.machine_from_keys`` 编译成状态机，其余位置全部走 ``phase_at(t)``。
语义与旧阈值**逐点等价**（tests/test_p6_proofs.py 用 t=0..1320 全扫对拍）。

记账：``Machine`` 同时支持事件驱动（``fire(event)``），本片是线性时间轴、
无分支，故只取时间轴形态；事件接口留给交互场景。
"""
from world3d.engine.fsm import machine_from_keys

# 阶段时间轴（秒，幕内时间）：环伺 -> 总攻 -> 引开 -> 守灵
NIGHT_KEYS = [
    (0.0, 'circle'),
    (300.0, 'charge'),
    (480.0, 'chase'),
    (700.0, 'grief'),
]

NIGHT = machine_from_keys(NIGHT_KEYS, name='act4_night')

ASSAULT = 'charge'          # 总攻窗（狼群扑向牛群）
CHASE = 'chase'             # 妈妈引开狼群


def phase_at(t):
    """t -> 阶段名（纯查询：每个 t 都落在某个窗口内）。"""
    return NIGHT.at(t)


def assault(t):
    """总攻窗：旧口径 ``300.0 <= t < 480.0``。"""
    return phase_at(t) == ASSAULT


def mother_falling(t):
    """妈妈引开/体力急坠窗：旧口径 ``480.0 <= t < 700.0``。"""
    return phase_at(t) == CHASE
