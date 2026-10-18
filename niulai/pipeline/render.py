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
from .profile import get_profile

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

# enhanced profile 无后处理时的直通呈现（属性布局同 world3d SKY_VERT）
COPY_VERT_SRC = '''#version 330 core
in vec3 position;
out vec2 vNdc;
void main() {
    vNdc = position.xy;
    gl_Position = vec4(position, 1.0);
}'''

COPY_FRAG_SRC = '''#version 330 core
in vec2 vNdc;
uniform sampler2D uTex;
out vec4 final_colors;
void main() {
    final_colors = texture(uTex, vNdc * 0.5 + 0.5);
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
    """离屏渲染器：一个窗口复用整个帧区间。

    profile：'raw'（默认）/ 'enhanced'（WBOIT 水面 + Bloom，见 pipeline/profile.py）。
    enhanced 资源（rt_a/rt_b/oit/post）惰性建，尺寸随窗口。
    """

    def __init__(self, width=1280, height=720, sky=(0.9, 0.85, 0.74), fov=55.0,
                 fog_k=0.0105, tint=(1.0, 1.0, 1.0), profile=None):
        self.width, self.height = width, height
        self.sky = sky
        self.fog_k = fog_k
        self.tint = tint
        self.profile = profile or get_profile('raw')
        self._batch_cache = {}          # vertex_count -> InstancedBatch
        self.window = pyglet.window.Window(width, height, visible=False)
        self.window.switch_to()
        self.program = ShaderProgram(Shader(VERTEX_SRC, 'vertex'),
                                     Shader(FRAGMENT_SRC, 'fragment'))
        self.window.projection = Mat4.perspective_projection(
            width / float(height), z_near=0.1, z_far=600.0, fov=fov)
        glEnable(GL_DEPTH_TEST)
        glClearColor(sky[0], sky[1], sky[2], 1.0)   # 清屏色 == 雾色（铁律）
        # enhanced / pbr 资源
        self._rt_a = self._rt_b = None
        self._oit = None
        self._post = None
        self._copy_prog = None
        self._w3renderer = None
        if self.profile.name == 'enhanced':
            self._build_enhanced()
        elif self.profile.name == 'pbr':
            self._build_pbr()

    def _build_pbr(self):
        """P5 全量 PBR：world3d Renderer（MRT + 天空 + SSAO + Bloom + 合成）。"""
        from world3d.engine.postfx import PostSettings
        from world3d.engine.renderer import Renderer
        # 曝光/泛光调校：程序化天空 + IBL 下默认参数会把画面推白（实测），
        # 压曝光 + 抬 Bloom 阈值保住沙丘纹理的对比。
        settings = PostSettings()
        settings.exposure = 0.62
        settings.bloom_threshold = 1.9
        settings.bloom_intensity = 0.25
        settings.vignette = 0.30
        self._w3renderer = Renderer(self.width, self.height,
                                    post_settings=settings)

    def _build_enhanced(self):
        from world3d.engine.oit import WBOIT, supported
        from world3d.engine.postfx import PostChain
        from world3d.engine.targets import RenderTarget
        self._rt_a = RenderTarget(self.width, self.height, color_count=1,
                                  depth=True)
        self._rt_b = RenderTarget(self.width, self.height, color_count=1,
                                  depth=False)
        if self.profile.wboit and supported():
            self._oit = WBOIT(self.width, self.height)
        if self.profile.bloom:
            self._post = PostChain(self.width, self.height)
        self._copy_prog = ShaderProgram(Shader(COPY_VERT_SRC, 'vertex'),
                                        Shader(COPY_FRAG_SRC, 'fragment'))

    # ------------------------------------------------------ enhanced 路径 --
    def _draw_water_wboit(self, positions, color, alpha):
        """水面 WBOIT 透明绘制（world3d 'wboit' 着色器：accum/reveal 双 MRT）。

        positions: 水面三角形位置列表；color: RGB 0-1；alpha: 不透明度。
        法线恒为 +Y（水面平坦），model/normal_mat 为单位矩阵。
        """
        from world3d.engine.shaders import get
        prog = get('wboit')
        prog.use()
        ident = (1.0, 0.0, 0.0, 0.0,
                 0.0, 1.0, 0.0, 0.0,
                 0.0, 0.0, 1.0, 0.0,
                 0.0, 0.0, 0.0, 1.0)
        prog['model'] = ident
        prog['normal_mat'] = ident
        prog['uColor'] = tuple(color)
        prog['uAlpha'] = float(alpha)
        prog['uLightDir'] = (0.35, 0.85, 0.40)
        n = len(positions) // 3
        norms = [0.0, 1.0, 0.0] * n
        vlist = prog.vertex_list(n, GL_TRIANGLES,
                                 position=('f', list(positions)),
                                 normals=('f', norms))
        vlist.draw(GL_TRIANGLES)
        vlist.delete()

    def _render_enhanced(self, meshes, eye, target, overlays, instanced,
                         particles, water):
        """enhanced profile：场景 -> rt_a；水面 WBOIT；Bloom -> 帧缓冲。"""
        from pyglet.gl import (GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
                               GL_NEAREST, GL_READ_FRAMEBUFFER,
                               glBindFramebuffer, glBlitFramebuffer, glClear,
                               glClearColor)
        win = self.window
        win.switch_to()
        win.view = look_at_matrix(eye, target, (0.0, 1.0, 0.0))
        prog = self.program
        # 1) 不透明场景（+ 实例化 + 粒子）-> rt_a
        self._rt_a.bind()
        prog.use()
        self._apply_uniforms(eye)
        glClearColor(self.sky[0], self.sky[1], self.sky[2], 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        vlist = merge_draw(prog, meshes)
        vlist.draw(GL_TRIANGLES)
        vlist.delete()
        if instanced:
            from . import instanced as _inst
            for pose_meshes, bases in instanced:
                total = sum(len(md.positions) // 3 for md in pose_meshes)
                batch = self._batch_cache.get(total)
                if batch is None:
                    batch = _inst.InstancedBatch(total)
                    self._batch_cache[total] = batch
                batch.draw(pose_meshes, bases, eye, self.sky, self.fog_k,
                           self.tint)
        if particles:
            for layer in particles:
                layer.draw(win, eye, self.sky, self.fog_k, self.tint)
        src_rt = self._rt_a
        # 2) 水面 WBOIT（深度从 rt_a blit -> 岸/角色正确遮挡水面）
        if water and self._oit is not None:
            self._oit.begin()
            glBindFramebuffer(GL_READ_FRAMEBUFFER, self._rt_a.fbo.id)
            glBlitFramebuffer(0, 0, self.width, self.height,
                              0, 0, self.width, self.height,
                              GL_DEPTH_BUFFER_BIT, GL_NEAREST)
            for positions, color, alpha in water:
                self._draw_water_wboit(positions, color, alpha)
            self._oit.end()
            # 3) 合成 -> rt_b
            self._rt_b.bind()
            self._oit.composite(self._rt_a.color[0])
            src_rt = self._rt_b
        # 4) Bloom / 呈现 -> 窗口帧缓冲
        src_rt.unbind()
        if self._post is not None:
            bloom_tex = self._post.render_bloom(src_rt.color[0])
            self._post.composite(src_rt.color[0], self.width, self.height,
                                 bloom_tex=bloom_tex)
        else:
            self._present_copy(src_rt.color[0])
        # 5) 字幕 overlay（屏幕空间）-> 帧缓冲
        if overlays:
            for ov in overlays:
                ov.draw(win)
        return read_pixels(win)

    def _present_copy(self, tex):
        """无后处理时的直通呈现（复制着色器 + FullscreenQuad）。"""
        from world3d.engine.postfx import FullscreenQuad
        from world3d.engine.targets import bind_texture
        prog = self._copy_prog
        prog.use()
        bind_texture(0, tex)
        prog['uTex'] = 0
        FullscreenQuad().draw(prog)

    # ------------------------------------------------------------ PBR --
    def _pbr_pack_for(self, scene):
        """幕 -> PbrPack（惰性建，缓存到场景实例上；IBL 每块烘焙一次）。"""
        from .pbr_bridge import PbrPack, act_of
        pack = getattr(scene, '_pbr_pack', None)
        if pack is None:
            pack = PbrPack(act_of(getattr(scene, 'NAME', '')), self._w3renderer)
            scene._pbr_pack = pack
        return pack

    def _render_pbr(self, scene, meshes, eye, target, overlays, instanced):
        """P5 全量 PBR：world3d Renderer 端到端（MRT/天空/SSAO/Bloom/合成）。

        粒子层不进本路径（allin fx 已在 raw/enhanced 验证；PBR 深度图
        与自定义点精灵的深度合成不在本档目标内）。
        """
        from pyglet.gl import GL_DEPTH_TEST, glEnable
        win = self.window
        win.switch_to()
        pack = self._pbr_pack_for(scene)
        w3scene = pack.build_frame(meshes, instanced)
        cam = pack.camera(eye, target)
        self._w3renderer.render(cam, w3scene, window=win)
        pack.cleanup_frame()
        glEnable(GL_DEPTH_TEST)
        if overlays:
            for ov in overlays:
                ov.draw(win)
        return read_pixels(win)

    def close(self):
        for obj in (self._rt_a, self._rt_b, self._oit, self._post,
                    self._w3renderer):
            try:
                if obj is not None:
                    obj.delete()
            except Exception:
                pass
        self.window.close()

    def _apply_uniforms(self, eye):
        prog = self.program
        prog['u_eye'] = (eye[0], eye[1], eye[2])
        prog['u_fog'] = self.sky
        prog['u_fog_k'] = self.fog_k
        prog['u_tint'] = self.tint

    def apply_atmosphere(self, sky, fog_k, tint):
        """逐帧更新大气（清屏色必须 == 雾色，否则地平线硬边）。"""
        self.sky = tuple(sky)
        self.fog_k = fog_k
        self.tint = tuple(tint)
        glClearColor(sky[0], sky[1], sky[2], 1.0)

    def render_frame(self, meshes, eye, target, path, atmosphere=None,
                     overlays=None, particles=None, water=None, scene=None,
                     instanced=None):
        """画一帧并存 PNG，返回该文件的 md5。"""
        if atmosphere is not None:
            self.apply_atmosphere(*atmosphere)
        if self.profile.name == 'pbr' and self._w3renderer is not None \
                and scene is not None:
            self._render_pbr(scene, meshes, eye, target, overlays, instanced)
            capture(self.window, path)
            return md5_of(path)
        if self.profile.name == 'enhanced' and self._rt_a is not None:
            self._render_enhanced(meshes, eye, target, overlays, None,
                                  particles, water)
            capture(self.window, path)
            return md5_of(path)
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
        if particles:
            for layer in particles:
                layer.draw(win, eye, self.sky, self.fog_k, self.tint)
        if overlays:
            for ov in overlays:
                ov.draw(win)
        capture(win, path)
        return md5_of(path)

    def render_frame_raw(self, meshes, eye, target, overlays=None,
                         atmosphere=None, instanced=None, particles=None,
                         water=None, scene=None):
        """画一帧并返回原始 RGBA 字节（供 raw pipe 直喂 ffmpeg）。

        overlays：可选的屏幕空间叠加层列表（字幕等），在 3D 之后、
        读回之前绘制（正交投影，见 SubtitleTrack.draw）；
        atmosphere：(sky, fog_k, tint) 逐帧大气（None = 用构造值）；
        instanced：[(pose_meshes, bases), ...] 群体戏实例化组
        （与 CPU 合并路径输出逐字节一致，见 pipeline/instanced.py）；
        particles：[ParticleLayer, ...] 氛围粒子层（allin fx 接入，
        世界空间点精灵，3D 之后、overlays 之前绘制；层内状态已由
        场景的 particles(t) 预推进到本帧）；
        water：[(positions, color, alpha), ...] WBOIT 透明面（仅 enhanced
        profile 生效，由场景的 water(t) 钩子给出）；
        scene：niulai 场景对象（仅 pbr profile 需要——桥接包挂它缓存）。
        """
        if atmosphere is not None:
            self.apply_atmosphere(*atmosphere)
        if self.profile.name == 'pbr' and self._w3renderer is not None \
                and scene is not None:
            return self._render_pbr(scene, meshes, eye, target, overlays,
                                    instanced)
        if self.profile.name == 'enhanced' and self._rt_a is not None:
            return self._render_enhanced(meshes, eye, target, overlays,
                                         instanced, particles, water)
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
        if instanced:
            from . import instanced as _inst
            for pose_meshes, bases in instanced:
                nv = len(pose_meshes[0].positions) // 3
                total = sum(len(md.positions) // 3 for md in pose_meshes)
                batch = self._batch_cache.get(total)
                if batch is None:
                    batch = _inst.InstancedBatch(total)
                    self._batch_cache[total] = batch
                batch.draw(pose_meshes, bases, eye, self.sky, self.fog_k,
                           self.tint)
        if particles:
            for layer in particles:
                layer.draw(win, eye, self.sky, self.fog_k, self.tint)
        if overlays:
            for ov in overlays:
                ov.draw(win)
        return read_pixels(win)


def frame_path(out_dir, frame):
    return os.path.join(out_dir, f'frame_{frame:05d}.png')


def render_range(scene, start, end, out_dir, size=(1280, 720), fps=30,
                 on_progress=None, profile=None):
    """渲染帧区间 [start, end)（半开）。返回 {frame: md5} 清单。

    同一个 OffscreenRenderer 复用整个区间；每帧先算相机再取姿态。
    """
    os.makedirs(out_dir, exist_ok=True)
    r = OffscreenRenderer(size[0], size[1], sky=scene.SKY, profile=profile)
    manifest = {}
    water_fn = getattr(scene, 'water', None)
    particles_fn = getattr(scene, 'particles', None)
    overlays_fn = getattr(scene, 'overlays', None)
    crowd_fn = getattr(scene, 'crowd', None)
    try:
        for frame in range(start, end):
            t = frame / float(fps)
            eye, target = scene.camera(t)
            meshes = scene.meshes(t)
            particles = particles_fn(t) if particles_fn else None
            water = water_fn(t) if water_fn else None
            overlays = overlays_fn(t) if overlays_fn else None
            crowd = crowd_fn(t) if crowd_fn else None
            p = frame_path(out_dir, frame)
            manifest[frame] = r.render_frame(meshes, eye, target, p,
                                             overlays=overlays,
                                             particles=particles, water=water,
                                             scene=scene, instanced=crowd)
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
                ffmpeg='ffmpeg', crf=20, on_progress=None, audio=None,
                profile=None):
    """raw pipe 直喂 ffmpeg：帧缓冲原始字节走 stdin，**无中间 PNG**。

    P0 的 PNG 路径 ~1.5fps@720p（zlib 压缩 3.7MB/帧是瓶颈）；本路径把
    编码整个交给 ffmpeg 的 C 实现，实测数量级提升（见 bench）。
    可选 audio：音轨文件路径，ffmpeg -i 混入（-shortest）。
    profile：渲染 profile（默认 raw；enhanced = WBOIT + Bloom）。
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
                          tint=getattr(scene, 'TINT', (1.0, 1.0, 1.0)),
                          profile=profile)
    manifest = {}
    overlays_fn = getattr(scene, 'overlays', None)
    particles_fn = getattr(scene, 'particles', None)
    water_fn = getattr(scene, 'water', None)
    t0 = getattr(scene, 'T0', 0.0)      # 全片帧号 -> 幕内时间
    atm_fn = getattr(scene, 'atmosphere', None)
    crowd_fn = getattr(scene, 'crowd', None)
    try:
        for frame in range(start, end):
            t = frame / float(fps) - t0
            eye, target = scene.camera(t)
            meshes = scene.meshes(t)
            overlays = overlays_fn(t) if overlays_fn else None
            particles = particles_fn(t) if particles_fn else None
            water = water_fn(t) if water_fn else None
            atm = atm_fn(t) if atm_fn else None
            instanced = crowd_fn(t) if crowd_fn else None
            _, _, raw = r.render_frame_raw(meshes, eye, target, overlays, atm,
                                           instanced, particles, water,
                                           scene=scene)
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
