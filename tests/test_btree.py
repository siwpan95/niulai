# -*- coding: utf-8 -*-
"""行为树测试（allin ai/decision 接入）： stance 确定性 + 转移合理性。

全部离线：不联网、不需要 ffmpeg、不需要渲染 —— 纯函数断言。

运行：python tests/test_btree.py（或 python -m pytest tests/）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from niulai.brains import btree  # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    status = 'ok' if cond else 'FAIL'
    print(f'  {status}: {name}' + (f'  [{detail}]' if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def test_wolf_determinism():
    print('test_wolf_determinism')
    cases = [(0.0, 1.0, 40.0, False, False),
             (15.0, 1.0, 10.0, False, False),
             (350.0, 0.4, 8.0, True, False),
             (600.0, 0.1, 6.0, False, True),
             (900.0, 0.0, 30.0, False, False)]
    for c in cases:
        a = btree.wolf_stance(*c)
        b = btree.wolf_stance(*c)
        check(f'同输入同 stance {c[:2]}', a == b, f'{a} != {b}')
    # stances 列表：同 t 同状态 -> 全群同 stance（实例化等价性前提）
    ss = btree.wolf_stances(20.0, count=10)
    check('stances 长度 == count', len(ss) == 10)
    check('全群同 stance', len(set(ss)) == 1, f'{ss}')


def test_wolf_transitions():
    print('test_wolf_transitions')
    # 远处无威胁 -> 环伺
    check('远处环伺', btree.wolf_stance(5.0, herd_dist=80.0) == 'circle')
    # 咬住窗（t>=12）-> 撕咬
    check('咬住窗撕咬', btree.wolf_stance(20.0) == 'bite')
    # 总攻 + 体力充沛 -> 潜行
    check('总攻初潜行', btree.wolf_stance(301.0, mother_stamina=1.0,
                                        assault=True) == 'stalk')
    # 总攻 + 体力跌破 -> 冲锋
    check('总攻冲锋', btree.wolf_stance(350.0, mother_stamina=0.4,
                                      assault=True) == 'charge')
    # 妈妈牺牲段 -> 追猎
    check('牺牲段追猎', btree.wolf_stance(600.0, mother_falling=True)
          == 'chase')
    # 非总攻 + 体力低 不冲锋（条件与运算）
    check('非总攻不冲锋', btree.wolf_stance(100.0, mother_stamina=0.1)
          != 'charge')


def test_cow_mode():
    print('test_cow_mode')
    check('无蛇照常走', btree.cow_mode(100.0, None, (10.0, 10.0)) == 'walk')
    check('蛇远照常走', btree.cow_mode(100.0, (40.0, 40.0), (10.0, 10.0))
          == 'walk')
    check('蛇近惊呆立定', btree.cow_mode(430.0, (12.0, 44.0), (13.0, 44.0))
          == 'stand')
    check('蛇在警觉带仍走', btree.cow_mode(430.0, (12.0, 44.0), (28.0, 44.0))
          == 'walk')
    # 确定性
    a = btree.cow_mode(430.0, (12.0, 44.0), (13.0, 44.0))
    b = btree.cow_mode(430.0, (12.0, 44.0), (13.0, 44.0))
    check('同输入同 mode', a == b)


def test_ecs_mount():
    print('test_ecs_mount')
    from allin_engine.core.ecs import World
    from niulai.brains.world import CastWorld
    from niulai.brains import btree as bt
    cw = CastWorld()
    for i in range(3):
        cw.register(f'wolf{i}')
    rig = bt.BrainRig(cw, ['wolf0', 'wolf1', 'wolf2'], bt.WOLF_TREE_SPEC)
    inputs = [dict(t=350.0, mother_stamina=0.4, herd_dist=8.0,
                   assault=True, mother_falling=False, bite_window=True)
              for _ in range(3)]
    bbs = rig.tick(inputs)
    stances = [bb.get('stance') for bb in bbs]
    check('ECS 挂载产出 stance', all(s == 'charge' for s in stances),
          f'{stances}')
    check('与纯函数一致', stances == [bt.wolf_stance(
        350.0, 0.4, 8.0, True, False)] * 3)
    # 黑板是实体组件（单一事实来源）
    bb0 = cw.entities['wolf0'].get(
        __import__('allin_engine.ai.decision.brain',
                   fromlist=['BlackboardComponent']).BlackboardComponent
    ).blackboard
    check('黑板挂在实体上', bb0.get('stance') == 'charge')
    # 确定性：同输入再 tick 同结果
    bbs2 = rig.tick(inputs)
    check('重复 tick 同结果', [bb.get('stance') for bb in bbs2] == stances)


def main():
    test_wolf_determinism()
    test_wolf_transitions()
    test_cow_mode()
    test_ecs_mount()
    if FAILED:
        print(f'\nFAILED {len(FAILED)}: {FAILED}')
        return 1
    print('\nALL_BTREE_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
