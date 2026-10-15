# -*- coding: utf-8 -*-
"""OST 预制：把循环主题裁剪/铺满为**精确时长**的有限音轨，再供成片混音。

为什么不直接在 render_pipe 里 `-stream_loop -1`：那会让 ffmpeg 的音轨时间轴
脱离视频帧狂奔（238 帧视频已跑到 13 分钟输出时间），mux 结果错乱（实测踩坑）。
正确做法：音频预处理成有限文件，混音时两个输入都是有限的。
"""
import os
import subprocess


def prepare_loop(src, seconds, out_path, ffmpeg='ffmpeg'):
    """把 src 循环铺满并裁剪到 seconds，输出有限 WAV（44.1k stereo）。"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    cmd = [ffmpeg, '-y', '-stream_loop', '-1', '-i', src,
           '-t', f'{seconds:.3f}', '-c:a', 'pcm_s16le', out_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.isfile(out_path):
        raise RuntimeError(f'prepare_loop failed:\n{proc.stderr[-1500:]}')
    return out_path


def prepare_act_audio(theme_wav, frames, fps=30, out_dir='output/ost',
                      ffmpeg='ffmpeg'):
    """按幕帧数预制音轨：output/ost/loop_<theme>_<frames>.wav。"""
    seconds = frames / float(fps)
    name = os.path.splitext(os.path.basename(theme_wav))[0]
    out = os.path.join(out_dir, f'loop_{name}_{frames}f.wav')
    return prepare_loop(theme_wav, seconds, out, ffmpeg=ffmpeg)


if __name__ == '__main__':
    import sys
    src, frames = sys.argv[1], int(sys.argv[2])
    print(prepare_act_audio(src, frames))
