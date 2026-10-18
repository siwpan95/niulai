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

## P1 状态（已交付代码 + proof 切片，全幕渲染进行中）

- [x] **渲染提速 13.3×**：raw pipe 直喂 ffmpeg（帧缓冲原始字节走 stdin，跳过高压缩 PNG）——
      实测 1.9 → 25.3 fps@720p（`scripts/bench_render.py`）；全片 154,800 帧约 1.7 小时
- [x] **对白字幕系统**：SubtitleTrack（正交投影 + view 置单位矩阵画 HUD；
      台词库取自原片 wikiquote/头条整理，同人学习口径）
- [x] **allin-engine 全量接入**：
  - `brains/world.py` CastWorld：ECS 实体注册表（牛来/妈妈/云玎/牛群36/狼群10/蛇/豹拉）+ Transform/CastState 组件；
    场景每帧从快照读姿态（单向数据流，防漂移）
  - `brains/migration.py`：牛群迁徙编队（领队路径 + 6×6 槽位 + 哈希抖动），HERD_SIZE=36（口径 30-50）
  - `brains/wolves.py`：狼群环伺/冲锋/撕咬态势纯函数 + **CombatEngine 固定种子无头战斗**
    （31 条节拍驱动第四幕总攻编排，两次运行逐字相同）
  - `bridge/events.py`：niulai 事件 ↔ allin EventBus 扇出
- [x] **角色阵容扩充**：`cast/quadruped.py` 规格驱动四足骨架（牛妈妈/豹拉/狼/牛群共用，
  枢轴在髋的摆步 + 卧伏/站立/走/跑四姿态）+ 草蛇（9 段蠕动）+ 歪脖子树（程序化地标）
- [x] **程序化 OST 三主题**：迁徙（进行曲）/ 友情（慢板）/ 狼袭（紧张），
  allin `MusicPattern` + `generate_music_wav` 渲染 180s WAV，随幕混音
- [x] **四幕实现 + proof 切片**（各 10-15s @720p，逐帧目检通过）：
  站不起来（清晨母子）/ 迁徙与过溪（36 头牛群编队渡河）/ 豹拉（初遇分奶约法三章）/ 狼袭与母亡（夜戏、树下决战、母亲牺牲）
- [x] **测试扩到 85 项**：群体规模口径、编队确定性、战斗节拍确定性、字幕时间窗不重叠、
  OST 渲染、跨进程确定性（pipe 路径帧 md5 相同）

## P1 验收（2026-10-16 已完成）

- **四幕全幕渲染完成**（第三轮，三轮实战见 CHANGELOG 0.2.1/0.2.2）：
  | 幕 | 时长 | 帧数 | 音轨 | 渲染吞吐 |
  |----|------|------|------|----------|
  | act1 站不起来 | 5:00 | 9,000 | —（静音） | 7.6 fps |
  | act2 迁徙与过溪 | 12:00 | 21,600 | 迁徙 OST | 4.5 fps |
  | act3 豹拉 | 12:00 | 21,600 | 友情 OST | 6.6 fps |
  | act4 狼袭与母亡 | 18:00 | 32,400 | 狼袭 OST | 6.3 fps |
- **合片**：`output/牛来_P1_四幕_47min.mp4`（47:00.02，1280×720@30fps，h264+aac，
  四幕 concat，三处过缝帧帧唯一无重复，全量解码无错误）
- **验收方式**：逐幕 ffprobe（时长/音轨/分辨率）+ 全镜头逐帧抽检（17 镜头全覆盖）
  + 过缝 md5 比对

## P2 状态（代码已交付，全幕渲染进行中）

- [x] **act5 传承决战**：岁月更迭（**逐帧大气系统**：天空/雾/色调白昼→黄昏→夜→黎明）、
  成年牛来 + 成年豹拉、重回牺牲之地（歪脖子树）、豹拉复刻妈妈嘱托断后、
  盗猎车 + 盗猎人登场、牛来战吼引开
- [x] **act6 梦醒而立（全片眼）**：开幕与 act1 **同一构图**（机位 + 角色位置逐分量复位，
  测试断言）；奋力站起（腿绕髋顶拉伸、蹄的绝对高度守恒、躯干单调抬升，测试钉住）；
  云雀高飞；见父亲得认可
- [x] **act7 片尾**：一家三口 + 牛群 + 云雀金色黄昏定格；staff 字幕明确标注
  **同人学习性复刻属性与原作信息**；片尾主题（致敬《雨后清风有香》的程序化民谣）
- [x] **1080p 冲刺**：act5-7 按 1920×1080 渲染（实测 4.9fps）
- [x] 新角色：成年牛来（ADULT_NIULAI_SPEC）、牛爸爸、盗猎人 + 盗猎车（程序化）
- [x] 测试扩到 **100+ 项**：循环断言（act6↔act1）、rise 包络、大气 U 形曲线

