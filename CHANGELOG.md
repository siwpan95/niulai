# Changelog

本项目所有值得注意的变更都会记录在此文件中。
格式基于 Keep a Changelog，版本号遵循语义化版本。

## [0.6.0] - 2026-10-18

### Added（P5 · 双引擎能力全量拉满 —— 全哥拍板「P5 必须全做」）

- **world3d 贴图/材质子系统（审计 0% 面 → 全用）**：`pipeline/pbr_bridge.py`
  + `--profile pbr` —— world3d `Renderer` 端到端（MRT -> 程序化天空 ->
  阴影化 PBR -> SSAO -> Bloom -> 曝光/ACES/暗角合成）；
  `proctex` 程序化贴图（dune/plaster/brushed/wood_planks/dragon_scale/snow
  + 自拼水面 fBm）；`material` 金属-粗糙度（河面 BLEND 走渲染器半透明）；
  `env.LightEnvironment` 每幕太阳/天色 IBL 烘焙 + act4 营火点光；
  `texproj` 平面/triplanar UV；`scene`/`mesh`/`InstancedMesh`（pbr_inst
  替换自研群体实例化）；rig 网格命名 `kind:part`（材质映射键）。
- **深度效果全链（`pipeline/pbr_frame.py`，帧图驱动）**：
  `framegraph.standard_3d_plan` 编译 + 按计划派发；CSM 3 级阴影
  （阴影化 PBR 变体 = PBR_FRAG 注入 csm_glsl）；`volumetrics` 高度雾+
  单次散射（阴影复用 CSM）；`dof` 薄透镜景深；`motionblur` 相机重投影；
  SSAO；线性距离图（R32F）三效果共用。
- **allin ECS+BT 闭环**：`brains/btree.py::BrainRig` —— 行为树正式挂
  `BrainComponent`+`BlackboardComponent`（黑板=单一事实来源）；
  act4 狼群/act2 牛群全部走实体脑，语义与纯函数一致（测试钉住）。
- **能力 proof 组**（`tests/test_p5_proofs.py`）：pointcloud+EDL 渲染
  （跨次逐字节一致）、`physics` 跃溪弧线（确定性抛物线）、`media.ca`
  规则演化确定性、程序化 GLB 解析。
- **覆盖实测更新**（`docs/引擎能力审计_2026-10-18.md`）：
  world3d 8/42≈19% -> **24/42≈57%**（贴图 0% → 全用）；allin ≈22% -> ≈25%。
  未用项全部记账（不适用/规模阈值/与 allin 二选一）。

### Fixed（P5 实测踩坑，全注释在代码）

- post.composite() 首行 bind_screen 强绑 FB0——复刻 uniform 体进中间目标；
- 子 pass bind/unbind 把当前 FBO 还原成 0——tonemap 最后绑目标；
- csm_glsl 自带 uniform 声明（宿主重复声明 = GLSL C1038）；
- u_csm_split 标量数组整体赋值；纹理单元冲突（CSM 图放 10-12）；
- world3d FullscreenQuad vec3 布局 vs 自管线 vec2（自建 quad）；
- WindowBlock 必须从本管线 window 设置（world3d Renderer 无 .window，
  hasattr 探测永远 None —— 几何画飞只剩天空）；
- 渲染脚本透传 --profile（pbr 全片重渲用）。

### Fixed（P5 全片重渲暴露的两类坑）

- **`--resume` 不认 profile**：残块检查只看文件是否存在，导致 `--profile pbr`
  的整片重渲被 raw 既有块全部跳过（一帧 PBR 都没渲，等于拿旧块重新升采）。
  `render_all.py` 改为 **profile 产物目录隔离**（`output/full_pbr/`、
  `output/final_pbr/`），resume 只在各自目录内生效。
- **体积雾地平线黑带**：`u_fog_shafts=0` 时散射只剩深蓝环境项，远处透射率
  趋 0 → 地平线一条黑带（act0/act2 proof 目检抓回）。改为开单次散射、
  环境项取该幕天空地平线色、密度 0.012→0.0055；同时给六幕补
  `ibl_intensity`（原先只有 act2/act4 设了，其余按默认 1.0 → 地形过曝发白）。

### Verified

- 测试 **12 个模块全绿**（profile 含 pbr 跨进程逐帧一致 + 与 raw 3/3 差异；
  新增 test_p5_proofs 四项 proof 全过）；
