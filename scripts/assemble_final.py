# -*- coding: utf-8 -*-
"""最终装配：分块视频拼幕 + 全长音轨混入 + 八幕 concat 86 分钟全片。

用法（渲染全部完成后）：
    .venv\\Scripts\\python.exe scripts\\assemble_final.py

步骤：
1. act5/6/7 的分块视频（video-only）按序 concat 成整幕视频；
2. 全长音轨 mux（act5=friends 900s / act6=credits 720s / act7=credits 360s）；
3. act0/act1 补静音轨（流一致性）；
4. 八幕 concat -> output/牛来_86分钟_全片_1080p.mp4；
5. ffprobe 验收（时长 86:00 / 1080p30 / h264+aac）。
"""
import os
import subprocess
import sys

FF = os.environ.get('NIULAI_FFMPEG', 'ffmpeg')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'output')
P2 = os.path.join(OUT, 'p2_full')
FINAL = os.path.join(OUT, 'final')
P1 = os.path.join(OUT, 'p1_full')
OST = os.path.join(OUT, 'ost')


def run(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        raise RuntimeError(f'cmd failed: {" ".join(cmd)[:160]}\n{p.stderr[-800:]}')
    return p


def concat_video(parts, out):
    """分块视频 concat（全部 video-only 或同流）。"""
    lst = os.path.join(FINAL, '_clist.txt')
    with open(lst, 'w', encoding='utf-8') as f:
        for pth in parts:
            f.write(f"file '{os.path.relpath(pth, FINAL).replace(os.sep, '/')}'\n")
    run([FF, '-y', '-f', 'concat', '-safe', '0', '-i', lst,
         '-c:v', 'copy', out])
    return out


def mux_audio(video, audio, out):
    run([FF, '-y', '-i', video, '-i', audio,
         '-c:v', 'copy', '-c:a', 'aac', '-shortest', out])
    return out


def add_silent(video, out):
    run([FF, '-y', '-i', video, '-f', 'lavfi',
         '-i', 'anullsrc=r=44100:cl=mono', '-shortest',
         '-c:v', 'copy', '-c:a', 'aac', out])
    return out


def probe(path):
    p = subprocess.run([FF, '-i', path, '-f', 'null', '-'],
                       capture_output=True, text=True)
    for line in p.stderr.splitlines():
        if line.startswith('  Duration') or 'Stream #0' in line:
            print('   ', line.strip()[:90])


def main():
    os.makedirs(FINAL, exist_ok=True)
    print('[1/4] act5: 前半(有音轨) + 尾部分块 -> 整幕')
    act5_parts = [os.path.join(P2, 'act5_finale_95400-108000.mp4'),
                  os.path.join(P2, 'act5_finale_109000-112600.mp4'),
                  os.path.join(P2, 'act5_finale_112600-116200.mp4'),
                  os.path.join(P2, 'act5_finale_116200-119800.mp4'),
                  os.path.join(P2, 'act5_finale_119800-122400.mp4')]
    # 前半含音轨：先剥出纯视频再整体混 900s 全长 OST
    v5 = concat_video([os.path.join(P2, 'act5_finale_95400-108000.mp4')]
                      + act5_parts[1:], os.path.join(FINAL, '_v5.mp4'))
    mux_audio(v5, os.path.join(OST, 'loop_ost_friend_27000f.wav'),
              os.path.join(FINAL, 'act5_1080.mp4'))

    print('[2/4] act6: 六分块 -> 整幕 + credits 720s')
    v6 = concat_video([os.path.join(P2, f'act6_wake_{a}-{b}.mp4')
                       for a, b in ((122400, 126000), (126000, 129600),
                                    (129600, 133200), (133200, 136800),
                                    (136800, 140400), (140400, 144000))],
                      os.path.join(FINAL, '_v6.mp4'))
    mux_audio(v6, os.path.join(OST, 'loop_ost_credits_21600f.wav'),
              os.path.join(FINAL, 'act6_1080.mp4'))

    print('[3/4] act7: 三分块 -> 整幕 + credits 360s')
    v7 = concat_video([os.path.join(P2, f'act7_credits_{a}-{b}.mp4')
                       for a, b in ((144000, 147600), (147600, 151200),
                                    (151200, 154800))],
                      os.path.join(FINAL, '_v7.mp4'))
    mux_audio(v7, os.path.join(OST, 'loop_ost_credits_10800f.wav'),
              os.path.join(FINAL, 'act7_1080.mp4'))

    print('[4/4] 八幕 concat -> 86 分钟全片')
    # P1 四幕用升采 1080p 版本（output/final/*_1080.mp4，lanczos）
    parts = [
        add_silent(os.path.join(P2, 'act0_prologue_0-10800.mp4'),
                   os.path.join(FINAL, 'act0_1080.mp4')),
        add_silent(os.path.join(FINAL, 'act1_stand_10800-19800_1080.mp4'),
                   os.path.join(FINAL, 'act1_1080.mp4')),
        os.path.join(FINAL, 'act2_migration_19800-41400_1080.mp4'),
        os.path.join(FINAL, 'act3_leopard_41400-63000_1080.mp4'),
        os.path.join(FINAL, 'act4_wolves_63000-95400_1080.mp4'),
        os.path.join(FINAL, 'act5_1080.mp4'),
        os.path.join(FINAL, 'act6_1080.mp4'),
        os.path.join(FINAL, 'act7_1080.mp4'),
    ]
    # 分辨率统一：P1 是升采 1080p ✓（act1/2 在 p1_full 已是 1080）
    lst = os.path.join(FINAL, '_flist.txt')
    with open(lst, 'w', encoding='utf-8') as f:
        for pth in parts:
            f.write(f"file '{os.path.relpath(pth, FINAL).replace(os.sep, '/')}'\n")
    film = os.path.join(OUT, '牛来_86分钟_全片_1080p.mp4')
    run([FF, '-y', '-f', 'concat', '-safe', '0', '-i', lst,
         '-c', 'copy', film])
    print()
    print('== FINAL FILM ==')
    probe(film)
    print(f'== size: {os.path.getsize(film) / 1048576:.1f} MB ==')
    return 0


if __name__ == '__main__':
    sys.exit(main())
