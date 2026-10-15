# -*- coding: utf-8 -*-
"""对白字幕轨：屏幕空间叠加层（正交投影，3D 之后绘制）。

原片台词是"梗"的一半 —— 字幕系统是 P1 刚需。设计：
- 轨 = [(t_start, t_end, speaker, text)]，line_at(t) 纯函数查询；
- 绘制：底部半透明暗条 + 说话人 + 台词（CJK 字体走 world3d 解析）；
- 自身保存/恢复 window.projection（正交<->透视），不污染下一帧 3D。
"""
import pyglet
from pyglet.gl import GL_BLEND, GL_DEPTH_TEST, GL_ONE_MINUS_SRC_ALPHA, \
    GL_SRC_ALPHA, glBlendFunc, glDisable, glEnable
from pyglet.math import Mat4

from world3d.engine.fonts import resolve_cjk_font

BAR_H = 64
BAR_COLOR = (10, 9, 8, 165)
COL_SPEAKER = (250, 226, 160, 255)
COL_TEXT = (245, 245, 240, 255)


class SubtitleTrack:
    """字幕轨。lines: [(t0, t1, speaker, text)]，单位秒。"""

    def __init__(self, lines=(), font_size=26):
        self.lines = tuple(sorted(lines))
        self.font_size = font_size
        self._batch = None
        self._label_text = None
        self._label_speaker = None
        self._bar = None
        self._w = self._h = 0
        self._cur = None

    def line_at(self, t):
        """t -> (speaker, text) 或 None（纯函数）。"""
        for t0, t1, speaker, text in self.lines:
            if t0 <= t < t1:
                return speaker, text
        return None

    def _ensure(self, win):
        if self._batch is not None and self._w == win.width:
            return
        from pyglet import shapes, text
        font_kw = {}
        cjk = resolve_cjk_font()
        if cjk:
            font_kw['font_name'] = cjk
        self._w, self._h = win.width, win.height
        self._batch = pyglet.graphics.Batch()
        self._bar = shapes.Rectangle(0, 0, self._w, BAR_H,
                                     color=BAR_COLOR, batch=self._batch)
        self._label_speaker = text.Label('', font_size=self.font_size - 4,
                                         weight='bold', x=28, y=0,
                                         anchor_x='left', anchor_y='center',
                                         color=COL_SPEAKER, batch=self._batch,
                                         **font_kw)
        self._label_text = text.Label('', font_size=self.font_size, x=28, y=0,
                                      anchor_x='left', anchor_y='center',
                                      color=COL_TEXT, batch=self._batch,
                                      **font_kw)
        self._layout()

    def _layout(self):
        w = self._w
        # 暗条铺底部 BAR_H；说话人居左、台词紧随（说话人宽度 + 24px 间距）
        self._bar.position = (0, 0)
        self._bar.width, self._bar.height = w, BAR_H
        sp_w = self._label_speaker.content_width
        self._label_speaker.position = (28, BAR_H - 26, 0)
        self._label_text.position = (28 + sp_w + 24, BAR_H - 26, 0)

    def draw(self, win, t=None):
        """作为 overlay 被 render_frame_raw 调用；t 由调用方经闭包提供。"""
        if t is None:
            return
        self._ensure(win)
        cur = self.line_at(t)
        if cur != self._cur:
            self._cur = cur
            if cur is None:
                self._label_speaker.text = ''
                self._label_text.text = ''
            else:
                speaker, text_ = cur
                self._label_speaker.text = f'{speaker}：' if speaker else ''
                self._label_text.text = text_
                self._layout()
        if self._cur is None:
            return
        # 正交投影 + **view 置单位矩阵** 画 HUD，画完两个都恢复
        # （只换 projection 不换 view 的话，暗条会被 3D 相机的 view 矩阵
        #  变换成巨大斜带 —— P1 实测踩坑）
        persp = win.projection
        view = win.view
        win.projection = Mat4.orthogonal_projection(0, self._w, 0, self._h,
                                                    -255, 255)
        win.view = Mat4()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        self._batch.draw()
        glEnable(GL_DEPTH_TEST)
        win.projection = persp
        win.view = view


class SubtitleOverlay:
    """把 SubtitleTrack 绑成 scene.overlays(t) 返回的 overlay 对象。

    用法：scene.overlays(t) -> [self._sub.at(t)]；draw(win) 时自带时刻。
    """

    def __init__(self, track):
        self.track = track
        self.t = 0.0

    def at(self, t):
        self.t = t
        return self

    def draw(self, win):
        self.track.draw(win, self.t)
