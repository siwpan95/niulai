# Changelog

本项目所有值得注意的变更都会记录在此文件中。
格式基于 Keep a Changelog，版本号遵循语义化版本。

## [0.2.1] - 2026-10-16

### Fixed（全幕渲染实战撞出的三个 bug，均已修 + 回归验证）

- **时间基错位（严重）**：`render_pipe`/`render_range` 把**全片绝对帧号**直接当幕内时间
  传给场景 —— act1-4 的全幕渲染实际渲染的是"最后一镜 + 进度钳位"（act1 的 5 分钟成品
  即错误内容，act2 白跑 5 小时）。现各幕场景声明 `T0`（取自分幕表 ACTS，单一事实来源），
  管线做 `t_local = frame/fps - T0` 换算。
- **ffmpeg 管道死锁（两轮实战）**：stderr 无人读 → 64KB 缓冲灌满 → Python 阻塞写 stdin /
  ffmpeg 阻塞写 stderr，互赌 5 小时零进展。第一修（`for line in` 排空）仍死——
  ffmpeg stats 进度行是 `` 结尾不是 `
`，行迭代卡在等换行；最终修：
  **`read1(65536)` 按块排空线程**。
- **OST 现场循环导致 mux 时间轴狂奔**：`-stream_loop -1` 让 ffmpeg 音轨脱离视频帧
  （238 帧视频已跑到 13 分钟输出时间）。改为 `audio/prepare.py` 预处理——
  先把主题循环裁剪为**精确时长的有限音轨**，再普通混音（+ `-shortest`）。

### Verified

- act1/act2 正确开头渲染验证（300 帧 @5-6fps，时长精确 10.00s，视频+音轨齐全）；
- 抽帧目检：act1 母子全景、act2 36 头集结 + 牛妈妈台词字幕，均正确；
- 冒烟 85 项仍全绿。

## [0.2.0] - 2026-10-16

### Added（P1 · 主体四幕 + allin 全量接入）

- **渲染管线升级**：`pipeline/render.py` 新增 raw pipe 直喂 ffmpeg（`render_pipe`）——
  帧缓冲原始字节走 stdin，跳过高压缩 PNG；实测 1.9 → 25.3 fps@720p（**13.3×**）。
  帧级 md5 清单（manifest）保留，确定性验收不变。
- **对白字幕系统**（`acts/subtitles.py`）：SubtitleTrack + SubtitleOverlay；
  正交投影 + view 置单位矩阵画 HUD（只换 projection 会出巨大斜带——实测踩坑）；
  四幕台词库对齐原片（wikiquote 来源，同人学习口径）。
- **allin-engine 全量接入**：
  - `brains/world.py` CastWorld：ECS 实体注册表 + Transform/CastState 组件 + 快照读取（单向数据流）；
  - `brains/migration.py`：牛群迁徙编队（领队路径 + 6×6 槽位 + 确定性抖动），HERD_SIZE=36（口径 30-50）；
  - `brains/wolves.py`：狼群三阶段态势纯函数 + CombatEngine 固定种子无头战斗（31 节拍驱动总攻编排）；
  - `bridge/events.py`：niulai ↔ allin EventBus 扇出（修复双重投递：本地监听不再重复注册总线）。
- **角色阵容**：`cast/quadruped.py` 规格驱动四足骨架（枢轴在髋的摆步、站/走/跑/卧四姿态）、
  `cast/specs.py`（牛妈妈/豹拉/狼三规格）、`cast/snake.py`（9 段蠕动草蛇）、
  `scenery/tree.py`（歪脖子树——第四幕地标 + 第六幕呼应锚点）、
  `scenery/desert.py` 新增河流谷地 + 水面。
- **程序化 OST 三主题**（`audio/ost.py`）：迁徙/友情/狼袭，allin MusicPattern 渲染 180s WAV，随幕混音。
- **四幕**：act1_stand（清晨母子，含牛来"站不起来"包络测试）、act2_migration（36 头牛群编队渡河）、
  act3_leopard（初遇/分奶/约法三章/分离）、act4_wolves（夜戏 tint、树下决战、母亲牺牲 CastState 事件）。
- **TTS 配音口径落地前置**：docs/TTS试水报告.md（SAPI Huihui 离线 + edge-tts 在线双通路）。

### Fixed

