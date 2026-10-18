# -*- coding: utf-8 -*-
"""TTS 配音：双引擎 —— SAPI Huihui（离线同嗓）/ edge-tts（多角色音色）。

设计口径（P0 既定，P3 扩展）：
- **sapi**（默认）：本机 SAPI 只有一个中文语音（Huihui，女声）——全片"同嗓"
  作为设定（原片本身就是少对白寓言；旁白感一致）。离线确定性：同机同版 SAPI
  同文本输出相同（一次性母带，不追求跨机复现）。
- **edge**（P3-1a，opt-in）：角色 -> 音色映射，一人一嗓。需联网 + ffmpeg
  （edge-tts 只出 mp3，转 wav 走 ffmpeg）。**默认关闭**——多角色是可选增强，
  不是替换原设定的默认值；合成失败逐句回退 sapi 并告警，不阻断整轨。
- 每句台词合成独立 WAV，按 LINES 的 t0 精确落位到对白轨；
- 对白轨（44.1k mono）与 OST 在 numpy 里逐样本相加 → 最终音轨。

时长是硬约束：每句必须落在 [t0, t1) 窗口内。edge-tts 支持合成时指定语速
（`rate`），故超窗时用**重合成加速**而非后处理变速——不做 WSOLA/变调，
保住自然度。
"""
import asyncio
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

try:
    import edge_tts
    HAS_EDGE = True
except ImportError:      # pragma: no cover
    HAS_EDGE = False

VOICE = 'Huihui'
SR = 44100

# ---- 多角色音色映射（P3-1a）----
# edge-tts 的 zh-CN 音色（2026-10 实测可用 8 个，此处选性格贴合的 4 个）：
#   Xiaoxiao 女/Warm · Yunxi 男/Lively,Sunshine · Yunyang 男/Professional,Reliable
#   Yunxia 男/Cute · Yunjian 男/Passion
VOICE_MAP = {
    '牛妈妈': 'zh-CN-XiaoxiaoNeural',     # 温暖女声 —— 母亲
    '牛来': 'zh-CN-YunxiNeural',          # 少年感（幼犊 / 少年期）
    '牛爸爸': 'zh-CN-YunyangNeural',      # 沉稳可靠 —— 父辈
    '豹拉': 'zh-CN-YunxiaNeural',         # 幼崽（act3 初遇）
    '云玎': 'zh-CN-XiaoyiNeural',         # 云雀（梦境旁观者，轻亮女声）
}
# 成年期覆盖：act5 传承决战 / act6 梦醒而立 里牛来、豹拉都已长大
VOICE_ADULT = {
    '牛来': 'zh-CN-YunyangNeural',
    '豹拉': 'zh-CN-YunjianNeural',
}
ADULT_ACTS = frozenset({'act5', 'act6', 'act5_finale', 'act6_wake'})
DEFAULT_VOICE = 'zh-CN-XiaoxiaoNeural'

# 语速调整边界（%）：超出即不再强压，避免机械腔 —— 改为告警
RATE_MAX_PCT = 30
RATE_MIN_PCT = -20


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


# ---------------------------------------------------------------- 多角色（edge）


def is_adult_act(act):
    """幕名是否属于成年期（act5 传承决战 / act6 梦醒而立）。"""
    if not act:
        return False
    name = str(act)
    return name in ADULT_ACTS or ('act5' in name or 'act6' in name)


def voice_for(speaker, act=None):
    """角色 + 幕 -> edge-tts 音色（纯函数，供测试直接钉住）。"""
    if is_adult_act(act) and speaker in VOICE_ADULT:
        return VOICE_ADULT[speaker]
    return VOICE_MAP.get(speaker, DEFAULT_VOICE)


def fit_rate(dur, window):
    """把 dur 压进 window 所需语速百分数（纯函数）。

    返回 (rate_pct, ok)：rate_pct=0 表示无需调整；ok=False 表示需要的加速
    超过 RATE_MAX_PCT，**调用方应告警并钳制**，而不是硬压出机械腔。
    """
    if window is None or window <= 0 or dur <= 0:
        return 0, True
    if dur <= window:
        return 0, True
    need = int(math.ceil((dur / window - 1.0) * 100))
    if need > RATE_MAX_PCT:
        return RATE_MAX_PCT, False
    return need, True


def rate_str(pct):
    """百分数 -> edge-tts rate 字符串（'+15%' / '-10%'）。"""
    return f'{int(pct):+d}%'


async def _edge_save(text, voice, rate, out_mp3):
    comm = edge_tts.Communicate(text, voice, rate=rate)
    await comm.save(out_mp3)


def _mp3_to_wav(mp3, wav_path, ffmpeg='ffmpeg', sr=SR):
    """edge-tts 只出 mp3，转 wav 走 ffmpeg（项目硬依赖，装配本来就要它）。"""
    cmd = [ffmpeg, '-y', '-i', mp3, '-ar', str(sr), '-ac', '1', wav_path]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f'mp3->wav failed: {(p.stderr or "")[-300:]}')
    return wav_path


