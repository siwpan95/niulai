# -*- coding: utf-8 -*-
"""导演过片联络图：每镜头一帧 + 时间码，单文件 HTML（base64 内嵌，零依赖）。

用法：.venv\\Scripts\\python.exe scripts\\contact_sheet.py [--size 640x360]

产出 output/review/contact_sheet.html —— 导演（全哥）逐镜头过片批注用。
再生成（修复后）用 --fresh 强制重新渲染帧。
"""
import argparse
import base64
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from niulai.cli import SCENES                                            # noqa: E402
from niulai.pipeline import render as pipe                               # noqa: E402
from niulai.timeline import ACTS                                         # noqa: E402

FF = os.environ.get('NIULAI_FFMPEG', 'ffmpeg')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'output')
REVIEW = os.path.join(OUT, 'review')
FPS = 30


def shot_mid(shot, act_t0):
    return int((act_t0 + (shot.t0 + shot.t1) / 2.0) * FPS)


def render_shot_frame(scene_name, frame, w, h, cache_path):
    """渲染一帧 -> PNG（缓存）。"""
    if os.path.exists(cache_path):
        return cache_path
    scene = SCENES[scene_name](seed=20260805, grid=96)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    pipe.render_pipe(scene, frame, frame + 1,
                     cache_path.replace('.png', '.mp4'),
                     size=(w, h), ffmpeg=FF)
    subprocess.run([FF, '-y', '-i', cache_path.replace('.png', '.mp4'),
                    '-frames:v', '1', cache_path], capture_output=True)
    os.remove(cache_path.replace('.png', '.mp4'))
    return cache_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--size', default='640x360')
    ap.add_argument('--fresh', action='store_true')
    args = ap.parse_args()
    w, h = (int(x) for x in args.size.lower().split('x'))
    os.makedirs(REVIEW, exist_ok=True)
    if args.fresh:
        for f in os.listdir(REVIEW):
            if f.endswith('.png'):
                os.remove(os.path.join(REVIEW, f))

    cells = []
    for act_name, t0, t1, _desc in ACTS:
        if act_name not in SCENES:
            continue
        scene = SCENES[act_name](seed=20260805, grid=48)
        act_t0 = t0
        if act_name == 'act0_prologue':
            # act0 未用 Shot 框架（P0 老结构）：取追雀/双人两帧代表
            pseudo = ((180.0, '追雀长镜头'), (350.0, '双人镜头过渡'))
            for mid, note in pseudo:
                frame = int((act_t0 + mid) * FPS)
                cache = os.path.join(REVIEW, f'act0_prologue_{mid:04.0f}.png')
                render_shot_frame(act_name, frame, w, h, cache)
                with open(cache, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('ascii')
                tc = f'{frame // (FPS * 60):02d}:{(frame // FPS) % 60:02d}'
                cells.append((act_name, note, tc, b64))
            continue
        for shot in scene.shots:
            frame = shot_mid(shot, act_t0)
            cache = os.path.join(REVIEW, f'{act_name}_{shot.t0:04.0f}-{shot.t1:04.0f}.png')
            render_shot_frame(act_name, frame, w, h, cache)
            with open(cache, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('ascii')
            tc = f'{frame // (FPS * 60):02d}:{(frame // FPS) % 60:02d}'
            cells.append((act_name, shot.note, tc, b64))

    # 单文件 HTML
    cards = []
    for act_name, note, tc, b64 in cells:
        cards.append(f'''<div class="card">
<img src="data:image/png;base64,{b64}" alt="{note}">
<div class="cap"><b>{act_name}</b> · {note} · <code>{tc}</code>
<br><input placeholder="批注..." class="note"></div>
</div>''')
    html = f'''<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>《牛来》导演过片联络图</title>
<style>
body{{background:#141518;color:#ddd;font-family:sans-serif;margin:16px}}
h1{{font-size:20px}} .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}}
.card{{background:#1e2024;border-radius:8px;overflow:hidden}}
.card img{{width:100%;display:block}}
.cap{{padding:8px 10px;font-size:13px;line-height:1.5}}
.note{{width:100%;background:#0c0d10;border:1px solid #333;color:#ccc;
border-radius:4px;padding:4px 6px;margin-top:4px}}
code{{color:#9ad}}
</style></head><body>
<h1>《牛来》导演过片联络图（{len(cells)} 镜头 · 同人学习性复刻）</h1>
<div class="grid">{''.join(cards)}</div>
</body></html>'''
    path = os.path.join(REVIEW, 'contact_sheet.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'OK {len(cells)} shots -> {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