- pbr 全片重渲（1080p，帧图全链）后台进行，产物口径不变（不入仓不上 Release）。

## [0.5.0] - 2026-10-18

### Added（P4 · 内容填充 + 双引擎全量增强 + 本机全片重制）

- **内容填充（联网调研驱动）**：
  - `docs/原片素材调研.md`：九源调研记账（维基语录为台词单一事实来源），
    台词台账（17 条 S1 全量采用裁定）+ 二创梗甄别 + 编辑裁定（E1-E5）；
  - 台词库 **36 -> 46 句**：act0 序幕新增入梦问答 4 句（云玎首次开口，
    "我们不一样，是吗？"）、act2 跳溪前后 +2、act3 初遇"我是豹啦"、
    act4 妈妈嘱托补全 wikiquote 原文、act5 牛爸爸"盘中餐"训诫 + 豹拉嘱托
    仿写句（调研 E3）、act1/act7 各 +1；九张片尾卡；
  - `docs/分幕脚本.md`：新增各幕节拍表（多源大纲交叉核定）+ 全量台词审计镜像；
  - `audio/tts.py`：VOICE_MAP 新增云玎（zh-CN-XiaoyiNeural）；
    `voice_mix.py` 新增 act0 配音（入梦问答）。
- **allin-engine 全量增强（逻辑/智能层）**：
  - `brains/btree.py`：**行为树决策**（allin `ai.decision.behavior_tree` 声明式
    spec）——狼群五态势（circle/stalk/charge/bite/chase）由妈妈体力曲线/
    总攻窗/狼群距离等**世界状态**驱动（替换硬编时间阈值）；act2 牛群蛇逼
    惊呆反应（<9u 立定）；stance 是 (t, 世界状态) 纯函数，确定性不破坏；
  - `fx/particles.py` + `fx/layer.py`：**粒子场接入**（allin `fx.particle_np`）
    ——act2 三 z 平面风沙带（跟牛群 x 漂移）+ 跃溪飞沫（窗 415-478s）+
    act4 夜风寒尘；固定步长推进 + 种子注入确定性（引擎 `_rng` 无 seed 参数，
    注入记账见 REFERENCE）；GPU 点精灵渲染（雾/色调公式与主体逐字一致）；
  - `brains/navigation.py`：**迁徙 A\* 领队路径**（allin `world.pathfinding`
    grid_astar）——栅格化地形（可走 = h > WATER_Y）+ 终点吸附南岸干地 +
    LOS 拉直，陆地段（progress<0.80）由引擎规划，入水段保留手搓编排，
    衔接逐分量连续（tests/test_navigation.py 钉住）；
  - 评估后不接入：`ai.narrative` / `ai.dialogue`（分支叙事引擎，线性复刻片
    无分支需求——见 docs/增强规划_P4.md §四）。
- **world3d 全量增强（渲染/演出层，默认关闭 profile）**：
  - `pipeline/profile.py`：raw（默认，忠实粗粝）/ **enhanced**（`--profile
    enhanced` 显式开启）——水面 **WBOIT 顺序无关透明**（world3d `engine.oit`，
    深度自 rt_a blit 保证岸/角色遮挡，act2 河面 alpha 0.72）+ **Bloom 后处理**
    （world3d `engine.postfx.PostChain`：软膝盖阈值 + Karis + 金字塔）；
  - 场景协议：`scene.set_profile(profile)` + `scene.water(t)` 钩子；
  - enhanced 与 raw 跨进程逐帧一致（tests/test_profile.py 钉住；WBOIT 不可用
    时自动跳过该步，不静默失败）。
- **本机重制基础设施**：
  - `scripts/render_all.py`：八幕顺序 + 6 并发分块 + resume + 720p lanczos
    升采 1080p（**seed 铁律**：显式传 MASTER_SEED，render_parallel 默认
    seed=0 会静默换地形——实测踩坑）；
  - `scripts/make_audio.py`：音频资产生成一条龙（6 条变奏组曲 + 3 CC0 拟音 +
    6 幕镜头拟音事件轨，49s 全部完成）；
  - `scripts/assemble_film.py`：逐幕 numpy 混音（峰值硬校验 >0.98 报错）+
    mux + 八幕 concat + 总时长验收（5160s ±1）。

### Fixed

