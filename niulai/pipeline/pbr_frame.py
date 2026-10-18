# -*- coding: utf-8 -*-
"""帧图驱动的全量 PBR 管线（P5）—— world3d 引擎能力收口。

以 examples/frame_graph.py 为模板（siwpan 自研，MIT），把 niulai 的每帧
场景接进**完整的深度效果链**：

    depth_prepass（线性距离图 R32F，雾/景深/运动模糊共用）
    -> shadow_pass（CSM 3 级阴影图，csm_matrices 正交光盒 + texel_snap）
    -> scene_pass（**阴影化 PBR 变体**：PBR_FRAG 注入 csm_glsl，太阳直射
       项乘 (1 - csm_shadow)；MRT COLOR1 法线+线性深度照常输出）
    -> SSAO（post.render_ssao，读 COLOR1）
    -> fog_pass（volumetric_glsl 高度雾 + 单次散射 + 光轴，复用 CSM 阴影）
    -> dof_pass（薄透镜 CoC gather，散景盘黄金角确定性）
    -> motionblur_pass（相机重投影 + 快门加权，单 pass 无时域累积）
    -> tonemap（Bloom + 曝光/ACES/暗角合成到屏幕）

pass 顺序由 `framegraph.standard_3d_plan` 声明编译（校验/排序/死 pass 剔除），
渲染循环就是"遍历计划"——这就是图驱动的全部。

确定性：IGN 抖动 / 黄金角散景盘 / 快门权重全部显式拒绝随机源；CSM 正交盒
由 t 纯函数的相机推导；阴影图内容随姿态确定。
"""
import math
import os

from pyglet.gl import (GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
                       GL_FRAMEBUFFER, GL_LINEAR, GL_NEAREST, GL_R32F,
                       GL_RED, GL_TEXTURE_2D, GL_TRIANGLES, glBindFramebuffer,
                       glClearColor, glClear, glDisable, glViewport,
                       glEnable, GL_DEPTH_TEST)
from pyglet.graphics.shader import Shader, ShaderProgram
from pyglet.math import Mat4, Vec3

from world3d.engine import csm, volumetrics, dof as dof_mod, motionblur as mb_mod
from world3d.engine.mathkit import mat4_from_Mat4, mat4_inverse, mat4_mul
from world3d.engine.postfx import FullscreenQuad, bind_screen
from world3d.engine.soft_shadow import pcss_glsl
from world3d.engine.targets import bind_texture

from .pbr_bridge import PbrPack  # noqa: F401  (re-export 便利)

WINDOW_BLOCK = '''uniform WindowBlock {
    mat4 projection;
    mat4 view;
} window;
'''

# ------------------------------------------------------------ 预 pass ---
DIST_VS = '#version 330 core\n' + WINDOW_BLOCK + '''
in vec3 position;
uniform vec3 u_cam;
out float v_dist;
void main() {
    vec4 wp = vec4(position, 1.0);
    v_dist = length(wp.xyz - u_cam);
    gl_Position = window.projection * window.view * wp;
}
'''

DIST_FS = '''#version 330 core
in float v_dist;
out vec4 final_colors;
void main() { final_colors = vec4(v_dist, 0.0, 0.0, 1.0); }
'''

SHADOW_VS = '''#version 330 core
in vec3 position;
uniform mat4 u_light_vp;
out float v_depth;
void main() {
    vec4 lp = u_light_vp * vec4(position, 1.0);
    v_depth = lp.z * 0.5 + 0.5;
    gl_Position = lp;
}
'''

SHADOW_FS = '''#version 330 core
in float v_depth;
out vec4 final_colors;
void main() { final_colors = vec4(v_depth, 0.0, 0.0, 1.0); }
'''

# ------------------------------------------------------ 阴影化 PBR 变体 --
_N_CASCADES = 3
_SHADOW_SIZE = 2048


