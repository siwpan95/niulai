# -*- coding: utf-8 -*-
"""角色包：程序化"手搓"角色 —— 盒体段骨架 + 姿态纯函数。

设计口径（忠实粗粝手搓感）：
- 全部角色 = 盒体段拼装（world3d.engine.geometry.box），零外部模型文件；
- 每面一个明暗档（CPU 烘焙伪 lambert），不用 PBR —— "B 超画质"是特征；
- 姿态 = t 的纯函数，动画按 12fps 量化（见 niulai.timeline.Timeline.quantize）；
- 关节僵硬、穿模容忍：参数在 perf.py，测试在 tests/ 钉住包络。
"""
