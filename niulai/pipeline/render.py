# -*- coding: utf-8 -*-
"""成片管线：确定性离屏逐帧渲染 -> PNG 序列 -> ffmpeg 拼装 MP4。

三条口径：
1. **确定性**：场景姿态全部是 t 的纯函数（+ 固定 seed），同一帧两次渲染
   （哪怕是两个进程）必须逐字节相同 —— tests/test_determinism.py 跨进程钉住。
2. **离屏**：visible=False 的 pyglet 窗口 + glReadPixels 抓帧
   （复用 world3d.platform.app.capture，DPI 无关、正立保存）。
3. **雾色 == 清屏色**：否则地平线出现硬边（3dworld terrain_flyover 坑位 3）。
"""
import hashlib
import json
import os
import subprocess

import pyglet
from pyglet.gl import GL_DEPTH_TEST, GL_TRIANGLES, glClearColor, glEnable
from pyglet.graphics.shader import Shader, ShaderProgram
from pyglet.math import Mat4

from world3d.logic.camera import look_at_matrix
from world3d.platform.app import capture

from ..cast.rig import merge_draw

VERTEX_SRC = '''#version 330 core
in vec3 position;
in vec4 colors;          // CPU 已烘焙：每面明暗 x 面向光
uniform WindowBlock { mat4 projection; mat4 view; } window;
out vec4 v_col;
out vec3 v_world;
void main() {
    v_col = colors;
    v_world = position;
    gl_Position = window.projection * window.view * vec4(position, 1.0);
}'''

FRAGMENT_SRC = '''#version 330 core
in vec4 v_col;
in vec3 v_world;
out vec4 final_colors;
uniform vec3 u_eye;
uniform vec3 u_fog;       // 必须等于清屏色
void main() {
    float d = distance(v_world, u_eye);
    float fog = 1.0 - exp(-d * 0.0105);
    final_colors = vec4(mix(v_col.rgb, u_fog, clamp(fog, 0.0, 1.0)), 1.0);
}'''


def md5_of(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


class OffscreenRenderer:
    """离屏渲染器：一个窗口复用整个帧区间。"""

    def __init__(self, width=1280, height=720, sky=(0.9, 0.85, 0.74), fov=55.0):
        self.width, self.height = width, height
        self.sky = sky
        self.window = pyglet.window.Window(width, height, visible=False)
        self.window.switch_to()
        self.program = ShaderProgram(Shader(VERTEX_SRC, 'vertex'),
                                     Shader(FRAGMENT_SRC, 'fragment'))
        self.window.projection = Mat4.perspective_projection(
            width / float(height), z_near=0.1, z_far=600.0, fov=fov)
        glEnable(GL_DEPTH_TEST)
        glClearColor(sky[0], sky[1], sky[2], 1.0)

    def close(self):
        self.window.close()

    def render_frame(self, meshes, eye, target, path):
        """画一帧并存 PNG，返回该文件的 md5。"""
        win = self.window
        win.switch_to()
        win.view = look_at_matrix(eye, target, (0.0, 1.0, 0.0))
        prog = self.program
        prog.use()
        prog['u_eye'] = (eye[0], eye[1], eye[2])
        prog['u_fog'] = self.sky
        win.clear()
        vlist = merge_draw(prog, meshes)
        vlist.draw(GL_TRIANGLES)
        vlist.delete()
        capture(win, path)
        return md5_of(path)


def frame_path(out_dir, frame):
    return os.path.join(out_dir, f'frame_{frame:05d}.png')


def render_range(scene, start, end, out_dir, size=(1280, 720), fps=30,
                 on_progress=None):
    """渲染帧区间 [start, end)（半开）。返回 {frame: md5} 清单。

    同一个 OffscreenRenderer 复用整个区间；每帧先算相机再取姿态。
    """
    os.makedirs(out_dir, exist_ok=True)
    r = OffscreenRenderer(size[0], size[1], sky=scene.SKY)
    manifest = {}
    try:
        for frame in range(start, end):
            t = frame / float(fps)
            eye, target = scene.camera(t)
            meshes = scene.meshes(t)
            p = frame_path(out_dir, frame)
            manifest[frame] = r.render_frame(meshes, eye, target, p)
            if on_progress is not None:
                on_progress(frame, end)
    finally:
        r.close()
    return manifest


def write_manifest(manifest, path, meta=None):
    data = {'frames': {str(k): v for k, v in sorted(manifest.items())}}
    if meta:
        data['meta'] = meta
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def assemble(frames_dir, out_path, fps=30, ffmpeg='ffmpeg', crf=20):
    """PNG 序列 -> MP4（H.264 + yuv420p，最大兼容）。"""
    pattern = os.path.join(frames_dir, 'frame_%05d.png')
    cmd = [ffmpeg, '-y', '-framerate', str(fps), '-i', pattern,
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', str(crf),
           out_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f'ffmpeg failed ({proc.returncode}):\n{proc.stderr[-2000:]}')
    if not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError(f'ffmpeg produced no output: {out_path}')
    return out_path