def _shadowed_pbr_program():
    """PBR 着色器 + csm_glsl 注入（太阳直射项乘 (1 - csm_shadow)）。"""
    from world3d.engine.shaders import PBR_VERT, PBR_FRAG
    vert = PBR_VERT.replace('out vec4 vTint;',
                            'out vec4 vTint;\nout float v_zview;')
    vert = vert.replace('gl_Position = window.projection * window.view * world;',
                        'v_zview = (window.view * world).z;\n'
                        '    gl_Position = window.projection * window.view * world;')
    csm_src = csm.csm_glsl(n=_N_CASCADES)
    frag = PBR_FRAG.replace('in vec3 vWorldPos;',
                            'in vec3 vWorldPos;\nin float v_zview;')
    anchor = 'void main() {'
    # ⚠ csm_glsl 已自带 u_csm_vp*/split*/pcf/tex* 的声明——宿主只赋值不重复声明
    # （重复声明 = GLSL C1038 conflict，实测踩坑）
    frag = frag.replace(anchor, csm_src + '\n' + anchor, 1)
    old = 'Lo += (kd * albedo / PI + spec) * uSunColor * NdotL;'
    new = ('Lo += (kd * albedo / PI + spec) * uSunColor * NdotL\n'
           '         * (1.0 - csm_shadow(vWorldPos, v_zview, NdotL));')
    assert old in frag, 'PBR_FRAG 太阳直射锚点未找到'
    frag = frag.replace(old, new, 1)
    return ShaderProgram(Shader(vert, 'vertex'), Shader(frag, 'fragment'))


# ------------------------------------------------------ 全屏 pass 片段 ---
FULL_VS = '''#version 330 core
in vec2 position;
in vec2 uv;
out vec2 v_uv;
void main() {
    v_uv = uv;
    gl_Position = vec4(position, 0.0, 1.0);
}
'''

FOG_BODY = '''
in vec2 v_uv;
out vec4 final_colors;
uniform sampler2D u_fog_src;
void main() {
    vec3 src = texture(u_fog_src, v_uv).rgb;
    float z = vol_fog_scene_dist(v_uv);
    vec4 f = vol_fog(v_uv, z, vol_fog_dither(gl_FragCoord.xy));
    final_colors = vec4(src * f.a + f.rgb, 1.0);
}
'''

DOF_BODY = '''
in vec2 v_uv;
out vec4 final_colors;
uniform sampler2D u_dof_src;
void main() { final_colors = vec4(dof_apply(v_uv), 1.0); }
'''

MB_BODY = '''
in vec2 v_uv;
out vec4 final_colors;
void main() { final_colors = vec4(mb_apply(v_uv), 1.0); }
'''

PRESENT_BODY = '''
in vec2 v_uv;
out vec4 final_colors;
uniform sampler2D u_screen;
void main() { final_colors = vec4(texture(u_screen, v_uv).rgb, 1.0); }
'''


def _fs(body_parts):
    return '#version 330 core\n' + '\n'.join(body_parts)


