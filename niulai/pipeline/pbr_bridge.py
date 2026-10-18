# -*- coding: utf-8 -*-
"""PBR 桥：niulai 每帧姿态 -> world3d Renderer 全 PBR 管线（P5-1）。

覆盖的 world3d 能力（引擎能力审计 A/B 档）：
- `renderer.Renderer`：场景 -> MRT(HDR+法线深度) -> 天空 -> SSAO -> Bloom
  -> 合成（曝光/ACES/暗角/gamma）——**enhanced 的目标形态**；
- `scene.Scene` / `mesh.Mesh` / `mesh.InstancedMesh`（pbr/pbr_inst 程序）；
- `material.Material`（金属-粗糙度 PBR，alpha_mode BLEND 走渲染器半透明路径）；
- `proctex`：程序化贴图（fBm -> albedo/mr/normal，磁盘不存像素）+ 自拼水面图案；
- `env.LightEnvironment`：程序化天空 + IBL 三件套烘焙（每幕专属太阳/天色）；
- `texproj`：世界->UV 线性投影（地形平面投影 + 盒体 triplanar）；
- `geometry.compute_normals/compute_tangents`；
- `camera.Camera`（niulai eye/target 直接映射）+ frustum 剔除（render 内部）。

确定性（本工程铁律在 PBR 路径的落地）：
- proctex 全部图案带 seed，`PATTERN_CACHE` 键控缓存；
- SSAO 噪声图引擎侧确定性生成（postfx 注释明示）；
- 相机/姿态/实例矩阵是 t 的纯函数；材质参数是常量表；
- **逐帧资源回收**：动态 Mesh/InstancedMesh 每帧新建，渲染后 delete()
  （GL 资源不回收会在 21600 帧的长幕里吃光显存——实测口径）。

协议：各幕网格需带名字（rig._bake 已补 `kind:part`；desert/river/tree
建造器自带名），材质按名字前缀映射（MAT_SPEC）。
"""

import math

from world3d.engine import proctex
from world3d.engine.env import LightEnvironment
from world3d.engine.geometry import MeshData
from world3d.engine.material import Material
from world3d.engine.mesh import InstancedMesh, Mesh
from world3d.engine.scene import Scene
from world3d.engine.texproj import UvProjection, dominant_axis, project_uv

from .. import MASTER_SEED

_SEED = int(MASTER_SEED) & 0xFFFF

# --------------------------------------------------------------- 材质表 --
# 名字前缀 -> (图案名, base_color, metallic, roughness, alpha_mode, alpha)
# 图案全部来自 proctex 程序化生成器（磁盘零像素，kkrieger 精神）。
MAT_SPEC = {
    'desert': ('dune', (0.62, 0.52, 0.38), 0.0, 0.95, 'OPAQUE', 1.0),
    'river': ('water', (0.22, 0.34, 0.42), 0.35, 0.18, 'BLEND', 0.72),
    'crooked_tree': ('wood_planks', (0.36, 0.25, 0.16), 0.0, 0.85,
                     'OPAQUE', 1.0),
    'cow': ('plaster', (0.44, 0.33, 0.24), 0.0, 0.80, 'OPAQUE', 1.0),
    'mother': ('plaster', (0.44, 0.33, 0.24), 0.0, 0.80, 'OPAQUE', 1.0),
    'niulai': ('plaster', (0.40, 0.30, 0.22), 0.0, 0.80, 'OPAQUE', 1.0),
    'calf': ('plaster', (0.66, 0.55, 0.42), 0.0, 0.80, 'OPAQUE', 1.0),
    'leopard': ('brushed', (0.62, 0.46, 0.22), 0.0, 0.70, 'OPAQUE', 1.0),
    'wolf': ('brushed', (0.32, 0.32, 0.34), 0.0, 0.75, 'OPAQUE', 1.0),
    'snake': ('dragon_scale', (0.26, 0.42, 0.24), 0.0, 0.55, 'OPAQUE', 1.0),
    'skylark': ('snow', (0.80, 0.78, 0.72), 0.0, 0.70, 'OPAQUE', 1.0),
}
DEFAULT_MAT_KEY = 'cow'

