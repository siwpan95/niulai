# -*- coding: utf-8 -*-
"""渲染 profile：raw（默认，忠实粗粝）/ enhanced（引擎能力展示，默认关闭）。

口径（docs/增强规划_P3.md §三）：粗粝是本项目的**设定**不是缺陷 ——
默认 raw 一刀不动；enhanced 把 world3d 引擎能力接上来，作为"本引擎
能力上限"的可选展示，`--profile enhanced` 显式开启。

enhanced 路径（全部走 world3d 引擎模块，非自研后处理）：
  1. 不透明场景（含 GPU 实例化 / 氛围粒子）-> rt_a；
  2. 水面 WBOIT 透明 pass（world3d.engine.oit：accum/reveal 双 MRT +
     McGuire 距离权重），深度从 rt_a blit 进 oit.rt 保证岸/角色遮挡；
  3. oit.composite(rt_a + water) -> rt_b；
  4. Bloom（world3d.engine.postfx.PostChain：软膝盖阈值 + Karis +
     降采样/上采样金字塔）-> 窗口帧缓冲；
  5. 字幕 overlay（屏幕空间）-> 帧缓冲；capture。

确定性：profile 只改渲染路径、不改姿态（t 纯函数不变）——同 profile
两次渲染（含跨进程）逐帧一致，tests/test_profile.py 钉住。
降级：WBOIT 不可用（无 glBlendFunci）时该步自动跳过（水面回落不透明
绘制仍在 meshes 里——场景的 water() 钩子只在 enhanced 且受支持时启用）。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderProfile:
    """name: raw | enhanced | pbr；wboit/bloom/pbr 为能力开关。"""
    name: str = 'raw'
    wboit: bool = False
    bloom: bool = False
    pbr: bool = False


PROFILES = {
    'raw': RenderProfile('raw'),
    'enhanced': RenderProfile('enhanced', wboit=True, bloom=True),
    # P5 全量 PBR：world3d Renderer（proctex 贴图 + material + env IBL +
    # 程序化天空 + SSAO + Bloom + ACES + 透明排序 + 实例化剔除）
    'pbr': RenderProfile('pbr', bloom=True, pbr=True),
}


def get_profile(name):
    """name -> RenderProfile；未知名抛 ValueError（不静默回落）。"""
    if name not in PROFILES:
        raise ValueError(f'unknown profile: {name!r} '
                         f'(available: {sorted(PROFILES)})')
    return PROFILES[name]
