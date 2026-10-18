# -*- coding: utf-8 -*-
"""行为树决策：allin-engine ai/decision 接入（狼群态势 / 牛群受惊）。

把原本硬编在时间阈值里的群体决策，升级为**数据驱动的行为树**：

- spec 用 allin `build_node` 声明式构造（sequence/selector/condition/action），
  树是数据 → 可单测、可审计（test_btree.py 钉住关键转移）；
- 每帧 tick 一次，动作节点只往 Blackboard 写 stance/mode（瞬时完成，
  无 RUNNING 跨帧状态）→ **stance 是 (t, 世界状态) 的纯函数**，
  不破坏本工程"姿态 = t 纯函数"的确定性铁律；
- 决策与几何分离：本模块只产 stance/mode，几何仍在 wolves/migration。

接入点：
- act4 狼群：`wolf_stance(t, mother_stamina, herd_dist, assault, ...)`
- act2 牛群：`cow_mode(i, t, snake_xy)`（蛇逼惊呆：walk -> stand）

输入口径（全部纯函数，无随机源/墙钟）：
- mother_stamina：妈妈体力 1.0 -> 0.0（act4 场景给定曲线）；
- herd_dist：狼群环心到牛群/妈妈的距离；
- assault：总攻窗（战斗节拍驱动的布尔）。
"""

from allin_engine.ai.decision.behavior_tree import BehaviorTree, Blackboard, \
    build_node

# ---------------------------------------------------------------- 狼群 --
# 优先级（selector 自上而下）：
#   1. 妈妈体力耗尽且进入牺牲段 -> 追猎（chase，act4 另做几何覆盖）
#   2. 总攻窗 + 妈妈体力跌破阈值 -> 冲锋（charge）
#   3. 总攻窗 -> 潜行逼近（stalk）
#   4. 咬住窗（t >= 12s，原 PHASE_BITE 口径）-> 撕咬（bite）
#   5. 白天/远处 -> 环伺（circle）
WOLF_TREE_SPEC = {
    'type': 'selector', 'name': 'wolf', 'children': [
        {'type': 'sequence', 'name': 'hunt_falling', 'children': [
            {'type': 'condition', 'key': 'mother_falling', 'op': 'truthy'},
            {'type': 'action', 'kind': 'set', 'key': 'stance',
             'value': 'chase'}]},
        {'type': 'sequence', 'name': 'charge', 'children': [
            {'type': 'condition', 'key': 'assault', 'op': 'truthy'},
            {'type': 'condition', 'key': 'mother_stamina', 'op': 'le',
             'value': 0.95},
            {'type': 'action', 'kind': 'set', 'key': 'stance',
             'value': 'charge'}]},
        {'type': 'sequence', 'name': 'stalk', 'children': [
            {'type': 'condition', 'key': 'assault', 'op': 'truthy'},
            {'type': 'action', 'kind': 'set', 'key': 'stance',
             'value': 'stalk'}]},
        {'type': 'sequence', 'name': 'bite', 'children': [
            {'type': 'condition', 'key': 'bite_window', 'op': 'truthy'},
            {'type': 'action', 'kind': 'set', 'key': 'stance',
             'value': 'bite'}]},
        {'type': 'sequence', 'name': 'close_in', 'children': [
            {'type': 'condition', 'key': 'herd_dist', 'op': 'lt',
             'value': 30.0},
            {'type': 'action', 'kind': 'set', 'key': 'stance',
             'value': 'stalk'}]},
        {'type': 'action', 'kind': 'set', 'key': 'stance', 'value': 'circle'},
    ]}

# ---------------------------------------------------------------- 牛群 --
# 蛇逼近（ act2 渡口戏）：距蛇 < 9u 惊呆立定（stand）；< 20u 警觉但仍走；
# 其余照常行进。原片节拍：蛇逼近 -> 慌乱跳过小溪（牛来）/ 牛群止步。
COW_TREE_SPEC = {
    'type': 'selector', 'name': 'cow', 'children': [
        {'type': 'sequence', 'name': 'startle', 'children': [
            {'type': 'condition', 'key': 'snake_dist', 'op': 'lt',
             'value': 9.0},
            {'type': 'action', 'kind': 'set', 'key': 'mode',
             'value': 'stand'}]},
        {'type': 'sequence', 'name': 'alert', 'children': [
            {'type': 'condition', 'key': 'snake_dist', 'op': 'lt',
             'value': 20.0},
            {'type': 'action', 'kind': 'set', 'key': 'mode',
             'value': 'walk'}]},
        {'type': 'action', 'kind': 'set', 'key': 'mode', 'value': 'walk'},
    ]}

_WOLF_BT = BehaviorTree(build_node(WOLF_TREE_SPEC))
_COW_BT = BehaviorTree(build_node(COW_TREE_SPEC))


def _tick(tree, data):
    """纯函数 tick：新 Blackboard -> bind -> tick -> 读结果。"""
    bb = Blackboard(dict(data))
    tree.bind(bb)
    tree.tick()
    return bb


def wolf_stance(t, mother_stamina=1.0, herd_dist=999.0, assault=False,
                mother_falling=False, bite_window=None):
    """t -> 'circle' | 'stalk' | 'charge' | 'bite' | 'chase'（纯函数）。

    世界状态输入：妈妈体力 / 狼群-牛群距离 / 总攻窗 / 妈妈牺牲段。
    """
    if bite_window is None:
        bite_window = t >= 12.0            # 原 wolves.PHASE_BITE 口径
    bb = _tick(_WOLF_BT, {
        't': float(t),
        'mother_stamina': float(mother_stamina),
        'herd_dist': float(herd_dist),
        'assault': bool(assault),
        'mother_falling': bool(mother_falling),
        'bite_window': bool(bite_window),
    })
    return bb.get('stance', 'circle')


def cow_mode(t, snake_xy, cow_xy):
    """蛇逼近反应 -> 'walk' | 'stand'（纯函数；蛇不在场时恒 walk）。"""
    if snake_xy is None:
        return 'walk'
    dx = cow_xy[0] - snake_xy[0]
    dz = cow_xy[1] - snake_xy[1]
    dist = (dx * dx + dz * dz) ** 0.5
    bb = _tick(_COW_BT, {'t': float(t), 'snake_dist': dist})
    return bb.get('mode', 'walk')


def wolf_stances(t, mother_stamina=1.0, herd_dist=999.0, assault=False,
                 mother_falling=False, count=1):
    """t -> [stance] * count（同 t 同世界状态 -> 全群同 stance）。"""
    s = wolf_stance(t, mother_stamina, herd_dist, assault, mother_falling)
    return [s] * count