def synth_line_edge(text, out_wav, voice=DEFAULT_VOICE, rate='+0%',
                    ffmpeg='ffmpeg'):
    """edge-tts 合成一句 -> WAV。返回 (path, 采样率, 时长秒)。"""
    if not HAS_EDGE:
        raise RuntimeError('edge-tts missing (pip install edge-tts)')
    tmp_mp3 = os.path.splitext(out_wav)[0] + '.mp3'
    asyncio.run(_edge_save(text, voice, rate, tmp_mp3))
    _mp3_to_wav(tmp_mp3, out_wav, ffmpeg=ffmpeg)
    with wave.open(out_wav, 'rb') as w:
        dur = w.getnframes() / float(w.getframerate())
        return out_wav, w.getframerate(), dur


def _mix_into(buf, seg_wav, t0, sr):
    """读一句 WAV 按 t0 加进对白缓冲（必要时重采样到 sr）。返回写入样本数。"""
    with wave.open(seg_wav, 'rb') as w:
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
    return max(0, end - start)


def build_dialogue_track(lines, duration, out_wav, sr=SR, tmpdir=None,
                         engine='sapi', act=None, ffmpeg=None, synth=None):
    """LINES [(t0, t1, speaker, text)] -> 对白轨 WAV（44.1k mono float32 落位）。

    speaker 前缀念出（"牛妈妈："），无声段落补静音；超出 t1 的语音
    保留完整（不截断台词）。

    engine: 'sapi'（默认，全片同嗓）/ 'edge'（P3-1a 多角色音色，需联网+ffmpeg）。
    act:    幕名，仅 edge 下用于成年期音色覆盖（act5/act6）。
    synth:  注入合成器 f(text, path) -> (path, sr, dur)，供测试离线验证落位。
    """
    import tempfile
    if tmpdir:
        os.makedirs(tmpdir, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=tmpdir or None)
    buf = np.zeros(int(duration * sr), dtype=np.float32)
    ff = ffmpeg or os.environ.get('NIULAI_FFMPEG', 'ffmpeg')
    n = 0
    for t0, t1, speaker, text in lines:
        text_full = f'{speaker}，{text}' if speaker else text
        seg = os.path.join(tmp, f'line{n:02d}.wav')
        try:
            if synth is not None:
                synth(text_full, seg)
            elif engine == 'edge':
                voice = voice_for(speaker, act)
                _, _, dur = synth_line_edge(text_full, seg, voice=voice,
                                            ffmpeg=ff)
                # 超窗 -> 按所需语速**重合成**（不变调、不做后处理变速）
                rate, ok = fit_rate(dur, t1 - t0)
                if rate != 0:
                    if not ok:
                        print(f'  [tts warn] line {n} ({speaker}) needs '
                              f'>{RATE_MAX_PCT}% speedup, clamped')
                    synth_line_edge(text_full, seg, voice=voice,
                                    rate=rate_str(rate), ffmpeg=ff)
            else:
                synth_line(text_full, seg)
            _mix_into(buf, seg, t0, sr)
            n += 1
        except Exception as e:
            # 单句失败不阻断整轨。edge 依赖网络 + ffmpeg，失败回退离线 sapi：
            # 有网更好，没网也照样能出片。
            if engine == 'edge' and HAS_SAPI:
                try:
                    synth_line(text_full, seg)
                    _mix_into(buf, seg, t0, sr)
                    n += 1
                    continue
                except Exception as e2:
                    print(f'  [tts warn] line {n} ({speaker}) edge failed '
                          f'({e}); sapi fallback failed ({e2})')
            else:
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
    import argparse

    ap = argparse.ArgumentParser(description='synth one line (probe)')
    ap.add_argument('--engine', default='sapi', choices=['sapi', 'edge'])
    ap.add_argument('--voice', default=DEFAULT_VOICE,
                    help='edge-tts voice short name')
    ap.add_argument('--text', default='我的孩子，你来了，欢迎你，牛来。')
    ap.add_argument('--out', default='output/ost/_probe.wav')
    ap.add_argument('--ffmpeg', default=os.environ.get('NIULAI_FFMPEG',
                                                       'ffmpeg'))
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    if a.engine == 'edge':
        path, sr0, dur = synth_line_edge(a.text, a.out, voice=a.voice,
                                         ffmpeg=a.ffmpeg)
        print(f'synth ok [edge/{a.voice}]: {path} sr={sr0} dur={dur:.2f}s '
              f'size={os.path.getsize(path)}')
    else:
        path, sr0, dur = synth_line(a.text, a.out)
        print(f'synth ok [sapi/{VOICE}]: {path} sr={sr0} dur={dur:.2f}s '
              f'size={os.path.getsize(path)}')
