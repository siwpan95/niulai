# -*- coding: utf-8 -*-
"""导出八幕场景清单（结构 + 参数，不含顶点）到 output/manifests/。

用法::

    python scripts/export_manifests.py                 # 八幕全出
    python scripts/export_manifests.py --acts act4

每幕产物：``<act>.scene.json``——相机关键帧、网格清单、光照环境、
可被 ``world3d.engine.serialize.loads`` 还原的节点结构。
校验：``scene_build.validate``（会实际试构建 mesh 定义）+ serialize 往返。
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from niulai import MASTER_SEED  # noqa: E402
from niulai.cli import SCENES  # noqa: E402
from niulai.pipeline import scene_manifest as sm  # noqa: E402
from niulai.timeline import ACTS  # noqa: E402

OUT = os.path.join(ROOT, 'output', 'manifests')


def main():
    ap = argparse.ArgumentParser(prog='export_manifests')
    ap.add_argument('--acts', default=None, help='comma list, default all')
    ap.add_argument('--samples', type=int, default=8,
                    help='每幕相机关键帧数（默认 8）')
    args = ap.parse_args()

    wanted = args.acts.split(',') if args.acts else [a[0] for a in ACTS]
    bad = 0
    for name, t0, t1, _fn in ACTS:
        key = name.split('_')[0]
        if name not in wanted and key not in wanted:
            continue
        cls = SCENES[name]
        scene = cls(seed=MASTER_SEED)
        data = sm.build(key, scene, (t0, t1), samples=args.samples)
        errs, ok = sm.verify(data)
        path = sm.write(data, OUT)
        mb = os.path.getsize(path) / 1024.0
        print(f'[manifest] {key}: {path}  ({mb:.1f} KB)  '
              f'keys={len(data["niulai"]["keyframes"])}  '
              f'errors={len(errs)}  roundtrip={"ok" if ok else "FAIL"}',
              flush=True)
        if errs or not ok:
            bad += 1
    if bad:
        print(f'[manifest] FAIL {bad} act(s)')
        return 1
    print('[manifest] ALL DONE')
    return 0


if __name__ == '__main__':
    sys.exit(main())
