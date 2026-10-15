# niulai —— 《牛来》双引擎复刻工程

用自研双引擎复刻 2026 年现象级"手搓"动画电影**《牛来》**（信雨萌 导演 / 孙丽芳 编剧，
2026-08-05 上映，86 分钟）：初生牛犊"牛来"在一场梦境中历经迁徙、友谊、牺牲与担当，
梦醒后借着梦境之力站了起来。

> **同人学习性复刻**：仅个人技术验证，不商用、不传播成片、不冒名。
> 原片剧情/台词版权归原制片方所有。

## 架构：双引擎分工

| 层 | 引擎 | 职责 |
|----|------|------|
| 渲染/演出 | **world3d**（PyPI: `3dworld`） | 程序化场景/角色/相机/分幕编排/字幕/成片录制 |
| 逻辑/智能 | **allin_engine**（PyPI: `allin-engine`） | ECS 角色实体/行为树/战斗/世界模型/音频合成（P0 仅事件桥接，P1 起全量） |

数据流铁律：**单一事实来源 = allin 世界状态**，world3d 每帧读快照（单向，防漂移）。

## 复刻口径（2026-10-15 定）

1. 完整 86 分钟成片（七幕，见 `docs/分幕脚本.md`）
2. **忠实粗粝手搓感**：低多边形盒体角色、12fps 量化动画、僵硬步态、穿模容忍——
   全部是受控参数（`niulai/cast/perf.py`），不是缺陷
3. allin-engine 全量接入
4. MP4 交付；720p 先行验收，1080p P2 冲刺

## P0 状态（已交付）

- [x] 工程骨架：`pyproject.toml` / venv（3dworld + allin-engine）/ CLI / 测试
- [x] 主时间轴：固定 30fps + 12fps 粗粝量化 + 八幕边界（测试钉住连续覆盖 5160s）
- [x] 角色生成器 v1：牛来（幼态，站不起来——姿态包络有测试）+ 云玎（飞行 + 振翅）
- [x] 序幕"荒漠飞雀"前 60s：确定性值噪声荒漠 + 追雀机位 + 末段双人镜头
- [x] 成片管线：离屏逐帧渲染（visible=False + glReadPixels）→ PNG 序列 → ffmpeg → MP4
- [x] **跨进程确定性**：同 seed 两次渲染逐帧 md5 相同（`tests/test_determinism.py`）
- [x] TTS 试水：SAPI Huihui（离线机械腔，贴合原片）+ edge-tts（在线神经语音）对照，
      报告见 `docs/TTS试水报告.md`
- [x] 冒烟测试全绿（`tests/test_smoke.py`）：时间轴不变量 / 站不起来包络 / 航线有界性 /
      相机防穿地 / 姿态确定性

P0 交付物：`output/牛来_序幕_荒漠飞雀_60s.mp4`（1280×720，30fps，60s）。

## 快速开始

```bat
:: 安装（本机 venv）
E:\Python314\python.exe -m venv .venv
.venv\Scripts\pip install 3dworld allin-engine
.venv\Scripts\pip install -e .[dev]

:: 测试
.venv\Scripts\python.exe tests\test_smoke.py
.venv\Scripts\python.exe tests\test_determinism.py --frames 3

:: 渲染序幕前 60s 并拼装 MP4（ffmpeg 路径按本机改；或设 NIULAI_FFMPEG）
.venv\Scripts\python.exe -m niulai render --act act0_prologue ^
    --start 0 --end 1800 --size 1280x720 --out output\act0_60s ^
    --assemble output\牛来_序幕_荒漠飞雀_60s.mp4 --ffmpeg E:\ffmpeg\bin\ffmpeg.exe

:: 只看结构
.venv\Scripts\python.exe -m niulai info
```

## 目录

```
niulai/          引擎复刻包
  timeline.py      主时间轴（固定步长 + 粗粝量化 + 分幕表）
  cast/            角色：perf.py 参数表 / rig.py 盒体骨架 / calf.py 牛来 / skylark.py 云玎
  scenery/         程序化荒漠高度场 + 顶点色烘焙
  acts/            分幕装配（act0_prologue.py = 序幕）
  bridge/          world3d <-> allin 事件桥接
  pipeline/        成片管线：离屏渲染 + PNG 序列 + ffmpeg 拼装
  cli.py           python -m niulai {render,assemble,info}
tests/           冒烟 + 跨进程确定性
docs/             分幕脚本 / 借鉴记账 / TTS 试水报告
```

## 已知限制（如实列）

- 渲染吞吐 ~1.5 fps @720p（PNG 编码是瓶颈）——全片 154,800 帧需优化
  （P1：raw pipe 直喂 ffmpeg，跳过高压缩 PNG）
- SAPI 只有一个中文语音（Huihui），多角色同嗓——用"同嗓"当作设定，或局部换 edge-tts
- 序幕之后各幕尚未实现（P1/P2 路线图见执行计划）
- 角色是盒体拼装，"穿模"按原片特征保留（CLIP_TOLERANCE < 0）

## 许可

MIT（见 LICENSE）。依赖的 3dworld / allin-engine 均为 siwpan 自研 MIT；
借鉴记账见 `docs/REFERENCE.md`。
