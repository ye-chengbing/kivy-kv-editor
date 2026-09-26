"""右侧属性/代码面板。只负责显示与收集输入，把动作转给 editor。"""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from .logger import get_logger

log = get_logger("inspector")


class Inspector(BoxLayout):
    def __init__(self, editor, **kw):
        super().__init__(orientation="vertical", size_hint_x=None,
                         width=dp(330), padding=dp(8), spacing=dp(6), **kw)
        self.editor = editor

        # 属性区
        self.add_widget(Label(text="[b]属性[/b]", markup=True,
                              size_hint_y=None, height=dp(28),
                              color=(0.9, 0.9, 0.9, 1)))
        self.prop_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                  spacing=dp(4))
        self.prop_box.bind(minimum_height=self.prop_box.setter("height"))
        prop_scroll = ScrollView(size_hint_y=0.55)
        prop_scroll.add_widget(self.prop_box)
        self.add_widget(prop_scroll)

        # KV 代码区
        self.add_widget(Label(text="[b]KV 代码[/b]", markup=True,
                              size_hint_y=None, height=dp(28),
                              color=(0.9, 0.9, 0.9, 1)))
        self.code_out = TextInput(
            text="", readonly=True, font_size="12sp",
            background_color=(0.1, 0.1, 0.12, 1),
            foreground_color=(0.85, 0.95, 0.85, 1),
        )
        self.add_widget(self.code_out)

        btn_copy = Button(text="复制 KV", size_hint_y=None, height=dp(36))
        btn_copy.bind(on_release=self._copy)
        self.add_widget(btn_copy)

        log.info("Inspector 初始化")

    def _copy(self, *a):
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(self.code_out.text)
            log.info("KV 已复制到剪贴板（%d 字符）", len(self.code_out.text))
        except Exception as e:
            log.warning("复制失败: %s", e)

    def show_props(self, canvas_node):
        self.prop_box.clear_widgets()
        if not canvas_node:
            self.prop_box.add_widget(
                Label(text="未选中控件", color=(0.6, 0.6, 0.6, 1),
                      size_hint_y=None, height=dp(30)))
            log.debug("属性面板：清空（无选中）")
            return

        self._add_prop_row(canvas_node, "text", "文本")
        self._add_prop_row(canvas_node, "width", "宽度")
        self._add_prop_row(canvas_node, "height", "高度")
        log.debug("属性面板：展示 id=%s 的 3 项属性", canvas_node.node.id)

    def _add_prop_row(self, cn, key, label):
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        row.add_widget(Label(text=label, size_hint_x=0.4,
                             color=(0.85, 0.85, 0.85, 1)))

        if key == "width":
            ti = TextInput(text=str(int(cn.width)),
                           multiline=False, size_hint_x=0.6)
            ti.bind(on_text_validate=lambda *a: self.editor.set_size(cn, "width", ti.text))
        elif key == "height":
            ti = TextInput(text=str(int(cn.height)),
                           multiline=False, size_hint_x=0.6)
            ti.bind(on_text_validate=lambda *a: self.editor.set_size(cn, "height", ti.text))
        else:
            ti = TextInput(text=str(cn.node.props.get(key, "")),
                           multiline=False, size_hint_x=0.6)
            ti.bind(on_text_validate=lambda *a, k=key: self.editor.set_prop(cn, k, ti.text))

        row.add_widget(ti)
        self.prop_box.add_widget(row)

    def set_code(self, text):
        self.code_out.text = text
