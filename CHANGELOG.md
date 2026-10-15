# Changelog

本项目所有值得注意的变更都会记录在此文件中。
格式基于 Keep a Changelog，版本号遵循语义化版本。

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
