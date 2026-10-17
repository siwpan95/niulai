# -*- coding: utf-8 -*-
"""TTS 配音：SAPI Huihui 离线合成（零新增依赖：pywin32 已在 venv）。

设计口径（P0 既定）：
- 本机 SAPI 只有一个中文语音（Huihui，女声）——**全片"同嗓"作为设定**
  （原片本身就是少对白寓言；旁白感一致）；
- 每句台词合成独立 WAV，按 LINES 的 t0 精确落位到对白轨；
- 对白轨（44.1k mono）与 OST 在 numpy 里逐样本相加 → 最终音轨；
- 离线确定性：同机同版 SAPI 同文本输出相同（一次性母带，不追求跨机复现）。
"""
import math
import os
import subprocess
import wave

import numpy as np

try:
    import win32com.client
    HAS_SAPI = True
except ImportError:      # pragma: no cover
    HAS_SAPI = False

VOICE = 'Huihui'
SR = 44100


def _spvoice():
    import pythoncom
    pythoncom.CoInitialize()
    return win32com.client.Dispatch('SAPI.SpVoice')


def synth_line(text, out_wav):
    """合成一句 -> WAV（SAPI 原生采样率）。返回 (path, 采样率, 时长秒)。"""
    if not HAS_SAPI:
        raise RuntimeError('pywin32 缺失，无法用 SAPI 合成')
    voice = _spvoice()
    for v in voice.GetVoices():
        if VOICE.lower() in v.GetDescription().lower():
            voice.Voice = v
            break
    fstream = win32com.client.Dispatch('SAPI.SpFileStream')
    fstream.Format.Type = 22          # SAFT22kHz16BitMono（必须先设再 Open）
    fstream.Open(out_wav, 3)          # SSFMCreateForWrite
    voice.AudioOutputStream = fstream
    try:
        voice.Speak(text)
    finally:
        fstream.Close()
        try:
            voice.AudioOutputStream = None
        except Exception:
            pass
    with wave.open(out_wav, 'rb') as w:
        dur = w.getnframes() / float(w.getframerate())
        return out_wav, w.getframerate(), dur


def build_dialogue_track(lines, duration, out_wav, sr=SR, tmpdir=None):
    """LINES [(t0, t1, speaker, text)] -> 对白轨 WAV（44.1k mono float32 落位）。

    speaker 前缀念出（"牛妈妈："），无声段落补静音；超出 t1 的语音
    保留完整（不截断台词）。
    """
    import tempfile
    if tmpdir:
        os.makedirs(tmpdir, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=tmpdir or None)
    buf = np.zeros(int(duration * sr), dtype=np.float32)
    n = 0
    for t0, t1, speaker, text in lines:
        text_full = f'{speaker}，{text}' if speaker else text
        seg = os.path.join(tmp, f'line{n:02d}.wav')
        try:
            synth_line(text_full, seg)
            with wave.open(seg, 'rb') as w:
                fs = w.getframerate()
                raw = np.frombuffer(w.readframes(w.getnframes()),
                                    dtype=np.int16).astype(np.float32) / 32768.0
            if fs != sr:
                xs = np.arange(len(raw)) / float(fs)
                xs2 = np.arange(int(len(raw) * sr / fs)) / float(sr)
                raw = np.interp(xs2, xs, raw)
            start = int(t0 * sr)
            end = min(len(buf), start + len(raw))
            if start < len(buf):
                buf[start:end] += raw[:end - start]
            n += 1
        except Exception as e:       # 单句失败不阻断整轨（记录并继续）
            print(f'  [tts warn] line {n} ({speaker}) failed: {e}')
    # 对白归一化：SAPI 输出峰值 94% 满幅，压到 0.6（-4.4dBFS）
    peak = np.abs(buf).max()
    if peak > 1e-6:
        buf = buf * (0.6 / peak)
    pcm = (np.clip(buf, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(out_wav, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return out_wav, n


def mix_tracks(ost_path, dialogue_path, out_wav, dialogue_gain=1.0):
    """OST + 对白逐样本相加（对齐到较长者，采样率统一 44.1k）。"""
    def load(p):
        with wave.open(p, 'rb') as w:
            fs = w.getframerate()
            n = w.getnframes()
            data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(
                np.float32) / 32768.0
        if fs != SR:
            xs = np.arange(len(data)) / float(fs)
            xs2 = np.arange(int(len(data) * SR / fs)) / float(SR)
            data = np.interp(xs2, xs, data)
        return data
    a = load(ost_path)
    b = load(dialogue_path) * dialogue_gain
    length = max(len(a), len(b))
    mix = np.zeros(length, dtype=np.float32)
    mix[:len(a)] += a
    mix[:len(b)] += b
    # 母带总闸：超 0.95 峰值整体压回（不削波、保比例）
    peak = float(np.abs(mix).max())
    if peak > 0.95:
        mix = mix * (0.95 / peak)
    pcm = (np.clip(mix, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(out_wav, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return out_wav


def remux(video, audio, out_mp4, ffmpeg='ffmpeg'):
    """视频流原样 + 新音轨重封（不重编码视频）。"""
    p = subprocess.run([ffmpeg, '-y', '-i', video, '-i', audio,
                        '-map', '0:v', '-map', '1:a',
                        '-c:v', 'copy', '-c:a', 'aac', '-shortest', out_mp4],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-1200:])
    return out_mp4


def silence_track(duration, out_wav, sr=SR):
    """纯静音轨（act0/act1 流一致性用；也可直接 amix）。"""
    pcm = np.zeros(int(duration * sr), dtype=np.int16)
    with wave.open(out_wav, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return out_wav


if __name__ == '__main__':
    import sys
    path, sr0, dur = synth_line('我的孩子，你来了，欢迎你，牛来。',
                                'output/ost/_probe.wav')
    print(f'synth ok: {path} sr={sr0} dur={dur:.2f}s '
          f'size={os.path.getsize(path)}')
