# -*- coding: utf-8 -*-
"""CastWorld：allin ECS 包装（角色实体注册表 + Transform 组件 + 事件桥）。

数据流铁律（计划 §三.4）：**单一事实来源 = allin 世界状态**；
world3d 每帧从 snapshot() 读姿态（单向，不写回）。
ECS 在这里承担"谁在场、各自什么状态"的账本；运动学本身是确定性
纯函数（migration/wolves 模块），ECS 镜像之 —— 这样离线逐帧渲染
不需要 O(n²) 的 dt 重放。
"""
from allin_engine.core.ecs import Component, Entity, World

from ..bridge.events import EV_CAST_STATE, Bridge


class Transform(Component):
    """角色世界姿态：位置 + 航向 + 步态相位 + 模式。"""

    def __init__(self, x=0.0, y=0.0, z=0.0, yaw=0.0, mode='stand', phase=0.0):
        self.x, self.y, self.z = x, y, z
        self.yaw = yaw
        self.mode = mode
        self.phase = phase


class CastState(Component):
    """角色叙事状态（供事件/测试查询）：alive / fallen / separated。"""

    def __init__(self, state='alive'):
        self.state = state


class CastWorld:
    """角色世界。who -> Entity；set_pose 更新 Transform；snapshot 输出快照。"""

    def __init__(self, bridge=None):
        self.world = World()
        self.bridge = bridge if bridge is not None else Bridge()
        self.entities = {}

    def register(self, who, x=0.0, y=0.0, z=0.0, yaw=0.0, mode='stand'):
        e = self.world.create_entity(who)
        e.add(Transform(x, y, z, yaw, mode))
        e.add(CastState())
        self.entities[who] = e
        return e

    def set_pose(self, who, x=None, y=None, z=None, yaw=None, mode=None):
        t = self.entities[who].get(Transform)
        if x is not None:
            t.x = x
        if y is not None:
            t.y = y
        if z is not None:
            t.z = z
        if yaw is not None:
            t.yaw = yaw
        if mode is not None:
            t.mode = mode

    def set_state(self, who, state):
        self.entities[who].get(CastState).state = state
        self.bridge.emit(EV_CAST_STATE, {'who': who, 'state': state})

    def get_pose(self, who):
        t = self.entities[who].get(Transform)
        return t.x, t.y, t.z, t.yaw, t.mode

    def snapshot(self):
        """全角色姿态快照 {who: (x, y, z, yaw, mode)}（场景每帧读这个）。"""
        return {who: self.get_pose(who) for who in self.entities}

    def __contains__(self, who):
        return who in self.entities

    def __len__(self):
        return len(self.entities)