# 每幕光照环境：太阳方向/色温 + 天空三色（程序化天穹 + IBL 烘焙一次）
ACT_ENVS = {
    'act0': dict(sun_dir=(0.62, 0.28, 0.30), sun_color=(1.0, 0.82, 0.62),
                 sun_intensity=1.1, sky_zenith=(0.30, 0.42, 0.66),
                 sky_horizon=(0.86, 0.66, 0.44), sky_ground=(0.30, 0.24, 0.18),
                 ibl_intensity=0.42),
    'act1': dict(sun_dir=(0.55, 0.42, 0.25), sun_color=(1.0, 0.90, 0.74),
                 sun_intensity=1.2, sky_zenith=(0.34, 0.50, 0.76),
                 sky_horizon=(0.90, 0.78, 0.58), sky_ground=(0.34, 0.30, 0.22),
                 ibl_intensity=0.45),
    'act2': dict(sun_dir=(0.30, 0.88, 0.20), sun_color=(1.0, 0.97, 0.90),
                 sun_intensity=1.0, sky_zenith=(0.26, 0.46, 0.78),
                 sky_horizon=(0.62, 0.68, 0.66), sky_ground=(0.36, 0.30, 0.22),
                 ibl_intensity=0.55),
    'act3': dict(sun_dir=(0.72, 0.50, -0.30), sun_color=(1.0, 0.92, 0.78),
                 sun_intensity=1.25, sky_zenith=(0.32, 0.48, 0.76),
                 sky_horizon=(0.88, 0.76, 0.56), sky_ground=(0.38, 0.32, 0.24),
                 ibl_intensity=0.45),
    'act4': dict(sun_dir=(-0.30, 0.70, 0.45), sun_color=(0.55, 0.66, 0.90),
                 sun_intensity=0.35, sky_zenith=(0.05, 0.07, 0.13),
                 sky_horizon=(0.12, 0.15, 0.24), sky_ground=(0.04, 0.04, 0.06),
                 ibl_intensity=0.45),
    'act5': dict(sun_dir=(0.80, 0.20, 0.35), sun_color=(1.0, 0.72, 0.46),
                 sun_intensity=1.15, sky_zenith=(0.24, 0.34, 0.58),
                 sky_horizon=(0.94, 0.58, 0.34), sky_ground=(0.26, 0.18, 0.13),
                 ibl_intensity=0.48),
    'act6': dict(sun_dir=(0.50, 0.62, 0.28), sun_color=(1.0, 0.94, 0.84),
                 sun_intensity=1.3, sky_zenith=(0.32, 0.52, 0.82),
                 sky_horizon=(0.86, 0.80, 0.64), sky_ground=(0.38, 0.33, 0.25),
                 ibl_intensity=0.45),
    'act7': dict(sun_dir=(0.86, 0.14, -0.25), sun_color=(1.0, 0.66, 0.36),
                 sun_intensity=1.05, sky_zenith=(0.22, 0.30, 0.54),
                 sky_horizon=(0.96, 0.52, 0.28), sky_ground=(0.24, 0.15, 0.10),
                 ibl_intensity=0.50),
}

# 每幕点光（≤4 盏；act4 夜袭营火）
ACT_POINT_LIGHTS = {
    'act4': [((10.0, 2.2, 66.5), (1.0, 0.55, 0.22))],
}


# --------------------------------------------------------------- 贴图 ----
def _water_pattern(size=256, seed=41):
    """自拼水面图案：双向 fBm 波纹 -> albedo/mr/normal（走 proctex 低层 API）。"""
    base, mr, h = proctex._blank(size), proctex._blank(size), [0.0] * (size * size)
    for y in range(size):
        for x in range(size):
            u, v = x / size, y / size
            n1 = proctex.fbm(u * 2.0, v * 5.0, 3, cells=6, seed=seed)
            n2 = proctex.fbm(u * 5.0, v * 2.0, 3, cells=5, seed=seed + 7)
            w = 0.5 + 0.25 * math.sin((n1 + n2) * 6.2831)
            _b = (66 + 40 * w, 96 + 42 * w, 118 + 40 * w)
            proctex._px(base, size, x, y, int(_b[0]), int(_b[1]), int(_b[2]))
            proctex._px(mr, size, x, y, 60, 255, 6)      # 低粗糙高反射
            h[y * size + x] = w * 0.6
    return dict(base=bytes(base), mr=bytes(mr),
                normal=proctex.height_to_normal(h, size, 1.6), size=size)


