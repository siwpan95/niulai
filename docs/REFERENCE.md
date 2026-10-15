# 借鉴记账（REFERENCE）

> 全哥铁律 4：借鉴必记账（来源 + 许可证 + 范围）。本工程引用的全部外部实现如下。
> siwpan 自研件注明来源仓库；无任何第三方代码入仓。

## 一、以依赖方式引入（PyPI，随 pyproject.toml 声明）

| 组件 | 版本 | 许可证 | 用途 |
|------|------|--------|------|
| 3dworld（导入名 world3d） | >=0.1.0 | MIT（siwpan 自研，gitee.com/siwpan/3dworld） | 渲染/演出层：`engine.geometry`（MeshData/box）、`logic.camera`（look_at_matrix）、`platform.app`（capture 抓帧） |
| allin-engine（导入名 allin_engine） | >=1.0.0 | MIT（siwpan 自研，gitee.com/siwpan/an-engine） | 逻辑/智能层：`core.event_bus`（EventBus，P0 桥接层）；P1 起接入 ECS / ai.decision / systems.combat / world / audio |

## 二、手法/算法借鉴（代码未整体复制，重写于 niulai/，注明来源）

| niulai 位置 | 借鉴来源 | 许可证 | 范围 |
|-------------|----------|--------|------|
| `niulai/scenery/desert.py`（`_hash01`/`_value_noise`/`_fbm`/顶点色烘焙 + 雾着色器） | 3dworld `examples/terrain_flyover.py` | MIT（siwpan 自研） | 确定性整数哈希值噪声 + fBm 高度场手法；"雾色 == 清屏色"坑位；每面明暗烘顶点色手法 |
| `niulai/pipeline/render.py`（`OffscreenRenderer`/离屏抓帧） | 3dworld `world3d/platform/app.py`（capture）+ `presentation/kkrieger_app.py`（跳帧截图 + 音画同步） | MIT（siwpan 自研） | glReadPixels 抓帧存 PNG 的手法；窗口/投影/WindowBlock 约定 |
| `niulai/cast/calf.py`、`skylark.py`（12fps 量化、僵硬步态） | 原片《牛来》美学特征（非代码） | —— | 观影调研结论，见 docs/分幕脚本.md |

## 三、工具链（不入仓、不随包分发）

| 工具 | 位置 | 用途 |
|------|------|------|
| FFmpeg 9.0.2 | `E:\ffmpeg\bin\ffmpeg.exe`（gyan.dev build） | PNG 序列 -> MP4 拼装（`niulai assemble`，路径经 `--ffmpeg`/`NIULAI_FFMPEG` 注入） |
| pyttsx3 / SAPI（Microsoft Huihui zh-CN） | venv 可选装 | TTS 试水（P0 报告见 docs/TTS试水报告.md） |
| edge-tts（zh-CN-YunjianNeural） | venv 可选装，在线 | TTS 质量对照 |

## 四、原片素材

《牛来》正片/台词为原片著作权内容。本工程仅依据公开剧情梗概、台词摘录与影评
做**同人学习性复刻**：不商用、不传播成片、不冒名。台词库仅存于本地 docs/，不入仓。
