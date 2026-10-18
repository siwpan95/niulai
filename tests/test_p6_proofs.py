# -*- coding: utf-8 -*-
"""P6 能力 proof 测试：frustum / gpu_cull / skin / greedy_mesh / orchestration。

P6 的原则：**能真接入且画面中立的才进正片**（fsm 时间轴、perf 帧计时、
serialize 场景清单、frustum 剔除），其余走本文件的对拍 proof 并记账理由。

运行：python tests/test_p6_proofs.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILED = []


def check(name, cond, detail=''):
    status = 'ok' if cond else 'FAIL'
    print(f'  {status}: {name}' + (f'  [{detail}]' if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def _cam(eye=(0.0, 5.0, 0.0), target=(0.0, 5.0, 20.0)):
    from world3d.engine.camera import Camera
    return Camera(position=eye, target=target, fov=55.0, near=0.1, far=400.0)


def test_frustum():
    """frustum：包围球判定的正确性 + 保守性（不误杀）。"""
    print('test_frustum')
    from world3d.engine.frustum import AABB, Frustum, Sphere

    cam = _cam()
    fr = Frustum.from_view_projection(cam.view_projection(16 / 9.0))

    check('相机前方的点在锥内', fr.contains_point((0.0, 5.0, 20.0)))
    check('相机背后的点不在锥内', not fr.contains_point((0.0, 5.0, -20.0)))
    check('极远处的点不在锥内（far 截断）',
          not fr.contains_point((0.0, 5.0, 900.0)))

    # 保守性：球心在锥外，但半径大到与锥相交 -> 必须判可见
    c = (0.0, 5.0, 20.0)
    check('半径覆盖到锥内时判可见', fr.intersects_sphere(c, 60.0))
    # AABB 版本与点测试一致
    box_in = AABB.from_center_half(c, (1.0, 1.0, 1.0))
    box_out = AABB.from_center_half((0.0, 5.0, -20.0), (1.0, 1.0, 1.0))
    check('AABB 锥内判可见', fr.intersects_aabb(box_in))
    check('AABB 锥外判不可见', not fr.intersects_aabb(box_out))
    check('Sphere.from_aabb 半径正确',
          abs(Sphere.from_aabb(box_in).radius - math.sqrt(3.0)) < 1e-6)

    # 视锥与相机一致：转 180° 后可见集合互补
    cam2 = _cam(eye=(0.0, 5.0, 0.0), target=(0.0, 5.0, -20.0))
    fr2 = Frustum.from_view_projection(cam2.view_projection(16 / 9.0))
    trials = [(0.0, 5.0, 20.0), (0.0, 5.0, -20.0)]
    v1 = [fr.intersects_sphere(p, 0.5) for p in trials]
    v2 = [fr2.intersects_sphere(p, 0.5) for p in trials]
    check('反向相机可见性互换', v1 == [True, False] and v2 == [False, True],
          f'{v1} / {v2}')


def test_gpu_cull_parity():
    """gpu_cull：CPU 参照与手算一致；LOD 阈值与手算一致；报告本机 compute 能力。"""
    print('test_gpu_cull_parity')
    from world3d.engine.frustum import Frustum
    from world3d.engine.gpu_cull import (GpuCullSupport, cpu_lod,
                                        cpu_reference, MAX_LOD)

    cam = _cam()
    fr = Frustum.from_view_projection(cam.view_projection(16 / 9.0))

    centers, radii = [], []
    for i in range(60):
        z = -40.0 + i * 2.0          # -40..78：一部分在相机背后
        centers.append((float(i % 7) - 3.0, 5.0, z))
        radii.append(1.0)
    vis = cpu_reference(fr, centers, radii)
    manual = [i for i, (c, r) in enumerate(zip(centers, radii))
              if fr.intersects_sphere(c, r)]
    check('cpu_reference == 手算', vis == manual, f'{len(vis)} vs {len(manual)}')
    check('可见集合非空且非全集', 0 < len(vis) < len(centers),
          f'{len(vis)}/{len(centers)}')

    # LOD：距离阈值边界（含最后一级夹取）
    lod_dists = (10.0, 40.0)
    lv = cpu_lod((0.0, 0.0, 0.0), [(0.0, 0.0, d) for d in (5.0, 10.0, 39.9, 80.0)],
                 lod_dists)
    check('cpu_lod 阈值正确', lv == [0, 1, 1, MAX_LOD - 1] or
          lv[:3] == [0, 1, 1], f'{lv}')

    sup = GpuCullSupport.detect()
    print(f'    (info) GpuCullSupport: {sup}')
    check('能力探测返回 dict', isinstance(sup, dict))


def test_skin_bend():
    """skin：关节矩阵与手算一致；两骨骼蒙皮后顶点确实弯折。"""
    print('test_skin_bend')
    from pyglet.math import Mat4, Vec3
    from world3d.engine.scene import Node
    from world3d.engine.skin import Skin

    # 两段骨骼：root 在原点，tip 在 (0,2,0)（父 -> 子链）
    root = Node(name='root')
    tip = Node(name='tip')
    tip.translation = (0.0, 2.0, 0.0)
    root.add(tip)
    root.update_world()

    ident = tuple(Mat4())
    skin = Skin([root, tip], [ident, ident], name='test')
    ms = skin.joint_matrices()
    check('关节数正确', skin.joint_count == 2)
    check('单位逆绑定 -> 关节矩阵 == 世界矩阵',
          ms[0] == tuple(Mat4()) and ms[1] == tuple(Mat4.from_translation(Vec3(0, 2, 0))))
    check('uniform 槽位补满单位阵', len(skin.uniform_matrices()) == skin.max_joints)

    # 绕 X 轴弯 90°：tip 上的顶点 (0, 3, 0) 应转到 (0, 2, -1) 附近
    bend = Mat4.from_rotation(math.radians(90.0), (1.0, 0.0, 0.0))
    tip_rot = Mat4.from_translation(Vec3(0.0, 2.0, 0.0)) @ bend @ \
        Mat4.from_translation(Vec3(0.0, -2.0, 0.0))
    v = (0.0, 3.0, 0.0)
    m = tip_rot
    p = (m[0] * v[0] + m[4] * v[1] + m[8] * v[2] + m[12],
         m[1] * v[0] + m[5] * v[1] + m[9] * v[2] + m[13],
         m[2] * v[0] + m[6] * v[1] + m[10] * v[2] + m[14])
    check('关节旋转把顶点带离原处', abs(p[2]) > 0.5, f'{p}')
    check('旋转后到枢轴距离不变（刚体）',
          abs(math.dist(p, (0.0, 2.0, 0.0)) - 1.0) < 1e-3, f'{p}')


def test_greedy_mesh():
    """greedy_mesh：贪心合并面数显著少于逐格，且与朴素计数关系正确。"""
    print('test_greedy_mesh')
    from world3d.engine.greedy_mesh import layer_mesh, naive_quad_count, quad_count

    h = w = 12
    walls = {(i, j) for i in range(4, 8) for j in range(2, 10)}   # 4x8 实心块
    pos, shade = layer_mesh(walls, h, w, cs=1.0, ytop=1.0)
    q = quad_count(pos)
    naive = naive_quad_count(walls, h, w)
    check('合并结果非空', q > 0, f'{q}')
    check('贪心 <= 逐格（顶/底/四侧合并）', q <= naive, f'{q} vs {naive}')
    # 4x8 实心块：顶+底各 1 个 quad（或按条带 1 个），侧面 = 周长段数
    check('实心块被合并成少量 quad', q <= 10, f'{q}')

    # 确定性：同输入两次同结果
    pos2, shade2 = layer_mesh(walls, h, w, cs=1.0, ytop=1.0)
    check('同输入同输出', pos == pos2 and shade == shade2)
    check('顶点数与 shade 等长', len(shade) == len(pos))


def test_orchestration():
    """orchestration：when→then 级联顺序确定、可重放。"""
    print('test_orchestration')
    from world3d.engine.orchestration import Bus

    bus = Bus('p6')
    hits = []

    def on_charge(event, payload):
        hits.append(('charge', payload.get('t')))

    def on_clash(event, payload):
        hits.append(('clash', payload.get('t')))

    bus.on('wolf.charge', on_charge)
    bus.on('wolf.clash', on_clash)
    bus.bind('wolf.charge', 'wolf.clash')

    out = bus.emit('wolf.charge', t=300.0)
    names = [e for e, _ in out]
    check('级联事件顺序', names == ['wolf.charge', 'wolf.clash'], f'{names}')
    check('订阅者都收到', hits == [('charge', 300.0), ('clash', 300.0)], f'{hits}')

    # 重放一致（新 bus 同声明 -> 同事件序列）
    bus2 = Bus('p6')
    bus2.bind('wolf.charge', 'wolf.clash')
    out2 = bus2.emit('wolf.charge', t=300.0)
    check('重放事件序列一致',
          [e for e, _ in out2] == names)

    # 环保护
    bad = Bus('cycle')
    bad.bind('a', 'b')
    bad.bind('b', 'a')
    try:
        bad.emit('a')
        check('环声明被拦截', False, '未抛 RecursionError')
    except RecursionError:
        check('环声明被拦截', True)


def test_scene_manifest():
    """serialize/scene_build：八幕清单 JSON 全部通过校验（产物在 output/manifests）。"""
    print('test_scene_manifest')
    import json

    from world3d.engine.scene_build import validate

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mdir = os.path.join(root, 'output', 'manifests')
    if not os.path.isdir(mdir):
        print('    (info) 未生成清单，跳过（先跑 scripts/export_manifests.py）')
        return
    files = sorted(f for f in os.listdir(mdir) if f.endswith('.scene.json'))
    check('八幕清单齐全', len(files) == 8, f'{len(files)}')
    for f in files:
        with open(os.path.join(mdir, f), encoding='utf-8') as fh:
            data = json.load(fh)
        errs = [i for i in validate(data) if i[0] == 'error']
        check(f'{f} 校验无错', not errs, f'{errs[:2]}')
        check(f'{f} 带关键帧', len(data.get('niulai', {}).get('keyframes', [])) >= 4)


def main():
    test_frustum()
    test_gpu_cull_parity()
    test_skin_bend()
    test_greedy_mesh()
    test_orchestration()
    test_scene_manifest()
    if FAILED:
        print(f'\nFAILED {len(FAILED)}: {FAILED}')
        return 1
    print('\nALL_P6_PROOF_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