def _tex(name):
    """图案名 -> (base_tex, mr_tex, normal_tex)（PATTERN_CACHE 键控，跨帧复用）。"""
    if name == 'water':
        pat = _water_pattern(seed=_SEED)
    else:
        maker = getattr(proctex, f'make_{name}')
        pat = maker(seed=_SEED + sum(ord(c) for c in name))
    cid = f'niulai:{name}'
    return (proctex.texture(pat, 'base', cid),
            proctex.texture(pat, 'mr', cid),
            proctex.texture(pat, 'normal', cid))


_MAT_CACHE = {}


def mat_for(name):
    """网格名 -> Material（按前缀匹配 MAT_SPEC；缓存复用同一实例，
    渲染器对相邻同材质对象跳过重复 apply）。"""
    if name in _MAT_CACHE:
        return _MAT_CACHE[name]
    key = DEFAULT_MAT_KEY
    for prefix in MAT_SPEC:
        if name.startswith(prefix):
            key = prefix
            break
    pat_name, base, metallic, rough, mode, alpha = MAT_SPEC[key]
    base_tex, mr_tex, normal_tex = _tex(pat_name)
    m = Material(name=f'niulai:{key}', base_color=base, metallic=metallic,
                 roughness=rough, base_tex=base_tex, mr_tex=mr_tex,
                 normal_tex=normal_tex, alpha_mode=mode, alpha=alpha)
    _MAT_CACHE[name] = m
    return m


# --------------------------------------------------------------- UV ----
def _planar_uvs(md, tile=16.0, axis='y'):
    """地形/水面：texproj 平面投影（from_tile：一张贴图盖 tile 个世界单位）。"""
    proj = UvProjection.from_tile(tile, axis=axis)
    uvs = []
    for i in range(md.vertex_count):
        p = md.positions[i * 3:i * 3 + 3]
        uvs.extend(project_uv(p, proj))
    return uvs


def _triplanar_uvs(md, tile=2.5):
    """盒体角色：按法线主轴选投影面（texproj dominant_axis）——六面同规则。"""
    projs = {ax: UvProjection.from_tile(tile, axis=ax) for ax in ('x', 'y', 'z')}
    uvs = []
    for i in range(md.vertex_count):
        p = md.positions[i * 3:i * 3 + 3]
        n = md.normals[i * 3:i * 3 + 3]
        uvs.extend(project_uv(p, projs[dominant_axis(n)]))
    return uvs


def _pbr_prepare(md, kind):
    """MeshData 补 normals/uvs/tangents（引擎自带的确定性几何工具）。"""
    if not md.normals:
        md.compute_normals()
    if not md.uvs:
        if kind in ('desert', 'river'):
            md.uvs = _planar_uvs(md, tile=16.0 if kind == 'desert' else 8.0)
        else:
            md.uvs = _triplanar_uvs(md)
    if not md.tangents:
        md.compute_tangents()
    return md