- 四足腿长与躯高不配（蹄陷地 0.39）→ body_y = 腿长 + 躯干半高 + 0.02；
- 四足摆步绕脊柱转（风车腿）→ 枢轴模型重定：几何只挂枢轴、位置全在姿态矩阵；
- 牛来半个身子埋进绿地 → 贴地计算（CALF_BELLY_CLEAR=0.61，蹄恰着地）；
- 低头时口鼻扎草皮 → droop 收敛至 -0.26+0.14w；
- 云雀航线 z 蜿蜒带 ±46 飞不到绿地 → 起终点插值 + 小幅蜿蜒；
- 字幕 HUD 巨大斜带 → 补 view=Mat4()（两个矩阵都要换）；
- 总攻相机扎进狼群（狼头占满画面）→ 距离 > 狼群环半径 + 余量；
- 牛群营地/歪脖子树扎进河里 → 按实测河床剖面（z≤61 水下）移至北岸干地；
- `Mat4.perspective_projection` 实参是 (aspect, ...) 不是 (w, h, ...)。

### Verified

- 冒烟测试 **85 项全绿**（新增：群体规模口径/编队确定性/战斗节拍确定性/字幕时间窗/OST 渲染）；
- 跨进程确定性：pipe 路径两次渲染逐帧 md5 相同（DETERMINISM_OK）；
- 渲染基准：25.3 fps@720p（PNG 路径 1.9 fps）；
- 四幕 proof 切片逐帧目检通过（composition/字幕/夜戏可读性）。

## [0.1.0] - 2026-10-15

### Added（P0 · 基建与管线验证）

- **工程骨架**：`pyproject.toml`（依赖 3dworld + allin-engine，MIT）、venv、
  CLI（`python -m niulai {render,assemble,info}`）、`.gitignore`、借鉴记账（docs/REFERENCE.md）。
- **主时间轴**（`niulai/timeline.py`）：固定 30fps、12fps 粗粝量化（floor 确定性）、
  八幕边界表单一事实来源（序幕 0–360s … 片尾 4800–5160s），测试钉住边界连续覆盖全片。
- **角色生成器 v1**（`niulai/cast/`）：
  - `rig.py`：盒体段骨架（复用 world3d `engine.geometry.box` + `MeshData.transform`），
    每面明暗 CPU 烘焙（FACE_SHADE 六档），`part_matrix` 欧拉组合（T@Rz@Ry@Rx）；
  - `calf.py`：牛来幼态——伏地、四肢外劈、低头、尾抽动、后腿间歇蹬踏；
    躯干高度贴地计算（`CALF_BELLY_CLEAR=0.61`，蹄恰着地），姿态包络由测试钉住；
  - `skylark.py`：云玎——60s 确定性航线（(-88,42,55) → (58,5.5,-12)）、
    转弯侧倾、12fps 量化振翅；尺寸按"影片主角雀"放大（粗粝美学下比例失真是特征）。
- **序幕 · 荒漠飞雀**（`niulai/acts/act0_prologue.py`，P0 切片前 60s）：
  确定性值噪声 + fBm 沙丘（ridged）+ 干河谷 + 噪声打糊边缘的幕末绿地；
  追雀机位（0–52s）→ 8s 过渡到"雀+牛"双人镜头（52–60s）；相机防穿地。
- **成片管线**（`niulai/pipeline/render.py`）：visible=False 离屏窗口 +
  glReadPixels 抓帧（复用 world3d `platform.app.capture`）→ PNG 序列 →
  ffmpeg（libx264/yuv420p）→ MP4；manifest 记录每帧 md5。
- **TTS 试水**（docs/TTS试水报告.md）：SAPI Huihui（离线，22.05kHz，机械腔贴合原片）
  + edge-tts YunjianNeural（在线，24kHz，质量对照）双通路实测。

### Verified（实测证据）

- `tests/test_smoke.py`：ALL_SMOKE_TESTS_PASSED（时间轴/量化/站不起来包络/
  航线有界与航向连续/高程确定性/相机不穿地/姿态确定性）。
- `tests/test_determinism.py --frames 3`：DETERMINISM_OK —— 跨进程两次渲染逐帧 md5 相同。
- 序幕 60s 成片：`output/牛来_序幕_荒漠飞雀_60s.mp4`（1280×720 @ 30fps）。

### Known issues

- 渲染吞吐 ~1.5 fps @720p（PNG 编码瓶颈）；全片 154,800 帧需 P1 上 raw pipe 直喂 ffmpeg。
- 绿地边缘仍有轻微圆形残留（噪声调制后改善，未根治）。
- SAPI 仅一个中文语音，多角色同嗓（按设定保留）。
