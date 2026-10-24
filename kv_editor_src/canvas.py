"""画布 + 可视节点。"""
from kivy.metrics import dp
from kivy.properties import ObjectProperty, BooleanProperty
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.scatterlayout import ScatterLayout
from kivy.graphics import Color, Rectangle


from .logger import get_logger

log = get_logger("canvas")


class CanvasNode(Button):
    """可视节点。只负责处理鼠标事件，坐标计算全丢给 Editor。"""
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
        
        self._is_dragging = False
        self._touch_start_pos = (0, 0)
        self._widget_start_pos = (0, 0)

    # 这里 instance 官方要求是必须的
    def on_is_selected(self, instance, value):
        if value:
            self.background_color = (1, 0.6, 0.2, 0.95)
        else:
            self.background_color = (0.25, 0.55, 0.85, 0.85)

    def on_touch_down(self, touch):
        if isinstance(self.parent, ScatterLayout):
            if self.parent.rotation != 0 or self.parent.scale != 1.0:
                return False

        if self.collide_point(*touch.pos):
            self.editor.select(self)
            touch.grab(self)
            
            self._is_dragging = False
            self._touch_start_pos = (touch.x, touch.y)
            self._widget_start_pos = (self.x, self.y)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            if isinstance(self.parent, ScatterLayout):
                if self.parent.rotation != 0 or self.parent.scale != 1.0:
                    return False
            
            dx = touch.x - self._touch_start_pos[0]
            dy = touch.y - self._touch_start_pos[1]
            
            # 阈值
            if not self._is_dragging:
                if abs(dx) < dp(5) and abs(dy) < dp(5):
                    return True
                self._is_dragging = True
            
            # 纯数学偏移算新位置
            raw_x = self._widget_start_pos[0] + dx
            raw_y = self._widget_start_pos[1] + dy

            # 丢给 editor 去判断边界
            self.x, self.y = self.editor.clamp_position(raw_x, raw_y, self.width, self.height)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            if self._is_dragging:
                self.editor.sync_pos_hint(self)
                self.editor.refresh_code()
                self._is_dragging = False
            return True
        return super().on_touch_up(touch)


class Canvas(FloatLayout):
    """画布容器。"""
    editor = ObjectProperty(None, allownone=True)

    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            Color(0.12, 0.13, 0.15, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)
        
        self.user_root = None

    def set_root_layout(self, root_type):
        if self.user_root:
            self.remove_widget(self.user_root)

        if root_type == "FloatLayout":
            self.user_root = FloatLayout()
        elif root_type == "RelativeLayout":
            self.user_root = RelativeLayout()
        elif root_type == "ScatterLayout":
            self.user_root = ScatterLayout(auto_bring_to_front=False)
            self.user_root.do_rotation = False
            self.user_root.do_scale = False
        else:
            self.user_root = FloatLayout()

        self.user_root.size_hint = (1, 1)
        self.user_root.pos_hint = {"x": 0, "y": 0}
        self.add_widget(self.user_root)

    def _update_bg(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size
