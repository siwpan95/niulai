# -*- coding: utf-8 -*-
"""桥接层：world3d 侧幕事件 ↔ allin_engine EventBus（P0 最小可用）。

数据流铁律（计划 §三.4）：**单一事实来源 = allin 世界状态**；
world3d 每帧从 ECS 快照读姿态。P0 只把事件扇出接上，实体快照 P1 接入。
"""
from allin_engine.core.event_bus import EventBus

# 幕事件名（niulai 自定义，与原片幕结构对应）
EV_ACT_ENTER = 'niulai.act.enter'        # payload: {'act': name, 't': t}
EV_ACT_EXIT = 'niulai.act.exit'
EV_CAST_STATE = 'niulai.cast.state'      # payload: {'who': name, 'state': str, 't': t}


class Bridge:
    """niulai 事件 -> allin EventBus 的最小适配。

    用法：bridge.emit(EV_ACT_ENTER, {...}) —— 内部监听者与 allin 订阅者同时收到。
    """

    def __init__(self, bus=None):
        self.bus = bus if bus is not None else EventBus()
        self._local = {}
        self.log = []                      # 发射历史（测试/审计用，有界）

    def on(self, name, callback):
        """订阅 niulai 事件（仅本地表）。

        注意：**不要**再 `bus.subscribe` 同一个 callback —— emit 时会先
        `bus.emit` 再走本地表，同一个回调会被投递两次。要收 allin 侧事件，
        直接 `bridge.bus.subscribe(name, cb)`。
        """
        self._local.setdefault(name, []).append(callback)

    def emit(self, name, payload=None):
        self.log.append((name, payload))
        if len(self.log) > 4096:
            self.log = self.log[-2048:]
        self.bus.emit(name, payload or {})
        for cb in self._local.get(name, ()):
            cb(payload or {})
