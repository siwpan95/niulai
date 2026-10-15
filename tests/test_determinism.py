# -*- coding: utf-8 -*-
"""确定性测试：**跨进程**两次渲染同一批帧，md5 必须逐帧相同。

这是成片管线的根基验收 —— 同 seed 同帧号，两个独立 Python 进程（各自建窗口、
各自过 GL）产出逐字节一致的 PNG。任何跨帧累积状态、任何依赖墙钟/随机源的
实现都会在这里现形。

运行：python tests/test_determinism.py [--frames 3]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def render_into(out_dir, frames):
    cmd = [sys.executable, '-m', 'niulai', 'render',
           '--act', 'act0_prologue', '--start', '0', '--end', str(frames),
           '--size', '320x200', '--out', out_dir]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f'render failed:\n{proc.stdout}\n{proc.stderr}')
    with open(os.path.join(out_dir, 'manifest.json'), encoding='utf-8') as f:
        return json.load(f)['frames']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', type=int, default=3)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        d1 = os.path.join(tmp, 'run1')
        d2 = os.path.join(tmp, 'run2')
        m1 = render_into(d1, args.frames)
        m2 = render_into(d2, args.frames)
        ok = True
        for k in sorted(m1, key=int):
            same = m1[k] == m2.get(k)
            print(f"  {'ok' if same else 'FAIL'}: frame {k}  {m1[k][:12]}"
                  f" vs {m2.get(k, 'MISSING')[:12]}")
            ok = ok and same
        print()
        if ok and set(m1) == set(m2):
            print(f'DETERMINISM_OK ({len(m1)} frames, cross-process)')
            return 0
        print('DETERMINISM_FAILED')
        return 1


if __name__ == '__main__':
    sys.exit(main())
