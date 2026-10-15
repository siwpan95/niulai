# -*- coding: utf-8 -*-
"""niulai —— 《牛来》双引擎复刻工程。

原片：动画电影《牛来》（信雨萌 导演 / 孙丽芳 编剧，2026-08-05 上映，86 分钟）。
本工程为**同人学习性复刻**：仅个人技术验证，不商用、不传播成片。

架构（见 docs/分幕脚本.md 与 README）：
- 渲染/演出层：world3d（PyPI 包 3dworld）—— 程序化场景 / 角色 / 相机 / 分幕编排 / 成片录制
- 逻辑/智能层：allin_engine（PyPI 包 allin-engine）—— ECS 角色实体 / 行为树 / 战斗 / 世界模型
"""
FILM_TITLE = "牛来"
FPS = 30                      # 成片帧率
MASTER_SEED = 20260805        # 主种子 = 原片上映日（全片程序化生成的唯一随机源）
TOTAL_DURATION = 5160.0       # 全片时长（秒）= 86 min
RESOLUTION = (1280, 720)      # P0/P1 验收分辨率（P2 冲刺 1920x1080）

__version__ = "0.1.0"