**全片合拢（2026-10-16 已完成）**：`output/牛来_86分钟_全片_1080p.mp4`
（86:00.02，1920×1080@30fps，h264+aac，735MB）——
八幕全片：序幕 6:00 + 站不起来 5:00 + 迁徙 12:00 + 豹拉 12:00 + 狼袭 18:00
+ 传承决战 15:00 + 梦醒而立 12:00 + 片尾 6:00。
P1 四幕 lanczos 升采 1080p；act5-7 原生 1080p；七处过缝帧帧唯一
（md5 验证无重复无跳空）；全量解码无错误。装配脚本：`scripts/assemble_final.py`。

## 快速开始

### 0) 环境自举（新机器先跑这一步）

```bat
:: 建 venv + 装依赖 + 探测 ffmpeg（不硬编码任何本机专属路径）
python scripts\bootstrap.py
python scripts\bootstrap.py --python E:\py313\python.exe   :: 指定解释器
python scripts\bootstrap.py --ffmpeg E:\ffmpeg\bin\ffmpeg.exe

:: 体检：Python / venv / 依赖 / ffmpeg / 磁盘，输出 PASS-WARN-FAIL 表
python scripts\check_env.py
```

`bootstrap` 找不到 ffmpeg 会**打印下载指引并以退出码 1 结束**——不静默失败，
避免几小时渲染后才在拼装阶段撞墙。`ffmpeg` 也可一次性固化为环境变量：

```bat
setx NIULAI_FFMPEG E:\ffmpeg\bin\ffmpeg.exe
```

### 1) 测试 / 看结构

```bat
.venv\Scripts\python.exe tests\test_smoke.py
.venv\Scripts\python.exe tests\test_determinism.py --frames 3
.venv\Scripts\python.exe -m niulai info
```

### 2) 渲染序幕前 60s 并拼装 MP4

```bat
.venv\Scripts\python.exe -m niulai render --act act0_prologue ^
    --start 0 --end 1800 --size 1280x720 --out output\act0_60s ^
    --assemble output\牛来_序幕_荒漠飞雀_60s.mp4 --ffmpeg E:\ffmpeg\bin\ffmpeg.exe
```

设置过 `NIULAI_FFMPEG` 后可省略 `--ffmpeg`。

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
tests/           冒烟 + 跨进程确定性 + 实例化
scripts/         工程脚本
  bootstrap.py     环境自举（venv + 依赖 + ffmpeg 探测）—— 新机器第一步
  check_env.py     环境体检（PASS/WARN/FAIL 表，退出码可用于 CI）
  assemble_final.py 八幕合片 + 全长 OST 混音
  voice_mix.py     六幕对白 + OST 混音 + 重封装
  contact_sheet.py 38 镜头联络图（单文件 HTML）
  render_parallel.py 分块并行渲染（P3-2：切块 + N 进程并发 + --resume + concat）
  bench_render.py  渲染吞吐基准
docs/             分幕脚本 / 借鉴记账 / TTS 试水报告 / 增强规划
```

## 已知限制（如实列）

- 群体戏渲染 ~5-7 fps@720p（36 头牛 × 13 盒体段的 CPU 合并不便宜）。
  P3 已交付 GPU 实例化（act2/4/7 群体一次 draw call，2.0× 吞吐）与
  **分块并行渲染**（`scripts/render_parallel.py`，默认 2 分钟一块、N 进程并发，
  实测 2 workers 1.66×；块失败只损失 2 分钟，`--resume` 续跑）。
  单进程跑满 154,800 帧仍需小时级——并行度受 CPU 核数与显存约束
- SAPI 只有一个中文语音（Huihui），多角色同嗓——**默认设定**，保留。
  多角色配音已作为 opt-in 引擎交付：`python -m niulai.audio.tts --engine edge`
  或 `scripts/voice_mix.py --engine edge`（角色各一嗓、act5-6 自动切成年嗓、
  超窗按语速重合成；单句失败自动回退 sapi）。需联网 + ffmpeg
- OST 为 180s 循环，长幕会有重复感（P3-3 做程序化变奏段）
- 绿地边缘仍有轻微圆形残留（噪声调制后改善，未根治）
- **环境依赖**：ffmpeg 为拼装硬依赖，本机缺失时 `scripts/check_env.py` 会报 FAIL；
  无 NVIDIA 独显的机器上，GPU 系方案（神经 TTS / 生成式配乐 / 超分）均不可跑，
  规划中已标注降级路径

## 许可

MIT（见 LICENSE）。依赖的 3dworld / allin-engine 均为 siwpan 自研 MIT；
借鉴记账见 `docs/REFERENCE.md`。