# --------------------------------------------------------------- 管线 ---
class PbrFramePipeline:
    """帧图驱动的全量深度效果管线（pbr profile 的渲染循环）。"""

    def __init__(self, w, h, renderer, window):
        self.w, self.h = int(w), int(h)
        self.r = renderer                    # world3d Renderer（program/post/scene_target）
        self.window = window
        self.pack = None                     # PbrPack（首帧由调用方注入）
        self.shadow_size = _SHADOW_SIZE
        self.n_cascades = _N_CASCADES
        self.focus = 22.0
        self.shutter = 0.55
        self.fog_density = 0.012
        self.prev_vp = None
        self._pos_cache = {}                 # id(md) -> pos vlist（静态复用）
        self._frame_pos_vls = []             # 本帧动态 pos vlist（帧末回收）
        self._build_programs()
        self._build_targets()
        # ---- 帧图：先声明，再编译 ----
        from world3d.engine.framegraph import standard_3d_plan
        self.graph = standard_3d_plan(shadows=True, fog=True, dof=True,
                                      motionblur=True, tonemap=True)
        # present（写 backbuffer，side_effect）必须保留——禁掉它计划就是空的
        self.plan = self.graph.compile()
        self.disabled = []
        for name in ('fog_pass', 'dof_pass', 'motionblur_pass'):
            if os.environ.get('NIULAI_PBR_OFF', '').find(name.split('_')[0]) >= 0:
                self.graph.disable(name)
                self.disabled.append(name)
        self.plan = self.graph.compile()

    # ------------------------------------------------------------ 资源 --
    def _tex(self, w, h, r32f=False):
        from pyglet.gl import GL_R32F, GL_NEAREST, GL_RED, GL_TEXTURE_2D
        from pyglet.image import Texture
        from world3d.engine.targets import create_texture
        if r32f:
            # R32F 线性距离图（pyglet 直建；NEAREST 采样——距离不许插值模糊）
            return Texture.create(w, h, GL_TEXTURE_2D, GL_R32F,
                                  GL_NEAREST, GL_NEAREST, GL_RED)
        from pyglet.gl import GL_RGBA16F, GL_RGBA
        return create_texture(w, h, internalformat=GL_RGBA16F, fmt=GL_RGBA)

    def _fbo(self, w, h, r32f=False):
        from pyglet.gl import GL_COLOR_ATTACHMENT0, GL_DEPTH_ATTACHMENT, \
            GL_DEPTH_COMPONENT24
        from pyglet.image.buffer import Renderbuffer
        from pyglet.image import Framebuffer
        tex = self._tex(w, h, r32f=r32f)
        fbo = Framebuffer()
        fbo.attach_texture(tex, attachment=GL_COLOR_ATTACHMENT0)
        fbo.attach_renderbuffer(Renderbuffer(w, h, GL_DEPTH_COMPONENT24),
                                attachment=GL_DEPTH_ATTACHMENT)
        return dict(tex=tex, fbo=fbo, size=(w, h))

    def _build_targets(self):
        w, h = self.w, self.h
        self.t_distance = self._fbo(w, h, r32f=True)
        self.t_shadow = [self._fbo(self.shadow_size, self.shadow_size,
                                   r32f=True)
                         for _ in range(self.n_cascades)]
        self.t_fog = self._fbo(w, h)
        self.t_dof = self._fbo(w, h)
        self.t_mb = self._fbo(w, h)
        self.t_ldr = self._fbo(w, h)

    # -------------------------------------------------------- 着色器 --
    def _build_programs(self):
        self.prog_dist = ShaderProgram(Shader(DIST_VS, 'vertex'),
                                       Shader(DIST_FS, 'fragment'))
        self.prog_shadow = ShaderProgram(Shader(SHADOW_VS, 'vertex'),
                                         Shader(SHADOW_FS, 'fragment'))
        self.prog_pbr = _shadowed_pbr_program()
        csm_src = csm.csm_glsl(n=self.n_cascades)
        self.progs = {
            'fog_pass': ShaderProgram(
                Shader(FULL_VS, 'vertex'),
                Shader(_fs([csm_src, volumetrics.volumetric_glsl(
                    'vol_fog', 'csm_shadow'), FOG_BODY]), 'fragment')),
            'dof_pass': ShaderProgram(
                Shader(FULL_VS, 'vertex'),
                Shader(_fs([dof_mod.dof_glsl(n=24, blades=6), DOF_BODY]),
                       'fragment')),
            'motionblur_pass': ShaderProgram(
                Shader(FULL_VS, 'vertex'),
                Shader(_fs([mb_mod.mb_glsl(n=12, mode='box'), MB_BODY]),
                       'fragment')),
            'present': ShaderProgram(
                Shader(FULL_VS, 'vertex'),
                Shader(_fs([PRESENT_BODY]), 'fragment')),
        }
        self._quad_cache = {}

    def _quad_draw(self, prog):
        """自建全屏 quad（FULL_VS 布局：position vec2 + uv vec2）。

        ⚠ 不能用 world3d 的 FullscreenQuad：它是 vec3 position 布局，
        喂给本管线的 vec2 程序会报 Invalid data size（实测踩坑）。
        """
        vl = self._quad_cache.get(id(prog))
        if vl is None:
            vl = prog.vertex_list(
                6, GL_TRIANGLES,
                position=('f', (-1.0, -1.0, 1.0, -1.0, 1.0, 1.0,
                                -1.0, -1.0, 1.0, 1.0, -1.0, 1.0)),
                uv=('f', (0.0, 0.0, 1.0, 0.0, 1.0, 1.0,
                          0.0, 0.0, 1.0, 1.0, 0.0, 1.0)))
            self._quad_cache[id(prog)] = vl
        vl.draw(GL_TRIANGLES)

    def _res_tex(self):
        """资源名 -> 纹理（'hdr' = MRT COLOR0；'shadow' = 0 号级联图）。"""
        return {
            'distance': self.t_distance['tex'],
            'shadow': self.t_shadow[0]['tex'],
            'hdr': self.r.scene_target.color[0],
            'hdr_fog': self.t_fog['tex'],
            'hdr_dof': self.t_dof['tex'],
            'hdr_mb': self.t_mb['tex'],
            'ldr': self.t_ldr['tex'],
        }

    def _out_target(self, name):
        res = self.plan.writes_of(name)[0]
        return {'distance': self.t_distance, 'shadow': self.t_shadow[0],
                'hdr_fog': self.t_fog, 'hdr_dof': self.t_dof,
                'hdr_mb': self.t_mb, 'ldr': self.t_ldr}[res]

    def _bind_reads(self, prog, name):
        """按 plan.reads_of 顺序绑纹理（图驱动的落点：别名直通自动生效）。

        buffer 类资源（如 motionblur 的 prev_view_proj）跳过——它走
        uniform（u_mb_vp_prev），不是纹理。
        """
        unit = 0
        shadow_unit = None
        for r in self.plan.reads_of(name):
            res = self.plan.resources.get(r)
            if res is not None and res.kind != 'texture':
                continue
            bind_texture(unit, self._res_tex()[r])
            if r == 'shadow':
                shadow_unit = unit
            unit += 1
        return unit, shadow_unit

    # -------------------------------------------------------- 场景项 --
    def _frame_items(self, meshes, crowd):
        """niulai 每帧网格 -> [(world3d 可绘制物, pos-vlist)]。

        pos-only vlist 供 distance/shadow 两个预 pass 共用（只读 position）；
        静态网格（terrain 等）缓存复用，动态的帧末回收。
        """
        pack = self.pack
        items = []
        for md in meshes:
            pm = pack.static_or_dynamic(md)
            items.append((pm, self._pos_vlist(md, static=pm in
                                              pack.static_meshes())))
        for pose_meshes, bases in (crowd or []):
            kind = (pose_meshes[0].name or 'cow').split(':')[0]
            merged = pack.merged_crowd_geometry(pose_meshes)
            im = pack.crowd_instanced(merged, bases)
            items.append((im, self._pos_vlist(merged, static=False)))
        return items

    def _pos_vlist(self, md, static):
        key = id(md)
        vl = self._pos_cache.get(key)
        if vl is None:
            vl = self.prog_dist.vertex_list(
                md.vertex_count, GL_TRIANGLES, position=('f', md.positions))
            if static:
                self._pos_cache[key] = vl
            else:
                self._frame_pos_vls.append(vl)
        return vl

    # ------------------------------------------------------------ 每帧 --
    def render_frame(self, eye, target, meshes, crowd):
        """一帧：遍历计划派发 pass（图驱动的全部）。"""
        from world3d.engine.camera import Camera
        cam = Camera(position=eye, target=target, fov=55.0, near=0.1, far=600.0)
        aspect = self.w / max(1.0, float(self.h))
        self.cam = cam
        self.items = self._frame_items(meshes, crowd)
        self._cascade_list = self._cascades(cam, aspect)
        # ⚠ WindowBlock 必须从**本管线的 window**设置（world3d Renderer 没有
        # .window 属性——用 hasattr 探测会永远拿到 None，几何画飞只剩天空）
        win = self.window
        if win is not None:
            win.projection = cam.projection(aspect)
            win.view = cam.view_Mat4()
        for name in self.plan.order:
            getattr(self, '_pass_' + name)()
        self.prev_vp = self._vp()
        self._free_frame()

    # ---- 各 pass ----
    def _cascades(self, cam, aspect):
        tf = math.tan(math.radians(cam.fov) / 2.0)
        light_dir = self.pack.sun_dir
        return csm.csm_matrices(mat4_from_Mat4(cam.view_matrix()),
                                cam.near, cam.far * 0.6, tf, aspect,
                                light_dir, n=self.n_cascades,
                                size=self.shadow_size, pad=2.0, snap=True)

    def _vp(self):
        aspect = self.w / max(1.0, float(self.h))
        return mat4_mul(tuple(self.cam.projection(aspect)),
                        mat4_from_Mat4(self.cam.view_matrix()))

    def _pass_depth_prepass(self):
        t = self.t_distance
        t['fbo'].bind()
        glViewport(0, 0, *t['size'])
        glClearColor(1e6, 1e6, 1e6, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.prog_dist.use()
        e = self.cam.position
        self.prog_dist['u_cam'] = (e[0], e[1], e[2])
        for (_pm, vl) in self.items:
            vl.draw(GL_TRIANGLES)
        t['fbo'].unbind()

    def _pass_shadow_pass(self):
        for k in range(self.n_cascades):
            t = self.t_shadow[k]
            t['fbo'].bind()
            glViewport(0, 0, *t['size'])
            glClearColor(1.0, 1.0, 1.0, 1.0)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            self.prog_shadow.use()
            self.prog_shadow['u_light_vp'] = \
                csm.mat4_as_Mat4(self._cascade_list[k]['vp'])
            for (_pm, vl) in self.items:
                vl.draw(GL_TRIANGLES)
            t['fbo'].unbind()

    def _pass_scene_pass(self):
        from pyglet.gl import GL_FRAMEBUFFER, glBindFramebuffer
        if os.environ.get('NIULAI_PBR_DIRECT'):
            glBindFramebuffer(GL_FRAMEBUFFER, 0)      # 诊断：直绘到屏
            glViewport(0, 0, self.w, self.h)
            glClearColor(0.03, 0.04, 0.06, 1.0)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        else:
            t = self.r.scene_target
            t.bind()
            t.clear(color=(0.03, 0.04, 0.06, 1.0), depth=True)
        from pyglet.gl import GL_DEPTH_TEST, glEnable
        glEnable(GL_DEPTH_TEST)
        # 天空（程序化天穹 + IBL 环境）
        self.r._draw_sky(self.cam, self.w / max(1.0, float(self.h)))
        # 几何：优先引擎自己的 _draw_list（battle-tested）；NIULAI_PBR_MYLOOP=1
        # 才走本工程手写循环（阴影化变体调试用）。
        drawables = [pm for (pm, _vl) in self.items]
        if os.environ.get('NIULAI_PBR_MYLOOP'):
            prog = self.prog_pbr
            prog.use()
            start = 0
            if self.pack.env is not None and self.pack.env.baked:
                start = self.pack.env.apply(prog, 0)
            e = self.cam.position
            prog['uCamPos'] = Vec3(*e)
            self._apply_lights(prog)
            self._apply_csm(prog, shadow_unit=10)
            last = None
            for (pm, _vl) in self.items:
                same = pm.material is last
                pm.draw(unit_start=start, skip_material=same)
                last = pm.material
        else:
            self.r._draw_list(drawables, self.cam)
        if not os.environ.get('NIULAI_PBR_DIRECT'):
            t.unbind()

    def _apply_lights(self, prog):
        prog['uPointCount'] = len(self.r.point_lights)
        for i in range(self.r.MAX_POINT_LIGHTS):
            if i < len(self.r.point_lights):
                pos, col = self.r.point_lights[i]
                prog[f'uPointPos{i}'] = Vec3(*pos)
                prog[f'uPointColor{i}'] = Vec3(*col)
            else:
                prog[f'uPointPos{i}'] = Vec3(0, 0, 0)
                prog[f'uPointColor{i}'] = Vec3(0, 0, 0)

    def _apply_csm(self, prog, shadow_unit=10):
        uniforms, splits = csm.csm_uniforms(self._cascade_list)
        for name, val in uniforms.items():
            prog[name] = csm.mat4_as_Mat4(val)
        prog['u_csm_split'] = tuple(float(s) for s in splits)
        prog['u_csm_pcf'] = 1.0
        for k in range(self.n_cascades):
            bind_texture(shadow_unit + k, self.t_shadow[k]['tex'])
            prog[f'u_csm_tex{k}'] = shadow_unit + k

    def _ssao(self):
        s = self.r.post.settings
        if not s.ssao_enabled:
            return None
        aspect = self.w / max(1.0, float(self.h))
        return self.r.post.render_ssao(
            self.r.scene_target.color[1],
            self.cam.projection(aspect),
            csm.mat4_as_Mat4(mat4_inverse(self._vp())))

    def _bind2(self, prog, tex0, tex1):
        bind_texture(0, tex0)
        prog['u_fog_src'] = 0
        bind_texture(1, tex1)
        prog['u_fog_depth'] = 1

    def _pass_fog_pass(self):
        t = self._out_target('fog_pass')
        t['fbo'].bind()
        glViewport(0, 0, *t['size'])
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        prog = self.progs['fog_pass']
        prog.use()
        unit, shadow_unit = self._bind_reads(prog, 'fog_pass')
        prog['u_fog_src'] = 0
        prog['u_fog_depth'] = 1
        uniforms, splits = csm.csm_uniforms(self._cascade_list)
        for name, val in uniforms.items():
            prog[name] = csm.mat4_as_Mat4(val)
        prog['u_csm_split'] = tuple(float(s) for s in splits)
        prog['u_csm_pcf'] = 1.0
        for k in range(self.n_cascades):
            prog[f'u_csm_tex{k}'] = shadow_unit + k
        prog['u_inv_vp'] = list(mat4_inverse(self._vp()))
        e = self.cam.position
        prog['u_fog_cam'] = (e[0], e[1], e[2])
        prog['u_fog_light_dir'] = self.pack.sun_dir
        prog['u_fog_light_color'] = self.pack.env.sun_color
        prog['u_fog_ambient'] = (0.10, 0.12, 0.16)
        prog['u_fog_density'] = self.fog_density
        prog['u_fog_falloff'] = 0.13
        prog['u_fog_base'] = 0.0
        prog['u_fog_phase_g'] = 0.74
        prog['u_fog_steps'] = 40.0
        prog['u_fog_max_dist'] = float(self.cam.far)
        prog['u_fog_analytic'] = 1.0
        prog['u_fog_shafts'] = 0.0
        self._quad_draw(prog)
        t['fbo'].unbind()

    def _pass_dof_pass(self):
        t = self._out_target('dof_pass')
        t['fbo'].bind()
        glViewport(0, 0, *t['size'])
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        prog = self.progs['dof_pass']
        prog.use()
        self._bind_reads(prog, 'dof_pass')
        prog['u_dof_color'] = 0
        prog['u_dof_depth'] = 1
        prog['u_dof_focus'] = self.focus
        prog['u_dof_aperture'] = 0.085 / 2.8
        prog['u_dof_focal'] = 0.085
        prog['u_dof_max_coc'] = 22.0
        prog['u_dof_coc_scale'] = self.h / 0.024
        prog['u_dof_on'] = 1.0
        self._quad_draw(prog)
        t['fbo'].unbind()

    def _pass_motionblur_pass(self):
        t = self._out_target('motionblur_pass')
        t['fbo'].bind()
        glViewport(0, 0, *t['size'])
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        prog = self.progs['motionblur_pass']
        prog.use()
        self._bind_reads(prog, 'motionblur_pass')
        prog['u_mb_color'] = 0
        prog['u_mb_depth'] = 1
        prog['u_mb_inv_vp_cur'] = list(mat4_inverse(self._vp()))
        prog['u_mb_vp_prev'] = list(self.prev_vp if self.prev_vp is not None
                                    else self._vp())
        e = self.cam.position
        prog['u_mb_cam'] = (e[0], e[1], e[2])
        prog['u_mb_shutter'] = self.shutter
        prog['u_mb_samples'] = 12.0
        prog['u_mb_max_len'] = 70.0
        prog['u_mb_on'] = 1.0
        self._quad_draw(prog)
        t['fbo'].unbind()

    def _pass_tonemap_pass(self):
        # ⚠ post.composite() 第一行就 bind_screen（强绑 FB0），进不了中间
        # 目标——这里复刻它的 uniform 体（不含 bind_screen），用同一份引擎
        # composite 着色器写进 t_ldr，present 再上屏。
        from world3d.engine.shaders import get
        ao_tex = self._ssao()
        bloom_tex = None
        src_res = self.plan.reads_of('tonemap_pass')[0]
        src_tex = self._res_tex()[src_res]
        if self.r.post.settings.bloom_enabled:
            bloom_tex = self.r.post.render_bloom(src_tex)
        t = self._out_target('tonemap_pass')
        t['fbo'].bind()
        glViewport(0, 0, *t['size'])
        glDisable(GL_DEPTH_TEST)
        s = self.r.post.settings
        prog = get('composite')
        prog.use()
        bind_texture(0, src_tex)
        prog['uScene'] = 0
        bind_texture(1, bloom_tex or src_tex)
        prog['uBloom'] = 1
        from world3d.engine.postfx import _white_ao
        bind_texture(2, ao_tex if ao_tex is not None else _white_ao())
        prog['uAO'] = 2
        prog['uBloomIntensity'] = s.bloom_intensity if bloom_tex else 0.0
        prog['uExposure'] = s.exposure
        prog['uAOStrength'] = s.ssao_strength if ao_tex else 0.0
        prog['uVignette'] = s.vignette
        prog['uToneMap'] = s.tone_map
        prog['uDebug'] = s.debug
        self.r.quad.draw(prog)
        t['fbo'].unbind()

    def _pass_present(self):
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glViewport(0, 0, self.w, self.h)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        prog = self.progs['present']
        prog.use()
        if os.environ.get('NIULAI_PBR_RAWHDR'):
            bind_texture(0, self._res_tex()['hdr'])     # 诊断：hdr 直上屏
        else:
            bind_texture(0, self._res_tex()[self.plan.reads_of('present')[0]])
        prog['u_screen'] = 0
        self._quad_draw(prog)

    def _free_frame(self):
        """本帧动态 GL 资源回收（pos vlist 由 pack.cleanup_frame 一并处理）。"""
        for vl in self._frame_pos_vls:
            try:
                vl.delete()
            except Exception:
                pass
        self._frame_pos_vls = []
