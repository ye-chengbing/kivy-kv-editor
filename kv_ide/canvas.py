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

    【坑 B 的对应修复】不手写 graphics 模仿官方组件——之前试过在
    self.canvas.before 里画 Rectangle(pos=...)，基准是 widget 局部坐标
    而非父级，结果所有控件蓝框堆到画布左下角。改成继承 Kivy 官方
    Button 后，渲染完全交给 Kivy，不用自己管 draw 逻辑。

    ============================================================
    【坐标语义·重要 · 别动】
    ============================================================
    Kivy 官方文档明确：FloatLayout 【不转换】子控件坐标系统。
    子控件的 x/y/center 和 touch.pos 一样，都是【窗口坐标】。

    只有以下四种容器在父链中时，才会让子控件坐标相对自己：
        RelativeLayout / Scatter / ScatterLayout / ScrollView
    FloatLayout 不在其中。

    来源（证据）：
      https://kivy.org/doc/stable-2.3.0/api-kivy.uix.relativelayout.html
      #coordinate-systems
      → "these coordinate systems are identical to the window
         coordinate system as long as a relative layout type widget
         is not in the widget's parent stack."

    ⚠️ 历史教训（v0.0.5 踩过，别重犯）：
    不要把 cn.center 改成 "mx - canvas.x" 这种"局部坐标"写法！
    FloatLayout 不会把它当局部坐标解释，控件会往左偏 cw.x=180。
    这个坑 v0.0.4 → v0.0.5 来回折腾了两天，2026-10-01 又差点绕回去。
    以后所有节点坐标一律用【窗口坐标】，只在算 pos_hint 时
    才减 canvas.pos 转成比例。
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

    ⚠️ 但【不改坐标系统】——FloatLayout 的子控件 x/y 仍是窗口坐标。
    证据与详细说明见 CanvasNode 类 docstring 顶部的 "坐标语义" 段，
    以及：https://kivy.org/doc/stable-2.3.0/api-kivy.uix.relativelayout
           .html#coordinate-systems

    【坑 B 边界】这里的 graphics 是【合法的】——背景就是画一块相对
    self 的矩形，基准和同步逻辑都自洽。要画【控件级】的可视元素，
    一律继承官方组件，不要自己 draw。
    """

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
