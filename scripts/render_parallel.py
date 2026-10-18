# -*- coding: utf-8 -*-
"""分块并行渲染（P3-2）：把一幕切成 N 块并发渲，再拼回完整一幕。

为什么分块：P2 实战踩过 ffmpeg 静默死亡（大段 1080p 渲染偶发 BrokenPipe，无崩溃
记录），故按 ~2 分钟切块——单块失败只损失 2 分钟。既然块是天然的独立单元，
就顺手让它**并行**：每块一个独立子进程（各自建 pyglet 离屏窗口、各自过 GL）。

为什么不会破坏确定性：场景姿态是 `t` 的纯函数 + 固定 seed，块间不共享任何状态。
每块独立跑现有 CLI（`python -m niulai render`），帧号不变，故并行结果与串行结果
**逐帧 md5 必须相同**——`tests/test_parallel.py` 用 2 workers vs 1 worker 实测钉住。

用法::

    # 生产（raw pipe，需 ffmpeg）：4 并发渲 act2 全幕
    python scripts/render_parallel.py --act act2_migration --workers 4 ^
        --size 1920x1080 --out output/act2 --concat output/act2_full.mp4

    # 无 ffmpeg 环境（PNG 序列，用于验证/调试）
    python scripts/render_parallel.py --act act0_prologue --start 0 --end 600 ^
        --workers 2 --png --out output/act0_probe

    # 中断后续跑（已完成且 manifest 完整的块直接跳过）
    python scripts/render_parallel.py ... --resume

控制台输出一律 ASCII（Windows GBK 代码页下中文会变问号，污染自动化解析）。
"""
import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_CHUNK_SECONDS = 120.0     # 沿用 P2 实战：2 分钟一块
DEFAULT_FPS = 30


def plan_chunks(start, end, chunk_frames):
    """[start, end) -> [(a, b), ...]：覆盖完整、不重不漏（半开区间）。"""
    if chunk_frames <= 0:
        raise ValueError(f'chunk_frames must be > 0 (got {chunk_frames})')
    out = []
    a = start
    while a < end:
        b = min(a + chunk_frames, end)
        out.append((a, b))
        a = b
    return out


def block_paths(out_root, idx, a, b, png):
    """块产物 -> (产物路径, manifest 路径, 日志路径)。"""
    tag = f'{idx:04d}_{a}-{b}'
    blocks = os.path.join(out_root, 'blocks')
    if png:
        prod = os.path.join(blocks, tag)
    else:
        prod = os.path.join(blocks, f'{tag}.mp4')
    return prod, os.path.join(blocks, f'{tag}.manifest.json'), \
        os.path.join(blocks, f'{tag}.log')


def block_done(prod, manifest, n_frames, png):
    """resume 判定：产物在 + manifest 完整（帧数对得上）。

    只看"文件在"是不够的——渲染中途被杀会留下半个 manifest，故必须校验帧数。
    """
    if not os.path.isfile(manifest):
        return False
    try:
        with open(manifest, encoding='utf-8') as f:
            frames = json.load(f).get('frames', {})
    except Exception:
        return False
    if len(frames) != n_frames:
        return False
    if png:
        return os.path.isdir(prod)
    return os.path.isfile(prod) and os.path.getsize(prod) > 0


def build_cmd(act, a, b, size, seed, prod, manifest, png, ffmpeg,
              profile=None):
    """块的渲染命令：复用现有 CLI（门禁/排空线程/确定性都在那里面）。"""
    cmd = [sys.executable, '-m', 'niulai', 'render',
           '--act', act, '--start', str(a), '--end', str(b),
           '--size', size, '--seed', str(seed),
           '--out', prod, '--manifest', manifest]
    if profile:
        cmd += ['--profile', profile]
    if png:
        cmd.append('--png')
    else:
        cmd += ['--assemble', prod, '--ffmpeg', ffmpeg]
    return cmd


def merge_manifests(paths, out_path, meta=None):
    """合并各块 manifest -> 总 manifest（帧号全局有序）。"""
    frames = {}
    for p in paths:
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding='utf-8') as f:
                frames.update(json.load(f).get('frames', {}))
        except Exception as e:
            print(f'  [parallel warn] bad manifest {p}: {e}')
    data = {'frames': {k: frames[k] for k in sorted(frames, key=int)}}
    if meta:
        data['meta'] = meta
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or '.',
                exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return frames


