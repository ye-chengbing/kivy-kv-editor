"""画布 + 可视节点。"""
import time

from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.properties import ObjectProperty, BooleanProperty
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from .logger import get_logger

log = get_logger("canvas")


class CanvasNode(Button):
    """可视节点。

    ============================================================
    |一些烦人的东西|
    ====================
    坑名：
        手写 graphics 模仿官方组件，蓝框堆在画布左下角
    证实方式：
        https://stackoverflow.com/questions/32752894/
        原文："Your drawing code is running before the label pos has
               been set by its parent layout - basically you're
               hitting the issue that your rectangle position doesn't
               update when the label position later does."
        Rectangle 的 pos 不会自动跟随 widget 移动，必须手动 bind。
        所以不要手写 graphics 模仿组件，直接继承官方 Button。
    ！！！绝对绝对绝对不要动它，现在能稳定跑是它对我们的宽容！！！
    ====================

    |一些烦人的东西|
    ====================
    坑名：
        FloatLayout 不转换子控件坐标，误当局部坐标处理会偏 180px
    证实方式：
        https://kivy.org/doc/stable-2.3.0/api-kivy.uix.relativelayout.html
        #coordinate-systems
        原文："these coordinate systems are identical to the window
               coordinate system as long as a relative layout type
               widget is not in the widget's parent stack."
        只有 RelativeLayout / Scatter / ScatterLayout / ScrollView
        在父链中时才会转换子控件坐标。FloatLayout 不在其中。
        v0.0.4→v0.0.5 在这个点来回折腾两天，别重犯！！
    ！！！绝对绝对绝对不要动它，现在能稳定跑是它对我们的宽容！！！
    ====================
    ============================================================
    """

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
        self._last_log_t = 0.0
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
            cw = self.editor.canvas_widget

            # 落点不在画布区域内 → 不处理，让事件穿透到下层
            in_canvas = (cw.x <= touch.x <= cw.x + cw.width and
                         cw.y <= touch.y <= cw.y + cw.height)
            if not in_canvas:
                return False

            self.editor.select(self)
            touch.grab(self)

            # 【窗口坐标】touch 和 self.x/y 同一坐标系，直接相减。
            # 不要在这里加任何 cw.x/cw.y 的换算。
            self._touch_offset = (touch.x - self.x, touch.y - self.y)
            log.debug("CanvasNode 按下 id=%s pos(win)=(%.1f,%.1f) "
                      "touch=(%.1f,%.1f) offset=%s",
                      self.node.id, self.x, self.y,
                      touch.x, touch.y, self._touch_offset)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            cw = self.editor.canvas_widget

            # 【窗口坐标】touch - offset 直接得目标窗口坐标。
            # 不要在这里做 "再减 cw.x" 的"局部坐标"换算——
            # FloatLayout 不认局部坐标，见类 docstring。
            new_x = touch.x - self._touch_offset[0]
            new_y = touch.y - self._touch_offset[1]

            # clamp 到画布的【窗口矩形】内
            min_x = cw.x
            max_x = cw.x + cw.width - self.width
            min_y = cw.y
            max_y = cw.y + cw.height - self.height
            new_x = max(min_x, min(new_x, max_x))
            new_y = max(min_y, min(new_y, max_y))

            self.x = new_x
            self.y = new_y

            now = time.time()
            if (now - self._last_log_t) >= 0.1:
                self._last_log_t = now
                log.debug("CanvasNode 拖动 id=%s new.pos(win)=(%.1f,%.1f)",
                          self.node.id, self.x, self.y)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            log.debug("CanvasNode 释放 id=%s pos(win)=(%.1f, %.1f)",
                      self.node.id, self.x, self.y)
            self.editor.sync_pos_hint(self)
            self.editor.refresh_code()
            return True
        return super().on_touch_up(touch)


class Canvas(FloatLayout):
    """画布背景 + 节点容器。

    【v0.0.5】从 Widget 改成 FloatLayout 是为了：
    - 语义上明确"这是容器，子控件挂在里面"
    - 未来可用 pos_hint 布局，为裁剪 / 滚动 / 缩放铺路

    |一些烦人的东西|
    ====================
    坑名：
        FloatLayout 不改变子控件坐标系统，子控件 x/y 仍是窗口坐标
    证实方式：
        https://kivy.org/doc/stable-2.3.0/api-kivy.uix.relativelayout.html
        #coordinate-systems
        上述 URL 明确列出只有 RelativeLayout / Scatter /
        ScatterLayout / ScrollView 会转换坐标。
        FloatLayout 的 do_layout() 只处理 size_hint 和 pos_hint，
        不改变子控件的坐标系。
    ！！！绝对绝对绝对不要动它，现在能稳定跑是它对我们的宽容！！！
    ====================

    这里的 graphics 是【合法的】——背景就是画一块相对self 的矩形，基准和同步逻辑都自洽。
    """

    editor = ObjectProperty(None, allownone=True)

    def __init__(self, **kw):
        super().__init__(**kw)
        # ========================================================
        # |一些烦人的东西|
        # ====================
        # 坑名：
        #     canvas.before / canvas.after 的执行顺序
        # 证实方式：
        #     https://kivy.org/doc/stable/guide/graphics.html
        #     原文："The instructions in these groups will be executed
        #            before and after the canvas group respectively.
        #            This means that they will appear under (be executed
        #            before) and above (be executed after) them."
        #     canvas.before 的指令在 widget 主 canvas 之前执行，
        #     视觉上在下层。背景用 canvas.before 是正确的。
        # ！！！绝对绝对绝对不要动它，现在能稳定跑是它对我们的宽容！！！
        # ====================
        # ========================================================
        with self.canvas.before:
            Color(0.12, 0.13, 0.15, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)
        log.info("Canvas 初始化")

    def _update_bg(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size
