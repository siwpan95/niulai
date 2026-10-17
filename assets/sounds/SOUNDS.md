# 公版音源来源与许可（SOUNDS.md）

本片氛围音效使用以下**真实录音**（替换了原先的程序合成噪声）。

| 文件 | 内容 | 时长 | 作者 | 来源 | 许可 |
|------|------|------|------|------|------|
| `birds_cc0_kvgarlic.ogg` | 晨间鸟鸣（实地录音） | 2:10 | kvgarlic | [Freesound #156826](https://freesound.org/people/kvgarlic/sounds/156826/) | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |
| `wind_cc0_felixblume.ogg` | 原野风声（实地录音） | 0:15 | felix.blume | [Freesound #217506](https://freesound.org/people/felix.blume/sounds/217506/) | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |

## 获取与校验

- 经由 [blanket（GPL-3.0）](https://github.com/rafaelmardojai/blanket) 资源库镜像下载
  （该仓库 `SOUNDS_LICENSING.md` 逐文件列明许可）；
- sha256 与 [QuietField 音源目录](https://github.com/Gary06868/QuietField/blob/main/src/catalog.public.json) 校验一致：
  - birds: `e59b19c2a377d5835d07e7ec8f8c876b9f40ae7f703738b55d616ef96a1638b2`
  - wind:  `cfdc81be69cd5f434ebfeb708bdf094725f3052d76691f550ff0e10eee3e32d2`
- 两段均为 **CC0 1.0**（公有领域贡献，可自由使用、无需署名；署名仍保留以示尊重）。

## 处理

- `niulai/audio/foley.py`：ffmpeg 解码为 44.1k 单声道 → 1.5s 交叉淡化无缝循环 →
  确定性包络（序幕风声随降落渐弱 / 鸣唱窗淡入淡出）。
- OST/对白仍为程序化合成（见 `audio/ost.py` / `audio/tts.py`）。

> 注：本片为同人学习性复刻（不商用、不传播成片）；CC0 素材的使用与上述许可一致。