def concat_blocks(mp4s, out_mp4, ffmpeg, audio=None):
    """纯视频 concat（-c copy，不重编码）；音轨最后统一混。

    P2 实战（0.3.1）：块各自带音轨再 concat 会丢时间（act5 曾丢 10.67s），
    故**纯视频 concat + 统一混音**。
    """
    listing = out_mp4 + '.concat.txt'
    with open(listing, 'w', encoding='utf-8') as f:
        for p in mp4s:
            f.write(f"file '{os.path.abspath(p)}'\n")
    cmd = [ffmpeg, '-y', '-f', 'concat', '-safe', '0', '-i', listing,
           '-c', 'copy']
    if audio:
        cmd += ['-i', audio, '-c:a', 'aac', '-shortest']
    cmd += [out_mp4]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f'concat failed: {(proc.stderr or "")[-1500:]}')
    if not os.path.isfile(out_mp4) or os.path.getsize(out_mp4) == 0:
        raise RuntimeError(f'concat produced no output: {out_mp4}')
    return out_mp4


def run(act, start, end, out_root, size='1280x720', seed=0, workers=2,
        chunk_seconds=DEFAULT_CHUNK_SECONDS, fps=DEFAULT_FPS, png=False,
        ffmpeg='ffmpeg', resume=False, concat=None, audio=None,
        profile=None, dry_run=False):
    """切块 -> 并发渲 -> 合并 manifest ->（可选）concat。返回统计字典。"""
    chunk_frames = max(1, int(round(chunk_seconds * fps)))
    blocks = plan_chunks(start, end, chunk_frames)
    os.makedirs(os.path.join(out_root, 'blocks'), exist_ok=True)
    # ⚠ profile 戳：resume 只看块文件存在性，不认 profile —— 若同一目录被两套
    # profile 复用，会静默拿旧块顶替（P5 实测：pbr 全片重渲被 raw 块顶掉，
    # 白渲 1.5 小时）。这里写入戳并在 resume 时校验，不一致直接报错。
    stamp = os.path.join(out_root, '_profile.txt')
    tag = profile or 'raw'
    if os.path.isfile(stamp):
        with open(stamp, encoding='utf-8') as f:
            old = f.read().strip()
        if old and old != tag:
            raise SystemExit(
                f'[parallel] profile mismatch in {out_root}: '
                f'blocks are {old!r}, requested {tag!r} — '
                f'use a separate output dir or clear it')
    else:
        with open(stamp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(tag + '\n')
    print(f'[parallel] act={act} frames {start}-{end} '
          f'({end - start} frames) -> {len(blocks)} blocks x {chunk_frames}f, '
          f'workers={workers}, png={png}')

    pending, skipped = [], 0
    for i, (a, b) in enumerate(blocks):
        prod, mani, log = block_paths(out_root, i, a, b, png)
        if resume and block_done(prod, mani, b - a, png):
            skipped += 1
            continue
        pending.append((i, a, b, prod, mani, log))
    if skipped:
        print(f'[parallel] resume: {skipped} block(s) already done, skipped')
    if dry_run:
        for i, a, b, *_ in pending:
            print(f'  block {i}: {a}-{b}')
        return {'blocks': len(blocks), 'skipped': skipped, 'pending': len(pending)}

    def poll_running(running, failed):
        """回收已结束的子进程，返回仍在运行的列表。"""
        still = []
        for job, proc, fp in running:
            if proc.poll() is None:
                still.append((job, proc, fp))
                continue
            try:
                fp.close()
            except Exception:
                pass
            i, a, b = job[0], job[1], job[2]
            if proc.returncode != 0:
                # 退出码非零不直接判死：实测 Windows 高并发下 CLI 进程
                # 在**退出阶段**（pyglet GL atexit）偶发 0xC0000409，
                # 而产物（mp4 + 完整 manifest）已写完——以 block_done()
                # 的产物完整性为准，完整即视为成功（记账：P4 全片重渲）。
                n_frames = b - a
                if block_done(prod, mani, n_frames, png):
                    print(f'  [parallel] block {i} ({a}-{b}) rc='
                          f'{proc.returncode} 但产物完整，按成功计')
                else:
                    print(f'  [parallel] block {i} ({a}-{b}) FAILED '
                          f'rc={proc.returncode} (see {job[5]})')
                    failed.append((i, a, b))
        return still

    t0 = time.perf_counter()
    running, failed = [], []
    for job in pending:
        i, a, b, prod, mani, log = job
        cmd = build_cmd(act, a, b, size, seed, prod, mani, png, ffmpeg,
                        profile=profile)
        try:
            fp = open(log, 'w', encoding='utf-8', errors='replace')
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=fp,
                                    stderr=subprocess.STDOUT)
        except Exception as e:
            print(f'  [parallel] block {i} ({a}-{b}) spawn failed: {e}')
            failed.append((i, a, b))
            continue
        running.append((job, proc, fp))
        # 达到并发上限就等一个腾位
        while len(running) >= max(1, workers):
            time.sleep(0.2)
            running = poll_running(running, failed)

    # 收尾：等剩下的全部结束
    while running:
        time.sleep(0.2)
        running = poll_running(running, failed)

    elapsed = time.perf_counter() - t0
    # 合并**全部**块的 manifest（含 resume 跳过的），得到完整的幕级清单
    manifests = [block_paths(out_root, i, a, b, png)[1]
                 for i, (a, b) in enumerate(blocks)]
    frames = merge_manifests(manifests,
                             os.path.join(out_root, 'manifest.json'),
                             meta={'act': act, 'start': start, 'end': end,
                                   'workers': workers, 'png': png,
                                   'seed': seed, 'size': size})
    rendered = len(pending) - len(failed)
    print(f'[parallel] rendered {rendered} block(s) in {elapsed:.1f}s '
          f'({(rendered * chunk_frames) / max(elapsed, 1e-6):.1f} fps '
          f'aggregate)')
    if failed:
        print(f'[parallel] FAILED {len(failed)} block(s): '
              f'{[(i, a, b) for i, a, b in failed]}')
        print('[parallel] re-run with --resume to retry only those')
    print(f'[parallel] manifest: {len(frames)} frames '
          f'-> {os.path.join(out_root, "manifest.json")}')

    if concat:
        mp4s = [block_paths(out_root, i, a, b, png)[0]
                for i, (a, b) in enumerate(blocks)]
        missing = [p for p in mp4s if not os.path.isfile(p)]
        if missing:
            print(f'[parallel] concat skipped: {len(missing)} block mp4 '
                  f'missing (e.g. {missing[0]})')
        else:
            out = concat_blocks(mp4s, concat, ffmpeg, audio=audio)
            print(f'[parallel] concat -> {out} '
                  f'({os.path.getsize(out) / 1048576.0:.1f} MB)')
    return {'blocks': len(blocks), 'skipped': skipped, 'rendered': rendered,
            'failed': len(failed), 'frames': len(frames), 'elapsed': elapsed}


