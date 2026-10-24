"""
左侧组件库面板。只负责 UI + 触发拖拽，不关心拖拽具体实现。
0.1.0让ai帮改了PaletteItem类。
"""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from .logger import get_logger

log = get_logger("palette")

COMPONENT_KINDS = ["Button", "Label", "TextInput", "ToggleButton","Slider", "Spinner", "BoxLayout", "GridLayout",]


class PaletteItem(Button):
    """
    这次的坐标转换是有史以来最稳定的一版
    """
    def __init__(self, kind, editor, **kw):
        super().__init__(text=kind, size_hint_y=None, height=dp(38),
                         font_size="13sp", **kw)
        self.kind = kind
        self.editor = editor

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.editor.start_drag(self.kind)
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self.editor.update_drag()
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.editor.end_drag(self.kind)
            return True
        return super().on_touch_up(touch)


class Palette(BoxLayout):
    def __init__(self, editor, **kw):
        super().__init__(orientation="vertical", size_hint_x=None,
                         width=dp(180), padding=dp(8), spacing=dp(6), **kw)
        self.editor = editor

        self.add_widget(Label(text="[b]Components[/b]", markup=True,
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
