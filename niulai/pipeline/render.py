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
import threading

import pyglet
from pyglet.gl import (GL_DEPTH_TEST, GL_RGBA, GL_TRIANGLES,
                       GL_UNSIGNED_BYTE, glClearColor, glEnable,
                       glReadPixels)
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
uniform float u_fog_k;    // 雾密度（夜戏更浓）
uniform vec3 u_tint;      // 全局色调（夜戏压暗偏蓝；默认白）
void main() {
    float d = distance(v_world, u_eye);
    float fog = 1.0 - exp(-d * u_fog_k);
    vec3 lit = v_col.rgb * u_tint;
    final_colors = vec4(mix(lit, u_fog, clamp(fog, 0.0, 1.0)), 1.0);
}'''


def md5_of(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read_pixels(window):
    """读回帧缓冲原始 RGBA 字节（**已翻转为顶行起始**，与 PNG/视频惯例一致）。

    glReadPixels 的原点在左下（GL 惯例），直接喂 ffmpeg 会得到倒影，
    故按行翻转。返回 (w, h, bytes)。
    """
    import ctypes

    w, h = window.width, window.height
    row = w * 4
    buf = (ctypes.c_ubyte * (row * h))()
    glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, buf)
    raw = bytes(buf)
    flipped = bytearray(row * h)
    for y in range(h):
        flipped[y * row:(y + 1) * row] = raw[(h - 1 - y) * row:(h - y) * row]
    return w, h, bytes(flipped)


class OffscreenRenderer:
    """离屏渲染器：一个窗口复用整个帧区间。"""

    def __init__(self, width=1280, height=720, sky=(0.9, 0.85, 0.74), fov=55.0,
                 fog_k=0.0105, tint=(1.0, 1.0, 1.0)):
        self.width, self.height = width, height
        self.sky = sky
        self.fog_k = fog_k
        self.tint = tint
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

    def _apply_uniforms(self, eye):
        prog = self.program
        prog['u_eye'] = (eye[0], eye[1], eye[2])
        prog['u_fog'] = self.sky
        prog['u_fog_k'] = self.fog_k
        prog['u_tint'] = self.tint

    def render_frame(self, meshes, eye, target, path):
        """画一帧并存 PNG，返回该文件的 md5。"""
        win = self.window
        win.switch_to()
        win.view = look_at_matrix(eye, target, (0.0, 1.0, 0.0))
        prog = self.program
        prog.use()
        self._apply_uniforms(eye)
        win.clear()
        vlist = merge_draw(prog, meshes)
        vlist.draw(GL_TRIANGLES)
        vlist.delete()
        capture(win, path)
        return md5_of(path)

    def render_frame_raw(self, meshes, eye, target, overlays=None):
        """画一帧并返回原始 RGBA 字节（供 raw pipe 直喂 ffmpeg）。

        overlays：可选的屏幕空间叠加层列表（字幕等），在 3D 之后、
        读回之前绘制（正交投影，见 SubtitleTrack.draw）。
        """
        win = self.window
        win.switch_to()
        win.view = look_at_matrix(eye, target, (0.0, 1.0, 0.0))
        prog = self.program
        prog.use()
        self._apply_uniforms(eye)
        win.clear()
        vlist = merge_draw(prog, meshes)
        vlist.draw(GL_TRIANGLES)
        vlist.delete()
        if overlays:
            for ov in overlays:
                ov.draw(win)
        return read_pixels(win)


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


def render_pipe(scene, start, end, out_path, size=(1280, 720), fps=30,
                ffmpeg='ffmpeg', crf=20, on_progress=None, audio=None):
    """raw pipe 直喂 ffmpeg：帧缓冲原始字节走 stdin，**无中间 PNG**。

    P0 的 PNG 路径 ~1.5fps@720p（zlib 压缩 3.7MB/帧是瓶颈）；本路径把
    编码整个交给 ffmpeg 的 C 实现，实测数量级提升（见 bench）。
    可选 audio：音轨文件路径，ffmpeg -i 混入（-shortest）。
    返回 {frame: md5}（帧级 md5 用于确定性验收；内容 = 翻转后 RGBA 字节）。
    """
    w, h = size
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    cmd = [ffmpeg, '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba',
           '-s', f'{w}x{h}', '-r', str(fps), '-i', '-']
    if audio:
        # 音轨必须是**有限**文件（audio/prepare.py 预制到精确时长）——
        # 现场 -stream_loop -1 会让音轨时间轴狂奔、mux 错乱（实测踩坑）
        cmd += ['-i', audio, '-c:a', 'aac', '-shortest']
    cmd += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', str(crf),
            out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    # stderr 必须**并发按块排空**：ffmpeg 的 stats 进度行是 \r 结尾（不是 \n），
    # 用 `for line in` 迭代会卡在等一个永远不来的换行符；灌满 64KB 管道缓冲后
    # 互赌死锁（Python 阻塞写 stdin / ffmpeg 阻塞写 stderr）——
    # P1 全幕渲染两轮 5 小时 + 14 分钟零进展都是这么死的（实测踩坑两次）
    err_chunks = []

    def _drain():
        while True:
            chunk = proc.stderr.read1(65536)   # 有数据即返回，不等换行
            if not chunk:
                break
            err_chunks.append(chunk)

    drain = threading.Thread(target=_drain, daemon=True)
    drain.start()
    r = OffscreenRenderer(w, h, sky=scene.SKY,
                          fog_k=getattr(scene, 'FOG_K', 0.0105),
                          tint=getattr(scene, 'TINT', (1.0, 1.0, 1.0)))
    manifest = {}
    overlays_fn = getattr(scene, 'overlays', None)
    t0 = getattr(scene, 'T0', 0.0)      # 全片帧号 -> 幕内时间
    try:
        for frame in range(start, end):
            t = frame / float(fps) - t0
            eye, target = scene.camera(t)
            meshes = scene.meshes(t)
            overlays = overlays_fn(t) if overlays_fn else None
            _, _, raw = r.render_frame_raw(meshes, eye, target, overlays)
            manifest[frame] = hashlib.md5(raw).hexdigest()
            try:
                proc.stdin.write(raw)
            except BrokenPipeError:
                err = proc.stderr.read().decode('utf-8', 'ignore')
                raise RuntimeError(f'ffmpeg pipe broke:\n{err[-2000:]}')
            if on_progress is not None:
                on_progress(frame, end)
    finally:
        r.close()
        proc.stdin.close()
        drain.join(timeout=10)
    err = b''.join(err_chunks).decode('utf-8', 'ignore')
    if proc.wait() != 0:
        raise RuntimeError(f'ffmpeg failed:\n{err[-2000:]}')
    if not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError(f'ffmpeg produced no output: {out_path}')
    return manifest


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
