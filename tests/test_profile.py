# -*- coding: utf-8 -*-
"""渲染 profile 测试：默认 raw 铁律 + enhanced 确定性 + 场景协议。

铁律（docs/增强规划_P3.md §三）：粗粝是**设定**不是缺陷 —— profile
默认 raw，enhanced 是显式 opt-in 的引擎能力展示，且不得破坏确定性。

运行：python tests/test_profile.py（渲染部分走 PNG 路径，不需要 ffmpeg）
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

FAILED = []


def check(name, cond, detail=''):
    status = 'ok' if cond else 'FAIL'
    print(f'  {status}: {name}' + (f'  [{detail}]' if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def test_registry():
    print('test_registry')
    sys.path.insert(0, ROOT)
    from niulai.pipeline.profile import get_profile
    raw = get_profile('raw')
    check('默认 raw', raw.name == 'raw')
    check('raw 无 wboit/bloom', not raw.wboit and not raw.bloom)
    enh = get_profile('enhanced')
    check('enhanced 开 wboit+bloom', enh.wboit and enh.bloom)
    try:
        get_profile('nope')
        check('未知名抛错', False)
    except ValueError:
        check('未知名抛错', True)


def test_scene_protocol():
    print('test_scene_protocol')
    sys.path.insert(0, ROOT)
    from niulai.acts.act2_migration import MigrationScene
    from niulai.pipeline.profile import get_profile
    sc = MigrationScene()
    sc.set_profile(get_profile('raw'))
    meshes_raw = sc.meshes(100.0)
    check('raw 河面在 meshes（不透明）',
          any(len(m.positions) > 1000 for m in meshes_raw))
    check('raw water() 空', sc.water(100.0) == [])
    sc.set_profile(get_profile('enhanced'))
    meshes_enh = sc.meshes(100.0)
    check('enhanced 河面移出 meshes',
          sum(len(m.positions) for m in meshes_enh)
          < sum(len(m.positions) for m in meshes_raw))
    water = sc.water(100.0)
    check('enhanced water() 给河面', len(water) == 1 and len(water[0][0]) > 0)
    check('water alpha 半透明', 0.0 < water[0][2] < 1.0)


def _render(out_dir, profile, frames):
    cmd = [sys.executable, '-m', 'niulai', 'render',
           '--act', 'act2_migration', '--start', str(frames[0]),
           '--end', str(frames[-1] + 1), '--size', '320x200',
           '--out', out_dir, '--png', '--profile', profile,
           '--manifest', os.path.join(out_dir, 'manifest.json')]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f'render {profile} failed:\n{proc.stdout}\n'
                           f'{proc.stderr}')
    with open(os.path.join(out_dir, 'manifest.json'), encoding='utf-8') as f:
        return json.load(f)['frames']


def test_enhanced_determinism():
    print('test_enhanced_determinism')
    # 跃溪名场面附近（河面入画的机位）
    frames = [32400, 32401, 32402]
    with tempfile.TemporaryDirectory() as tmp:
        d1, d2 = os.path.join(tmp, 'e1'), os.path.join(tmp, 'e2')
        m1 = _render(d1, 'enhanced', frames)
        m2 = _render(d2, 'enhanced', frames)
        ok = all(m1[k] == m2.get(k) for k in m1)
        check('enhanced 跨进程逐帧一致', ok and set(m1) == set(m2))
        # raw 对照：同一批帧
        d3 = os.path.join(tmp, 'r1')
        m3 = _render(d3, 'raw', frames)
        diff = [k for k in m1 if m1[k] != m3.get(k)]
        print(f'    (info) enhanced vs raw 差异帧: {len(diff)}/{len(m1)}'
              f'  —— WBOIT 水面生效证据')
        check('enhanced 与 raw 有差异（水面确实换了画法）', len(diff) > 0,
              'WBOIT 可能未生效')


def main():
    test_registry()
    test_scene_protocol()
    test_enhanced_determinism()
    if FAILED:
        print(f'\nFAILED {len(FAILED)}: {FAILED}')
        return 1
    print('\nALL_PROFILE_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
