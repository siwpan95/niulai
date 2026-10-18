# -*- coding: utf-8 -*-
"""分块并行渲染测试（P3-2）。

核心验收：**并行（2 workers）产出的帧必须与串行（1 worker）逐帧 md5 相同**——
场景姿态是 t 的纯函数 + 固定 seed，块间零共享状态，所以并行不该改变任何一帧。

其余为纯函数测试（切块覆盖性、resume 判定），不需要渲染。

运行：python tests/test_parallel.py [--slow]（真渲染对比默认开启，用 --no-render 跳过）
"""
import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# scripts/ 不是包，按文件路径加载
_spec = importlib.util.spec_from_file_location(
    'render_parallel', os.path.join(ROOT, 'scripts', 'render_parallel.py'))
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)

FAILED = []


def check(name, cond, detail=''):
    status = 'ok' if cond else 'FAIL'
    print(f'  {status}: {name}' + (f'  [{detail}]' if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


# ---------------------------------------------------------------- 纯函数


def test_plan_chunks():
    print('test_plan_chunks')
    # 整除
    blocks = rp.plan_chunks(0, 12, 6)
    check('整除切块数', blocks == [(0, 6), (6, 12)], f'{blocks}')
    # 非整除：最后一块收尾
    blocks = rp.plan_chunks(0, 10, 6)
    check('非整除切块', blocks == [(0, 6), (6, 10)], f'{blocks}')
    # 覆盖性：不重不漏
    for start, end, cf in ((0, 100, 7), (5, 47, 13), (0, 1, 6), (3, 3, 6)):
        blocks = rp.plan_chunks(start, end, cf)
        if end <= start:
            check(f'空区间 ({start},{end}) 无块', blocks == [], f'{blocks}')
            continue
        check(f'首块起点 ({start},{end},{cf})', blocks[0][0] == start)
        check(f'末块终点 ({start},{end},{cf})', blocks[-1][1] == end)
        contiguous = all(blocks[i][1] == blocks[i + 1][0]
                         for i in range(len(blocks) - 1))
        check(f'块间首尾相接 ({start},{end},{cf})', contiguous, f'{blocks}')
        total = sum(b - a for a, b in blocks)
        check(f'总帧数守恒 ({start},{end},{cf})', total == end - start,
              f'{total} vs {end - start}')
        sizes = [b - a for a, b in blocks]
        check(f'除末块外等长 ({start},{end},{cf})',
              all(s == cf for s in sizes[:-1]), f'{sizes}')
    # 非法输入
    try:
        rp.plan_chunks(0, 10, 0)
        check('chunk_frames=0 应抛错', False)
    except ValueError:
        check('chunk_frames=0 应抛错', True)


def test_block_done():
    print('test_block_done')
    tmp = tempfile.mkdtemp(prefix='niulai_par_')
    prod_dir = os.path.join(tmp, 'blockdir')
    prod_mp4 = os.path.join(tmp, 'block.mp4')
    mani = os.path.join(tmp, 'block.manifest.json')
    os.makedirs(prod_dir, exist_ok=True)
    open(prod_mp4, 'wb').write(b'\x00' * 128)

    def write_manifest(n):
        data = {'frames': {str(i): f'md5{i:03d}' for i in range(n)}}
        with open(mani, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    check('无 manifest -> 未完成',
          not rp.block_done(prod_dir, mani, 4, True))
    write_manifest(4)
    check('manifest 完整 + 目录在 -> 完成',
          rp.block_done(prod_dir, mani, 4, True))
    check('mp4 模式：产物非空 -> 完成',
          rp.block_done(prod_mp4, mani, 4, False))
    # 半截 manifest（渲染中途被杀）必须判为未完成 —— 否则 --resume 会跳过坏块
    write_manifest(2)
    check('半截 manifest -> 未完成（防中断残留）',
          not rp.block_done(prod_dir, mani, 4, True))
    # 产物缺失
    write_manifest(4)
    missing = os.path.join(tmp, 'nope.mp4')
    check('产物缺失 -> 未完成', not rp.block_done(missing, mani, 4, False))
    # 空 mp4
    empty = os.path.join(tmp, 'empty.mp4')
    open(empty, 'wb').close()
    check('空 mp4 -> 未完成', not rp.block_done(empty, mani, 4, False))
    # 坏 manifest
    with open(mani, 'w', encoding='utf-8') as f:
        f.write('not json')
    check('坏 manifest -> 未完成（不崩）',
          not rp.block_done(prod_dir, mani, 4, True))
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- 真渲染


def test_parallel_matches_serial(do_render=True):
    """并行 vs 串行：逐帧 md5 必须完全相同（P3-2 的核心验收）。"""
    print('test_parallel_matches_serial')
    if not do_render:
        print('  skip: --no-render')
        return
    tmp = tempfile.mkdtemp(prefix='niulai_par_render_')
    serial_dir = os.path.join(tmp, 'serial')
    par_dir = os.path.join(tmp, 'parallel')
    # 12 帧 = 2 块 x 6 帧；320x200 最省
    start, end, frames_per_block = 0, 12, 6
    common = dict(act='act0_prologue', size='320x200', seed=0,
                  chunk_seconds=frames_per_block / 30.0, fps=30, png=True)
    t0 = time.perf_counter()
    s1 = rp.run(start=start, end=end, out_root=serial_dir, workers=1, **common)
    t_ser = time.perf_counter() - t0
    t0 = time.perf_counter()
    s2 = rp.run(start=start, end=end, out_root=par_dir, workers=2, **common)
    t_par = time.perf_counter() - t0

    check('串行块数', s1['blocks'] == 2, f"{s1['blocks']}")
    check('并行块数', s2['blocks'] == 2, f"{s2['blocks']}")
    check('串行无失败', s1['failed'] == 0, f"{s1['failed']}")
    check('并行无失败', s2['failed'] == 0, f"{s2['failed']}")
    check('并行帧数 == 串行帧数', s1['frames'] == s2['frames'] == end - start,
          f"{s1['frames']} vs {s2['frames']}")

    with open(os.path.join(serial_dir, 'manifest.json'), encoding='utf-8') as f:
        m1 = json.load(f)['frames']
    with open(os.path.join(par_dir, 'manifest.json'), encoding='utf-8') as f:
        m2 = json.load(f)['frames']
    check('帧集合一致', set(m1) == set(m2),
          f'{sorted(set(m1) ^ set(m2))[:5]}')
    diff = [k for k in sorted(m1, key=int) if m1.get(k) != m2.get(k)]
    check('并行 vs 串行逐帧 md5 相同', not diff, f'diff frames: {diff[:5]}')
    if not diff:
        print(f'  ok: {len(m1)} frames identical '
              f'(serial {t_ser:.1f}s / parallel {t_par:.1f}s, '
              f'speedup {t_ser / max(t_par, 1e-6):.2f}x)')

    # resume：第二次跑应全部跳过
    s3 = rp.run(start=start, end=end, out_root=par_dir, workers=2,
                resume=True, **common)
    check('resume 跳过全部已完成块', s3['skipped'] == 2, f"{s3['skipped']}")
    check('resume 不重复渲染', s3['rendered'] == 0, f"{s3['rendered']}")
    check('resume 后帧数仍完整', s3['frames'] == end - start,
          f"{s3['frames']}")
    shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-render', action='store_true',
                    help='skip the (slow) real render comparison')
    args = ap.parse_args()
    test_plan_chunks()
    test_block_done()
    test_parallel_matches_serial(do_render=not args.no_render)
    if FAILED:
        print(f'\nFAILED {len(FAILED)}: {FAILED}')
        return 1
    print('\nALL_PARALLEL_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
