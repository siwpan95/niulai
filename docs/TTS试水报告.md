# TTS 试水报告（P0 · 2026-10-15）

> 口径决策：配音 TTS 试水（全哥 2026-10-15 定）。本文记录两条通路的实测结果与选型建议。
> 样本句（牛妈妈第一句）："我的孩子，你来了，欢迎你，牛来。"

## 通路 A：Windows SAPI5（离线）

- 实现：`pyttsx3`（venv 可选依赖），本机语音库实测 2 个：
  - **Microsoft Huihui Desktop - Chinese (Simplified)**（zh-CN，女声）← 唯一中文
  - Microsoft Zira Desktop - English (United States)
- 产物：`output/tts_huihui_line1.wav` —— 22.05 kHz / mono / 5.23 s / 225 KB
- 特征：机械译制腔、字头硬、无情感起伏。**与原片"业余配音"质感意外契合**
  （原片配音正是导演母亲的非专业演绎，观众笑点部分来自台词口音）。
- 局限：只有一个中文语音，全部角色同嗓；rate 130 已偏慢仍显赶。

## 通路 B：edge-tts（在线神经语音）

- 实现：`edge-tts`（venv 可选装，走 Microsoft 在线服务，需网络）
- 产物：`output/tts_edge_yunjian_line1.mp3` —— 24 kHz / mono / 4.37 s / 26 KB
  （`zh-CN-YunjianNeural`，男声；另有 Xiaoxiao/Xiaoyi 等中文神经语音可换）
- 特征：自然流畅、吐字清晰。质量远超 SAPI，但**太"好"了**——与原片的
  "手搓感"路线相悖。

## 选型建议

| 用途 | 建议 | 理由 |
|------|------|------|
| 正片配音（默认） | **SAPI Huihui** | 机械感 = 原片特质；离线零依赖；全部角色同嗓反而强化"母子二人包干"的设定真实感 |
| 片尾曲《雨后清风有香》旁白/特殊角色 | edge-tts 备用 | 需要"质量对照"时（如牛爸爸说教段）可局部换嗓，形成粗粝/精致的反差 |
| 混音 | 都需压响度 + 加混响（P1 音频管线） | SAPI 输出干、直白；原片音画不同步是特征，但我们至少要做到音画对齐后可选择性地"做旧" |

## 复现命令

```bat
:: A. SAPI（离线）
.venv\Scripts\python.exe -c "import pyttsx3; e=pyttsx3.init(); e.setProperty('voice', [v.id for v in e.getProperty('voices') if 'ZH-CN' in v.id][0]); e.setProperty('rate', 130); e.save_to_file('我的孩子，你来了，欢迎你，牛来。', 'output/tts_huihui_line1.wav'); e.runAndWait()"
:: B. edge-tts（在线）
.venv\Scripts\python.exe -m edge_tts --voice zh-CN-YunjianNeural --text "我的孩子，你来了，欢迎你，牛来。" --write-media output/tts_edge_line1.mp3
```