- act4 台词时间窗重叠（500-508 与 506-513 相交——冒烟测试只查 act1 未暴露），
  顺带把妈妈嘱托补全为 wikiquote 原文全文；
- 粒子场回退重模拟不一致：发射器 `_accum` / 力场 `_time` 跨重建复用带残余
  状态（实测踩坑），`_build()` 现在显式清零；
- `OffscreenRenderer.__init__` 的 `glClearColor(sky)` 在 profile 重构中一度
  丢失（raw 路径清屏色变黑——proof 目检抓回），已恢复并加注释。

### Verified

- 测试 **11 个模块全绿**：smoke / voices / spots / variations / instancing
  （BT 分组后实例化 vs CPU 仍逐帧 md5 相同）/ parallel / btree / particles /
  navigation / profile / determinism（跨进程 3 帧）；
- **全片重制**：`output/牛来_86分钟_全片_1080p.mp4`（86:00.02 = 5160.02s，
  745MB，1920×1080 30fps h264+aac，八幕混音峰值 0.08–0.51 无削波，
  **全量解码零错误**）；八幕渲染 6 workers 聚合 26.7–30.7 fps（720p 幕）；
- **配音版**：`牛来_86分钟_全片_1080p_配音版.mp4`（46 句 SAPI 同嗓，
  含 act0 入梦问答 4 句，86:00.02，全量解码零错误）；
- enhanced proof：act2 跃溪镜 WBOIT 水面 + Bloom 跨进程逐帧一致，
  且与 raw 逐帧不同（3/3 帧差异——水面确实换了画法）；
- raw proof 目检：act0 入梦字幕（云玎句）、act2 渡口全景、act4 夜袭
  （BT 态势 + 夜尘粒子）、成片 act3 河畔特写；
- **0xC0000409 记账**：Windows 高并发下 CLI 子进程在退出阶段（pyglet GL
  atexit）偶发 fail-fast，块产物已完整——render_parallel 改为
  rc!=0 时先验 block_done()，产物完整计成功（d994b9f）。

## [0.4.0] - 2026-10-17

### Added（三任务：TTS 配音 / GPU 实例化 / 过片细修）

- **TTS 配音**：`audio/tts.py`（SAPI Huihui 离线合成、对白轨 t0 精确落位、
  与 OST 逐样本混合）+ `scripts/voice_mix.py`（六幕 36 句、-c:v copy 重封装）；
  配音版全片 `牛来_86分钟_全片_1080p_配音版.mp4`。
- **GPU 实例化**：`pipeline/instanced.py` InstancedBatch（4×vec4 实例列矩阵）；
  act2/4/7 牛群狼群 crowd(t) 协议；验收：路径内确定性（逐帧 md5）+ 视觉等价
  （MAD≤3.0≈PSNR>40dB）+ 2.0× 吞吐。顺带修复 Rig scale 未进 base 矩阵。
- **过片基础设施**：`scripts/contact_sheet.py`（38 镜头联络图，单文件 HTML）。
- **首轮自审修复**：act2 跃溪镜收紧 4.5 单位（原广角淹没牛来+蛇）；
  act1 双人镜改越肩对立机位、离场镜高机位拉远。
- **配音版 v2 全片**：`牛来_86分钟_全片_1080p_配音版_v2.mp4`
  （act1/act2 重渲 + 重混配音 + 重拼，86:00.02；新旧片同帧 md5 确认修复生效）。

## [0.3.1] - 2026-10-16

### Added / Fixed（全片装配实战）

- `scripts/assemble_final.py`：分块视频拼幕 + 全长 OST 混音 + 八幕 concat。
- 序幕扩展为全幕 6 分钟（航线 360s；测试同步）。
- **帧区间门禁**（CLI）：渲染区间必须落在该幕 [T0×fps, (T0+dur)×fps) 内，
  错位立即报错（P2 全幕帧号错位事故的机械护栏，实测拦截）。
- **分块渲染策略**：ffmpeg 静默死亡（大段 1080p 渲染偶发 BrokenPipe，无崩溃记录、
  内存充足）→ 按 2 分钟分块渲染 + concat，单块失败只损失 10 分钟；
  音轨最后统一混（块间无缝）。
- **act5 缺口修复**：误删 1000 帧缺口块 + 混合流 concat 丢 10.67s →
  纯视频 concat + 统一混 900s OST，重建后 15:00.00 精确。

