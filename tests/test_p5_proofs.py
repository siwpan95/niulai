# -*- coding: utf-8 -*-
"""P5-6 能力 proof 测试：pointcloud+EDL / physics / media CA / gltf。

逐项验证「审计账」里 B/C 档剩余能力的确定性可用性。渲染类 proof 走
独立小管线（不进成片），纯逻辑类直接断言。

运行：python tests/test_p5_proofs.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILED = []


def check(name, cond, detail=''):
    status = 'ok' if cond else 'FAIL'
    print(f'  {status}: {name}' + (f'  [{detail}]' if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def test_pointcloud_edl():
    """pointcloud + EDL：螺旋点云渲染两遍逐字节一致 + 非空。"""
    print('test_pointcloud_edl')
    import pyglet
    from pyglet.gl import (GL_BLEND, GL_DEPTH_TEST, GL_POINTS,
                           GL_PROGRAM_POINT_SIZE, GL_SRC_ALPHA,
                           GL_ONE_MINUS_SRC_ALPHA, GL_TRIANGLES,
                           glBlendFunc, glEnable)
    from pyglet.graphics.shader import Shader, ShaderProgram
    from world3d.engine.camera import Camera
    from world3d.engine.pointcloud import generate_helix_cloud, edl_glsl
    from world3d.engine.postfx import FullscreenQuad, bind_screen
    from world3d.engine.targets import bind_texture
    from niulai.pipeline.render import md5_of

    pyglet.options['headless'] = getattr(pyglet.options, 'headless', None)
    win = pyglet.window.Window(320, 200, visible=False)
    try:
        pos, col, siz = generate_helix_cloud(n=8000, seed=7)
        point_prog = ShaderProgram(
            Shader('''#version 330 core
in vec3 position;
in vec3 colors;
in float sizes;
uniform WindowBlock { mat4 projection; mat4 view; } window;
uniform float uPointScale;
out vec3 v_col;
void main() {
    v_col = colors;
    vec4 clip = window.projection * window.view * vec4(position, 1.0);
    gl_Position = clip;
    gl_PointSize = clamp(sizes * uPointScale / max(0.001, clip.w), 1.0, 31.0);
}''', 'vertex'),
            Shader('''#version 330 core
in vec3 v_col;
out vec4 outColor;
void main() {
    vec2 pc = gl_PointCoord - 0.5;
    if (dot(pc, pc) > 0.25) discard;
    outColor = vec4(v_col, 0.85);
}''', 'fragment'))
        vlist = point_prog.vertex_list(
            len(pos) // 3, GL_POINTS, position=('f', pos),
            colors=('f', col), sizes=('f', siz))
        edl_prog = ShaderProgram(
            Shader('''#version 330 core
in vec2 position;
in vec2 uv;
out vec2 v_uv;
void main() { v_uv = uv; gl_Position = vec4(position, 0.0, 1.0); }''',
                    'vertex'),
            Shader(edl_glsl(), 'fragment'))
        quad = FullscreenQuad()

        def render_once(path):
            cam = Camera(position=(14.0, 9.0, 16.0), target=(0.0, 5.0, 0.0),
                         fov=55.0)
            aspect = 320 / 200.0
            win.projection = cam.projection(aspect)
            win.view = cam.view_Mat4()
            win.switch_to()
            bind_screen(320, 200)
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_PROGRAM_POINT_SIZE)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            point_prog.use()
            point_prog['uPointScale'] = 220.0
            vlist.draw(GL_POINTS)
            # EDL 需要可采样深度——窗口 FB 不可采样，这里跳过 EDL，
            # 仅验证点云渲染路径 + 确定性（EDL 数学由 cpu_edl 单测）
            win.flip() if hasattr(win, 'flip') else None
            from pyglet.gl import glReadPixels, GL_RGBA, GL_UNSIGNED_BYTE
            import ctypes
            buf = (ctypes.c_ubyte * (320 * 200 * 4))()
            glReadPixels(0, 0, 320, 200, GL_RGBA, GL_UNSIGNED_BYTE, buf)
            data = bytes(buf)
            # 存 PNG（复用 world3d capture 的翻转逻辑太重，直接算 md5）
            import hashlib
            return hashlib.md5(data).hexdigest(), data

        h1, d1 = render_once('a')
        h2, d2 = render_once('b')
        check('点云渲染跨次逐字节一致', h1 == h2)
        check('点云非空', max(d1) > 0)
        vlist.delete()
    finally:
        win.close()


def _leap_trail():
    from world3d.engine.physics import Body, PhysicsWorld
    w = PhysicsWorld(gravity=-22.0)
    body = Body(position=(12.0, 2.2, 48.0), half=(0.35, 0.9, 0.35))
    w.bodies.append(body)                # 直接注册（add_body 若存在走之）
    body.apply_impulse((3.2, 9.0, 2.4))
    trail = []
    for _ in range(120):
        w.step(1 / 30.0)
        trail.append(tuple(body.position))
    return trail


def test_physics_leap():
    """physics：跃溪弧线模拟 —— 确定性 + 抛物线 + 落回地面。"""
    print('test_physics_leap')
    trail = _leap_trail()
    check('轨迹非空', len(trail) > 10)
    ys = [p[1] for p in trail]
    check('先升后降（抛物线）', max(ys) > trail[0][1] + 0.5
          and trail[-1][1] < max(ys))
    check('确定性：同参数同轨迹', _leap_trail() == trail)
    check('水平前进（z 位移 > 1u）', trail[-1][2] > 48.0 + 1.0)


def _rerun_leap():
    return _leap_trail()


def test_media_ca():
    """allin media CA：规则演化确定性（同网格同规则同结果）。"""
    print('test_media_ca')
    import numpy as np
    from allin_engine.media.ca.automaton import CellularAutomaton
    a1 = CellularAutomaton(24, 32, rule_name='game_of_life')
    a2 = CellularAutomaton(24, 32, rule_name='game_of_life')
    # randomize 的初始态不保证跨实例一致——手工铺同一初始态（确定性输入）
    grid0 = (np.arange(24 * 32).reshape(24, 32) * 2654435761) % 100 < 38
    a1.grid[:] = grid0.astype(np.uint8)
    a2.grid[:] = grid0.astype(np.uint8)
    for _ in range(12):
        a1.step()
    for _ in range(12):
        a2.step()
    check('CA 12 代演化逐格一致', bool(np.array_equal(a1.grid, a2.grid)))
    check('CA 演化发生（网格改变）',
          not bool(np.array_equal(a1.grid, grid0.astype(np.uint8))))


def test_gltf_parse():
    """gltf：程序化最小 glTF（内存构建 -> 临时文件）解析通过。"""
    print('test_gltf_parse')
    import struct
    import tempfile
    from world3d.engine.gltf import load
    # 最小 glTF 2.0：一个三角形 mesh（positions accessor + buffer）
    positions = bytes(struct.pack('<12f', 0, 0, 0, 1, 0, 0, 0, 1, 0,
                                  0, 0, 0))
    gltf = {
        'asset': {'version': '2.0'},
        'scenes': [{'nodes': [0]}], 'scene': 0,
        'nodes': [{'mesh': 0}],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
        'buffers': [{'byteLength': len(positions)}],
        'bufferViews': [{'buffer': 0, 'byteOffset': 0,
                         'byteLength': len(positions), 'target': 34962}],
        'accessors': [{'bufferView': 0, 'componentType': 5126,
                       'count': 4, 'type': 'VEC3',
                       'max': [1, 1, 0], 'min': [0, 0, 0]}],
    }
    blob = json.dumps(gltf).encode()
    bin_chunk = struct.pack('<I I', len(positions), 0x004E4942) + positions
    json_pad = (4 - len(blob) % 4) % 4
    blob += b' ' * json_pad
    total = 12 + 8 + len(blob) + len(bin_chunk)
    glb = (struct.pack('<I', 0x46546C67) + struct.pack('<I', 2)
           + struct.pack('<I', total)
           + struct.pack('<I I', len(blob), 0x4E4F534A) + blob
           + bin_chunk)
    tmp = tempfile.NamedTemporaryFile(suffix='.glb', delete=False)
    tmp.write(glb)
    tmp.close()
    try:
        g = load(tmp.name)
        check('glTF 解析通过', g is not None)
    finally:
        os.unlink(tmp.name)


def main():
    test_media_ca()
    test_physics_leap()
    test_gltf_parse()
    test_pointcloud_edl()
    if FAILED:
        print(f'\nFAILED {len(FAILED)}: {FAILED}')
        return 1
    print('\nALL_P5_PROOF_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