def main(argv=None):
    p = argparse.ArgumentParser(prog='render_parallel')
    p.add_argument('--act', required=True)
    p.add_argument('--start', type=int, default=None,
                   help='default: act start frame (from ACTS table)')
    p.add_argument('--end', type=int, default=None,
                   help='default: act end frame')
    p.add_argument('--size', default='1280x720')
    p.add_argument('--out', default='output/parallel')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--chunk-seconds', type=float,
                   default=DEFAULT_CHUNK_SECONDS)
    p.add_argument('--fps', type=float, default=DEFAULT_FPS)
    p.add_argument('--profile', default=None,
                   choices=[None, 'raw', 'enhanced', 'pbr'],
                   help='渲染 profile（默认走 CLI 的 raw）')
    p.add_argument('--png', action='store_true',
                   help='PNG-sequence blocks (no ffmpeg needed, for '
                        'verification/debug)')
    p.add_argument('--ffmpeg', default=os.environ.get('NIULAI_FFMPEG',
                                                      'ffmpeg'))
    p.add_argument('--resume', action='store_true')
    p.add_argument('--concat', default=None,
                   help='final mp4 path (concat all blocks, -c copy)')
    p.add_argument('--audio', default=None,
                   help='mux this track in at concat time (not per block)')
    p.add_argument('--dry-run', action='store_true',
                   help='print the block plan and exit')
    args = p.parse_args(argv)

    sys.path.insert(0, ROOT)
    from niulai.cli import SCENES
    from niulai.timeline import Timeline
    if args.act not in SCENES:
        raise SystemExit(f'unknown act: {args.act}')
    tl = Timeline()
    a0, a1 = tl.act_frames(args.act)
    start = a0 if args.start is None else args.start
    end = a1 if args.end is None else args.end
    if start < a0 or end > a1 or end <= start:
        raise SystemExit(f'range {start}-{end} outside act {args.act} '
                         f'[{a0}, {a1})')
    stats = run(args.act, start, end, args.out, size=args.size, seed=args.seed,
                workers=args.workers, chunk_seconds=args.chunk_seconds,
                fps=args.fps, png=args.png, ffmpeg=args.ffmpeg,
                resume=args.resume, concat=args.concat, audio=args.audio,
                profile=args.profile, dry_run=args.dry_run)
    return 1 if stats.get('failed') else 0


if __name__ == '__main__':
    sys.exit(main())
