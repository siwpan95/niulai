# -*- coding: utf-8 -*-
"""配音测试（P3-1a）：多角色音色映射 + 台词落位窗口 + 语速适配。

全部**离线**：不联网、不需要 ffmpeg、不需要 SAPI —— 落位用注入的假合成器验证，
音色映射与语速计算都是纯函数。

运行：python tests/test_voices.py（或 python -m pytest tests/）
"""
import os
import sys
import tempfile
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from niulai.acts import (act0_prologue, act1_stand, act2_migration,  # noqa: E402
                         act3_leopard, act4_wolves, act5_finale,
                         act6_wake, act7_credits)
from niulai.audio import tts  # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    status = 'ok' if cond else 'FAIL'
    print(f'  {status}: {name}' + (f'  [{detail}]' if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def all_lines(include_credits=False):
    """全片台词 (幕名, t0, t1, speaker, text)，单一事实来源就是各幕的 LINES。

    act0 序幕自 2026-10-18 内容扩充后也有入梦问答（4 句，云玎开口）；
    act7 是**片尾字幕卡**：speaker 全空、只上字幕不配音——`scripts/voice_mix.py`
    的 ACTS 也只含 act0-act6。故默认排除，避免"字幕卡也被念出来"。
    """
    mods = [act0_prologue, act1_stand, act2_migration, act3_leopard,
            act4_wolves, act5_finale, act6_wake, act7_credits]
    out = []
    for m in mods:
        name = m.__name__.split('.')[-1]
        if name == 'act7_credits' and not include_credits:
            continue
        for line in getattr(m, 'LINES', ()):
            out.append((name,) + tuple(line))
    return out


def all_speakers():
    """全片出现过的角色名集合（all_lines 的第 4 列）。"""
    return {ln[3] for ln in all_lines()}


# ---------------------------------------------------------------- 音色映射


def test_credits_not_dubbed():
    print('test_credits_not_dubbed')
    credit = [ln for ln in all_lines(include_credits=True)
              if ln[0] == 'act7_credits']
    check('片尾存在字幕卡', len(credit) > 0)
    check('字幕卡无说话人（不进配音）',
          {ln[3] for ln in credit} == {''},
          f'{sorted({ln[3] for ln in credit})}')


def test_voice_coverage():
    print('test_voice_coverage')
    speakers = all_speakers()
    check('全片有台词角色', len(speakers) > 0, f'{speakers}')
    for name in sorted(speakers):
        check(f'{name} 有专属音色', name in tts.VOICE_MAP,
              f'missing: {name}')
    # 反向：映射表里不应有全片用不到的幽灵角色
    unused = set(tts.VOICE_MAP) - speakers
    check('映射表无幽灵角色', not unused, f'unused: {unused}')


def test_voice_uniqueness():
    print('test_voice_uniqueness')
    voices = [tts.voice_for(n) for n in tts.VOICE_MAP]
    check('各角色音色互不相同', len(set(voices)) == len(voices),
          f'{dict(zip(tts.VOICE_MAP, voices))}')
    check('牛妈妈 != 牛来',
          tts.voice_for('牛妈妈') != tts.voice_for('牛来'))
    check('牛爸爸 != 牛来',
          tts.voice_for('牛爸爸') != tts.voice_for('牛来'))
    check('所有音色都是 zh-CN',
          all(v.startswith('zh-CN') for v in voices))


def test_adult_override():
    print('test_adult_override')
    check('act5 牛来换成年嗓',
          tts.voice_for('牛来', 'act5') == tts.VOICE_ADULT['牛来'])
    check('act6 牛来换成年嗓',
          tts.voice_for('牛来', 'act6') == tts.VOICE_ADULT['牛来'])
    check('act1 牛来保持幼年嗓',
          tts.voice_for('牛来', 'act1') == tts.VOICE_MAP['牛来'])
    check('act5 豹拉换成年嗓',
          tts.voice_for('豹拉', 'act5') == tts.VOICE_ADULT['豹拉'])
    check('act3 豹拉保持幼崽嗓',
          tts.voice_for('豹拉', 'act3') == tts.VOICE_MAP['豹拉'])
    check('act=None 不触发成年化', not tts.is_adult_act(None))
    check('未知角色回落默认音色',
          tts.voice_for('路人甲') == tts.DEFAULT_VOICE)
    # 成年嗓不能和幼年嗓撞车，否则等于没换
    check('成年嗓 != 幼年嗓',
          tts.VOICE_ADULT['牛来'] != tts.VOICE_MAP['牛来'])


# ---------------------------------------------------------------- 语速适配


def test_fit_rate():
    print('test_fit_rate')
    check('窗内无需调速', tts.fit_rate(3.0, 6.0) == (0, True))
    check('刚好等于窗口不需调速', tts.fit_rate(6.0, 6.0) == (0, True))
    check('超窗按比例加速', tts.fit_rate(6.0, 5.0) == (20, True))
    check('超上限钳制 + 告警', tts.fit_rate(20.0, 5.0) == (tts.RATE_MAX_PCT, False))
    check('非法窗口不崩', tts.fit_rate(1.0, 0) == (0, True))
    check('零时长不崩', tts.fit_rate(0.0, 5.0) == (0, True))
    check('rate 字符串格式', tts.rate_str(15) == '+15%')
    check('负 rate 字符串格式', tts.rate_str(-10) == '-10%')


# ---------------------------------------------------------------- 落位（离线）


def _fake_synth(dur, sr=22050, amp=0.5):
    """假合成器：产出固定时长的满幅段，用于钉住落位逻辑。"""
    def _f(text, path):
        n = int(dur * sr)
        pcm = np.full(n, int(amp * 32767), dtype=np.int16)
        with wave.open(path, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm.tobytes())
        return path, sr, dur
    return _f


def _read_wav(path):
    with wave.open(path, 'rb') as w:
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return sr, data


def test_placement():
    print('test_placement')
    dur, seg = 60.0, 2.0
    lines = ((5.0, 9.0, '牛妈妈', '第一句'),
             (20.0, 24.0, '牛来', '第二句'),
             (40.0, 44.0, '牛爸爸', '第三句'))
    tmp = tempfile.mkdtemp(prefix='niulai_voices_')
    out = os.path.join(tmp, 'diag.wav')
    _, n = tts.build_dialogue_track(lines, dur, out, tmpdir=tmp,
                                    synth=_fake_synth(seg))
    check('合成句数 == 台词句数', n == len(lines), f'{n} != {len(lines)}')
    sr, data = _read_wav(out)
    check('对白轨长度 == 幕时长', len(data) == int(dur * sr),
          f'{len(data)} vs {int(dur * sr)}')
    check('对白轨采样率 44.1k', sr == tts.SR)
    for t0, t1, sp, _ in lines:
        a, b = int(t0 * sr), int((t0 + seg) * sr)
        check(f'{sp} 语音落在 t0', np.abs(data[a:b]).max() > 0)
        # 段后到窗口结束必须干净（2s 段落进 4s 窗口）
        check(f'{sp} 不溢出 t1',
              np.abs(data[int((t0 + seg) * sr):int(t1 * sr)]).max() == 0)
    check('句间静音（第 1、2 句之间）',
          np.abs(data[int(10 * sr):int(19 * sr)]).max() == 0)
    check('句间静音（第 2、3 句之间）',
          np.abs(data[int(25 * sr):int(39 * sr)]).max() == 0)
    check('首句之前静音', np.abs(data[:int(5 * sr)]).max() == 0)
    check('末句之后静音', np.abs(data[int(46 * sr):]).max() == 0)


def test_placement_engine_default():
    print('test_placement_engine_default')
    import inspect
    sig = inspect.signature(tts.build_dialogue_track)
    check('默认 engine 保持 sapi（同嗓设定不被静默替换）',
          sig.parameters['engine'].default == 'sapi')
    # 注入 synth 时 engine 不参与，落位行为一致
    tmp = tempfile.mkdtemp(prefix='niulai_voices_')
    out = os.path.join(tmp, 'diag2.wav')
    lines = ((1.0, 3.0, '牛妈妈', 'x'),)
    _, n = tts.build_dialogue_track(lines, 10.0, out, tmpdir=tmp,
                                    synth=_fake_synth(1.0))
    check('注入合成器下句数正确', n == 1)


def main():
    test_credits_not_dubbed()
    test_voice_coverage()
    test_voice_uniqueness()
    test_adult_override()
    test_fit_rate()
    test_placement()
    test_placement_engine_default()
    if FAILED:
        print(f'\nFAILED {len(FAILED)}: {FAILED}')
        return 1
    print('\nALL_VOICE_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
