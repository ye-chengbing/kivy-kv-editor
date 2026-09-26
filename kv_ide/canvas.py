"""画布 + 可视节点。"""
import time

from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.properties import ObjectProperty, BooleanProperty
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from .logger import get_logger

log = get_logger("canvas")


class CanvasNode(Button):
    """可视节点，用 Kivy 官方 Button 承载，渲染完全交给 Kivy。"""

    node = ObjectProperty(None)
    editor = ObjectProperty(None)
    is_selected = BooleanProperty(False)

    def __init__(self, node, editor, **kw):
        super().__init__(**kw)
        self.node = node
        self.editor = editor
        self.size_hint = (None, None)
        self.size = node.props.get("size", (dp(120), dp(40)))
        self.text = str(node.props.get("text", node.kind))
        self.font_size = "13sp"
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0.25, 0.55, 0.85, 0.85)
        self.color = (1, 1, 1, 1)
        self.pos = (0, 0)
        self._touch_offset = (0.0, 0.0)
        self._last_log_t = 0.0                 # 日志采样时间戳
        log.debug("CanvasNode 创建 id=%s pos=%s size=%s",
                  node.id, self.pos, self.size)

    def on_is_selected(self, instance, value):
        if value:
            self.background_color = (1, 0.6, 0.2, 0.95)
        else:
            self.background_color = (0.25, 0.55, 0.85, 0.85)
        log.debug("CanvasNode is_selected id=%s -> %s", self.node.id, value)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            # 落点不在画布区域内 → 不处理，让事件穿透到下层
            cw = self.editor.canvas_widget
            in_canvas = (cw.x <= touch.x <= cw.x + cw.width and
                         cw.y <= touch.y <= cw.y + cw.height)
            if not in_canvas:
                return False

            self.editor.select(self)
            touch.grab(self)
            self._touch_offset = (touch.x - self.x, touch.y - self.y)
            log.debug("CanvasNode 按下 id=%s self.pos=%s touch=(%.1f,%.1f) "
                      "offset=%s", self.node.id, self.pos, touch.x, touch.y,
                      self._touch_offset)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self.x = touch.x - self._touch_offset[0]
            self.y = touch.y - self._touch_offset[1]
            # 采样：每 100ms 最多一条日志
            now = time.time()
            if (now - self._last_log_t) >= 0.1:
                self._last_log_t = now
                log.debug("CanvasNode 拖动 id=%s new.pos=(%.1f,%.1f)",
                          self.node.id, self.x, self.y)
            # 拖动中不 sync_pos_hint / refresh_code，松手才做
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            log.debug("CanvasNode 释放 id=%s pos=(%.1f, %.1f)",
                      self.node.id, self.x, self.y)
            # 松手时一次性提交
            self.editor.sync_pos_hint(self)
            self.editor.refresh_code()
            return True
        return super().on_touch_up(touch)


class Canvas(Widget):
    editor = ObjectProperty(None, allownone=True)

    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            Color(0.12, 0.13, 0.15, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)
        log.info("Canvas 初始化")

    def _update_bg(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size