### Verified（86 分钟全片交付）

- 八幕时长逐段 ffprobe：6/5/12/12/18/15/12/6 = **86:00.02**；
- 七处过缝 md5 帧帧唯一（抽查 4 处 12 帧无重复无跳空）；全量解码无错误；
- 1080p30 全片 h264+aac，735MB。

## [0.3.0] - 2026-10-16

### Added（P2 · 收官三幕 + 1080p 冲刺）

- **act5 传承决战**：逐帧大气系统（`scene.atmosphere(t)` -> sky/fog/tint 关键帧插值；
  白昼 -> 黄昏 -> 夜 -> 黎明）；成年牛来/豹拉；小树林地标；歪脖子树纪念戏；
  豹拉断后（复刻妈妈嘱托，CastState 事件广播）；盗猎人 + 皮卡（轮子绕自身轮心自转）；
  牛来战吼引开盗猎车。
- **act6 梦醒而立（全片眼）**：开幕与 act1 同一构图（import act1 常量 + 同相机函数，
  `test_loop_assertion` 断言机位/角色位置/AABB 复位）；奋力站起
  （`Calf._pose_rise`：躯体组 +0.17u、腿绕髋顶拉伸 k=1+0.37u，**蹄的绝对高度守恒**，
  `test_rise_envelope` 钉住）；云雀高飞；见父亲。
- **act7 片尾**：一家三口 + 8 头牛群 + 云雀金色黄昏；staff 字幕（同人声明 + 原作信息）；
  片尾主题 OST（致敬《雨后清风有香》的程序化民谣，非原曲）。
- **1080p**：act5-7 按 1920x1080 渲染（4.9fps 实测）。
- 新 cast：ADULT_NIULAI_SPEC / FATHER_SPEC / Poacher / PoacherTruck；
  `part_matrix` 增绕枢轴 Y 缩放（sy/pivot_y）；Rig 增整体缩放（scale）。
- 测试扩到 100+ 项（新增循环断言 / rise 包络 / 大气 U 形）。

### Fixed

- `_pose_rise` 双重定位（在 PARTS 烘焙偏移上又叠平移，头被推到 x=1.6）——
  改为部件只做纯 y 增量 + 腿绕髋顶拉伸；
- Poacher/Truck 部件位置翻倍 + 车轮公转变自转 —— 偏移全零、位置全进姿态；
- 云雀高飞镜头鸟飞 +22 单位导致画面只剩天空 —— 降到 +10 并贴近牛群。

## [0.2.2] - 2026-10-16

### Verified（P1 全幕渲染验收通过）

- 四幕全幕渲染（84,600 帧）：act1 5:00（7.6fps）/ act2 12:00（4.5fps，迁徙 OST）/
  act3 12:00（6.6fps，友情 OST）/ act4 18:00（6.3fps，狼袭 OST）；
  逐幕 ffprobe：时长分毫不差、1280x720@30fps、h264+aac 齐全。
- 合片 `output/牛来_P1_四幕_47min.mp4`：47:00.02，三处过缝帧帧唯一
  （md5 比对无重复无跳空），全量解码无错误。
- 全镜头逐帧抽检：17 镜头全覆盖（含成片抽帧复检）。
- 渲染实战修复记录见 0.2.1（时间基/管道死锁/OST 循环）与 2e03d0f
  （蛇飞界外/分奶糊脸/台词时序/夜戏对比度）。

## [0.2.1] - 2026-10-16

### Fixed（全幕渲染实战撞出的三个 bug，均已修 + 回归验证）

- **时间基错位（严重）**：`render_pipe`/`render_range` 把**全片绝对帧号**直接当幕内时间
  传给场景 —— act1-4 的全幕渲染实际渲染的是"最后一镜 + 进度钳位"（act1 的 5 分钟成品
  即错误内容，act2 白跑 5 小时）。现各幕场景声明 `T0`（取自分幕表 ACTS，单一事实来源），
  管线做 `t_local = frame/fps - T0` 换算。
- **ffmpeg 管道死锁（两轮实战）**：stderr 无人读 → 64KB 缓冲灌满 → Python 阻塞写 stdin /
  ffmpeg 阻塞写 stderr，互赌 5 小时零进展。第一修（`for line in` 排空）仍死——
  ffmpeg stats 进度行是 `
` 结尾不是 `
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
