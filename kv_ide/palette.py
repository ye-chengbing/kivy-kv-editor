"""左侧组件库面板。只负责 UI + 触发拖拽，不关心拖拽具体实现。"""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from .logger import get_logger

log = get_logger("palette")

COMPONENT_KINDS = ["Button", "Label", "TextInput", "ToggleButton",
                   "Slider", "Spinner", "BoxLayout", "GridLayout"]


class PaletteItem(Button):
    def __init__(self, kind, editor, **kw):
        super().__init__(text=kind, size_hint_y=None, height=dp(38),
                         font_size="13sp", **kw)
        self.kind = kind
        self.editor = editor

    def _window_pos(self, touch):
        """把 touch 坐标转成窗口坐标。

        |一些烦人的东西|
        ====================
        坑名：
            touch.x/y 在 widget 回调里是相对 widget.parent 的坐标系
        证实方式：
            不清楚咋回事，没查到资料，但这样写能用。
            （用 to_window 转换后坐标正确，但没找到官方文档
             明确说明 touch 坐标的坐标系归属。）
        ！！！绝对绝对绝对不要动它，现在能稳定跑是它对我们的宽容！！！
        ====================
        """
        lx = touch.x - self.x
        ly = touch.y - self.y
        return self.to_window(lx, ly)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            wx, wy = self._window_pos(touch)
            log.debug("palette 按下 kind=%s win=(%.1f, %.1f)",
                      self.kind, wx, wy)
            self.editor.start_drag(self.kind, wx, wy)
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            wx, wy = self._window_pos(touch)
            self.editor.update_drag(wx, wy)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            wx, wy = self._window_pos(touch)
            touch.ungrab(self)
            log.debug("palette 释放 kind=%s win=(%.1f, %.1f)",
                      self.kind, wx, wy)
            self.editor.end_drag(wx, wy, self.kind)
            return True
        return super().on_touch_up(touch)


class Palette(BoxLayout):
    def __init__(self, editor, **kw):
        super().__init__(orientation="vertical", size_hint_x=None,
                         width=dp(180), padding=dp(8), spacing=dp(6), **kw)
        self.editor = editor

        self.add_widget(Label(text="[b]组件库[/b]", markup=True,
                              size_hint_y=None, height=dp(32),
                              color=(0.9, 0.9, 0.9, 1)))

        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=dp(6),
                          size_hint_y=None, padding=dp(4))
        grid.bind(minimum_height=grid.setter("height"))
        for k in COMPONENT_KINDS:
            grid.add_widget(PaletteItem(k, editor))
        scroll.add_widget(grid)
        self.add_widget(scroll)

        log.info("Palette 初始化，组件数=%d", len(COMPONENT_KINDS))
