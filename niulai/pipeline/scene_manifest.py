# -*- coding: utf-8 -*-
"""每幕场景清单（结构 + 参数，不含顶点）—— world3d ``serialize``/``scene_build``。

产出 ``output/manifests/<act>.scene.json``：镜头关键帧、网格清单（名字/顶点数）、
光照环境、以及一份可被 ``world3d.engine.serialize.loads`` 还原的 Scene 结构。

为什么只存结构：顶点动辄几十万（act2 地形 218,886 顶点），进 JSON 既慢也没意义；
几何由程序化生成器按名字重建——这正是引擎 ``serialize`` 的设计口径。

用途（都不是装饰）：
1. **复现依据**：成片每幕的相机/环境参数可查，换机器或改代码后能定位漂移；
2. **结构校验**：``scene_build.validate`` 会实际试构建 mesh 定义，挡住参数拼写错误；
3. **热重载底稿**：``SceneWatcher`` 的 JSON 格式即是本文件，调光时可直接改。
"""
import json
import os

from world3d.engine.env import LightEnvironment
from world3d.engine.scene import Node, Scene

from .pbr_bridge import ACT_ENVS, ACT_POINT_LIGHTS


def _env_for(act):
    kw = dict(ACT_ENVS.get(act, ACT_ENVS['act2']))
    return LightEnvironment(**kw)


def build(act, scene, frames, samples=8):
    """act + 场景实例 -> 清单 dict（纯函数：同输入同输出）。"""
    a0, a1 = frames
    # 关键帧：等距采样 + 幕首幕尾（相机轨迹足够复现构图）
    times = [round(a0 / 30.0 + (a1 - a0) / 30.0 * i / max(1, samples - 1), 3)
             for i in range(samples)]
    keys = []
    for t in times:
        eye, target = scene.camera(t)
        meshes = scene.meshes(t)
        keys.append({
            't': t,
            'eye': [round(float(x), 4) for x in eye],
            'target': [round(float(x), 4) for x in target],
            'meshes': sorted({(md.name or 'unnamed') for md in meshes}),
            'vertex_total': sum(md.vertex_count for md in meshes),
        })

    # 结构 Scene：只放节点（几何按名字重建），供 serialize 还原
    sc = Scene(name=f'niulai/{act}')
    sc.environment = _env_for(act)
    for tag, xy in ACT_POINT_LIGHTS.get(act, []):
        n = Node(name=f'point_light:{tag[0]:.1f},{tag[1]:.1f}')
        n.user_data = {'color': list(xy)}
        sc.add(n)
    for i, k in enumerate(keys):
        for mname in k['meshes']:
            n = Node(name=f'key{i:02d}/{mname}')
            n.user_data = {'t': k['t']}
            sc.add(n)

    data = sc.to_dict()
    data['niulai'] = {
        'act': act,
        'frames': [a0, a1],
        'fps': 30,
        'keyframes': keys,
        'mesh_inventory': sorted({m for k in keys for m in k['meshes']}),
    }
    return data


def verify(data):
    """scene_build.validate + serialize 往返。返回 (issues, roundtrip_ok)。"""
    from world3d.engine import serialize
    from world3d.engine.scene_build import validate

    issues = validate(data)
    errs = [i for i in issues if i[0] == 'error']
    text = serialize.dumps(_as_scene(data))
    back = serialize.loads(text)
    ok = back.name == data.get('name') and \
        len(list(back.root.traverse())) == len(list(_as_scene(data).root.traverse()))
    return errs, ok


def _as_scene(data):
    from world3d.engine.scene import Scene
    s = Scene.from_dict({k: v for k, v in data.items()
                         if k in ('name', 'root', 'environment')})
    return s


def write(data, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{data['niulai']['act']}.scene.json")
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path