# --------------------------------------------------------------- 包 ----
class PbrPack:
    """一幕的 PBR 资产包：环境烘焙 + 材质 + 静态网格缓存 + 每帧场景组装。

    生命周期 = 一个渲染块（场景对象每块新建，pack 随之重建；IBL 烘焙
    一次/块，proctex 纹理走全局缓存跨块复用）。
    """

    def __init__(self, act, w3renderer, pbr_program=None):
        self.act = act                      # 'act0' .. 'act7'
        self.renderer = w3renderer
        self.pbr_program = pbr_program      # 阴影化 PBR 变体（帧图管线注入）
        env_kw = dict(ACT_ENVS.get(act, ACT_ENVS['act2']))
        self.sun_dir = tuple(env_kw.get('sun_dir', (0.5, 0.8, 0.3)))
        self.env = LightEnvironment(**env_kw)
        self.env.bake()
        w3renderer.environment = self.env
        w3renderer.set_point_lights(ACT_POINT_LIGHTS.get(act, []))
        self._static = {}                   # id(md) -> world3d Mesh（缓存）
        self._frame_meshes = []             # 本帧动态（渲染后 delete）

    def static_meshes(self):
        """静态网格 id 集合（帧图管线判定 pos-vlist 是否可复用）。"""
        return set(self._static.keys())

    def static_or_dynamic(self, md):
        """md -> world3d Mesh（静态缓存 / 动态新建并登记帧末回收）。"""
        kind = (md.name or '').split(':')[0]
        if id(md) in self._static or kind in ('desert', 'river',
                                              'crooked_tree'):
            return self._static_mesh(md)
        return self._dyn_mesh(md)

    # ---------------------------------------------------------- 静态 --
    def _static_mesh(self, md):
        m = self._static.get(id(md))
        if m is None:
            kind = (md.name or '').split(':')[0]
            _pbr_prepare(md, kind)
            m = Mesh(md, self.pbr_program or self.renderer.program('pbr'),
                     mat_for(kind), name=md.name or kind)
            self._static[id(md)] = m
        return m

    # ---------------------------------------------------------- 每帧 --
    def camera(self, eye, target, fov=55.0):
        from world3d.engine.camera import Camera
        return Camera(position=eye, target=target, fov=fov, near=0.1, far=600.0)

    def _dyn_mesh(self, md):
        kind = (md.name or '').split(':')[0]
        _pbr_prepare(md, kind)
        m = Mesh(md, self.pbr_program or self.renderer.program('pbr'),
                 mat_for(kind), name=md.name or kind)
        self._frame_meshes.append(m)
        return m

    def build_frame(self, meshes, crowd):
        """(meshes 平铺列表, crowd 组列表) -> world3d Scene（含透明排序数据）。"""
        sc = Scene(name=f'niulai:{self.act}')
        for md in meshes:
            sc.add_mesh(self.static_or_dynamic(md))
        for pose_meshes, bases in (crowd or []):
            merged = self.merged_crowd_geometry(pose_meshes)
            sc.add_mesh(self.crowd_instanced(merged, bases))
        return sc

    @staticmethod
    def _merge(pose_meshes, kind):
        """同一角色的多个 part 合并成一份 InstancedMesh 几何（含 UV/法线）。"""
        pos, nor, uv, tan = [], [], [], []
        for md in pose_meshes:
            _pbr_prepare(md, kind)
            pos.extend(md.positions)
            nor.extend(md.normals)
            uv.extend(md.uvs)
            tan.extend(md.tangents)
        merged = MeshData(pos, normals=nor, uvs=uv, tangents=tan,
                          name=f'{kind}:instanced')
        return merged

    def merged_crowd_geometry(self, pose_meshes):
        """群体戏共享几何（公开口，帧图管线用）。"""
        kind = (pose_meshes[0].name or 'cow').split(':')[0]
        return self._merge(pose_meshes, kind)

    def crowd_instanced(self, merged_md, bases):
        """群体戏实例化网格（world3d InstancedMesh/pbr_inst，帧末回收）。"""
        kind = (merged_md.name or 'cow').split(':')[0]
        im = InstancedMesh(merged_md, self.renderer.program('pbr_inst'),
                           mat_for(kind), capacity=max(1, len(bases)))
        im.write_all([tuple(b) for b in bases])
        im.count = len(bases)
        self._frame_meshes.append(im)
        return im

    def cleanup_frame(self):
        """本帧动态 GL 资源回收（长幕显存安全）。"""
        for m in self._frame_meshes:
            try:
                m.delete()
            except Exception:
                pass
        self._frame_meshes = []


def act_of(scene_name):
    """'act2_migration' -> 'act2'。"""
    return (scene_name or '').split('_')[0]
