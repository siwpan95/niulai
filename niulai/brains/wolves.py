# -*- coding: utf-8 -*-
"""狼群 + 夜袭战斗节拍。

两层：
1. **态势纯函数** pack_positions(t_local, phase)：狼群环形逼近 -> 冲锋 -> 撕咬后退，
   全部是 t 的纯函数（确定性）；
2. **战斗节拍** build_battle_log()：用 allin CombatEngine 跑一场**固定种子的
   无头卡牌战斗**，log_cb 收集事件文本 -> [(beat_t, text)] 节拍表。
   节拍表驱动第四幕的编排时机（每次冲撞/防御/伤害 = 一个镜头节拍）。
   随机源已播种（random.seed），同种子两次运行业拍表逐字相同。
"""
import math
import random

from allin_engine.systems.combat.card import Card
from allin_engine.systems.combat.combat_engine import CombatEngine
from allin_engine.systems.combat.enemy import Enemy, EnemyInstance

WOLF_COUNT = 10                    # 8-12 只（全哥口径）
BATTLE_SEED = 20260805

# 夜袭三阶段（秒）
PHASE_CIRCLE, PHASE_CHARGE, PHASE_BITE = 0.0, 6.0, 12.0
PACK_RADIUS = 16.0


def pack_positions(t_local, center=(10.0, 52.0), count=WOLF_COUNT):
    """t_local -> [(x, z, yaw)] 狼位（环形散布 + 阶段行为）。

    circle：绕圆心徘徊；charge：圆心收缩；bite：最近目标撕咬后跳开。
    """
    cx, cz = center
    out = []
    for i in range(count):
        ang = (i / count) * math.tau + 0.6 * math.sin(t_local * 0.5 + i)
        if t_local < PHASE_CHARGE:
            r = PACK_RADIUS + 3.0 * math.sin(t_local * 0.8 + i * 1.7)
            mode = 'walk'
        elif t_local < PHASE_BITE:
            r = PACK_RADIUS - (t_local - PHASE_CHARGE) * 1.6
            mode = 'run'
        else:
            k = (t_local - PHASE_BITE) * 0.9
            r = max(3.0, PACK_RADIUS - 6.0 * 1.6 - 2.0 * math.sin(k + i))
            mode = 'run'
        r = max(2.5, r)
        x = cx + math.cos(ang) * r
        z = cz + math.sin(ang) * r * 0.7
        out.append((x, z, ang + math.pi, mode))
    return out


def build_battle_log():
    """固定种子无头战斗 -> [(beat_index, text)]。确定性（random 已播种）。"""
    random.seed(BATTLE_SEED)
    engine = CombatEngine()
    enemy = EnemyInstance(Enemy('wolf_king', '狼王', hp=64, max_hp=64))
    deck = [Card(id=f'jiao{i}', name=f'角击{i}', ap_cost=1,
                 damage=8 + (i % 3) * 2, block=2 + (i % 2) * 2)
            for i in range(10)]
    log = []
    state = engine.start_combat(60, 60, 30, 30, enemy, deck,
                                log_cb=log.append)
    # 固定出牌序列（索引循环），直到分出胜负
    hand_cycle = [0, 1, 2, 1, 0, 2]
    turn = 0
    while not (state.check_victory() or state.check_defeat()) and turn < 40:
        for idx in hand_cycle:
            if state.check_victory() or state.check_defeat():
                break
            state.play_card(idx % max(1, len(state.hand)))
        state.end_player_turn()
        turn += 1
    beats = [(i, txt) for i, txt in enumerate(log)]
    engine.end_combat()
    return beats


def beats_at(beats, t_local, beats_per_sec=1.0):
    """t_local 时刻应显示的节拍文本（无则 None）。"""
    idx = int(t_local * beats_per_sec)
    if 0 <= idx < len(beats):
        return beats[idx][1]
    return None
