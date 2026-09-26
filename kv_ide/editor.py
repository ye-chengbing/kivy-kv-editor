"""编辑器主协调器：连接 palette / canvas / inspector，处理拖拽和节点管理。"""
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from .logger import get_logger
from .model import Node
from .palette import Palette
from .canvas import Canvas, CanvasNode
from .inspector import Inspector

log = get_logger("editor")


class KVEditor(BoxLayout):
    selected = ObjectProperty(None, allownone=True)
    ghost = ObjectProperty(None, allownone=True)

    def __init__(self, **kw):
        kw.setdefault("size_hint", (1, 1))
        kw.setdefault("pos_hint", {"x": 0, "y": 0})
        super().__init__(orientation="horizontal", **kw)
        self.nodes = []
        self._drag_kind = None
        self._build_ui()
        log.info("KVEditor 初始化完成")
        from kivy.clock import Clock
        Clock.schedule_once(self._log_layout, 0.5)
        Window.bind(on_key_down=self._on_key_down)

    # ---------- UI ----------
    def _build_ui(self):
        self.palette = Palette(self)
        self.add_widget(self.palette)

        center = BoxLayout(orientation="vertical",
                           size_hint_x=1, size_hint_y=1)   # 显式

        toolbar = BoxLayout(size_hint_y=None, height=dp(44),
                            padding=dp(6), spacing=dp(6))
        toolbar.add_widget(Label(text="画布", color=(0.85, 0.85, 0.85, 1),
                                 size_hint_x=None, width=dp(60)))
        btn_del = Button(text="删除选中", size_hint_x=None, width=dp(90))
        btn_del.bind(on_release=self.delete_selected)
        toolbar.add_widget(btn_del)
        btn_clear = Button(text="清空", size_hint_x=None, width=dp(70))
        btn_clear.bind(on_release=self.clear_canvas)
        toolbar.add_widget(btn_clear)
        center.add_widget(toolbar)

        self.canvas_widget = Canvas(editor=self)
        center.add_widget(self.canvas_widget)
        self.add_widget(center)

        self.inspector = Inspector(self)
        self.add_widget(self.inspector)

    def _log_layout(self, *args):
        def box(w):
            return f"({w.x:.0f},{w.y:.0f}) {w.width:.0f}x{w.height:.0f}"
        log.info("=== 布局检查（窗口 %sx%s）===",
                 Window.width, Window.height)
        log.info("  KVEditor  %s parent=%s",
                 box(self), type(self.parent).__name__ if self.parent else None)
        log.info("  palette   %s", box(self.palette))
        log.info("  center    %s parent=%s",
                 box(self.canvas_widget.parent),
                 type(self.canvas_widget.parent).__name__)
        log.info("  canvas    %s parent=%s",
                 box(self.canvas_widget),
                 type(self.canvas_widget.parent).__name__)
        log.info("  inspector %s", box(self.inspector))
        # 反算一次：canvas 窗口原点 = canvas.pos
        cw = self.canvas_widget
        log.info("  canvas窗口原点 应为 (%(x).0f,%(y).0f), 覆盖窗口"
                 " x∈[%(x0).0f,%(x1).0f] y∈[%(y0).0f,%(y1).0f]",
                 {"x": cw.x, "y": cw.y,
                  "x0": cw.x, "x1": cw.x + cw.width,
                  "y0": cw.y, "y1": cw.y + cw.height})

    def _on_key_down(self, window, key, scancode, codepoint, modifiers):
        # Window.on_key_down 与焦点链是并行两条路（SDL 层直接派发），
        # 无条件触发，不是"焦点组件处理了就冒泡终止"。
        # 所以必须手动检查"焦点是否在 TextInput"，否则输入框里
        # 按 Delete 会误删控件。
        # 见 Kivy 源码 window_sdl2.py 的 mainloop 与
        # window/__init__.py 的 _on_window_key_down。
        kb = getattr(window, "_system_keyboard", None)
        focus = getattr(kb, "widget", None) if kb else None
        if isinstance(focus, TextInput):
            return False

        # 焦点丢失时按 Backspace 会误删控件；Kivy 2.x TextInput 处理
        # DELETE(127)——本项目锁 2.x。（1.x 是否处理未考证，不写进注释）
        if key != 127:
            return False

        # 【实测用】无论带不带 Ctrl 都打印，方便确认当前环境下
        # modifiers 里到底是 'ctrl' 还是 'lctrl'/'rctrl'。
        # 实测确认后本行可删。
        log.debug("Delete 键触发 modifiers=%r", modifiers)

        # 【语义变更】Delete 必须配合 Ctrl 才删控件。
        # 单独按 Delete 太容易误伤（比如切焦点没成功、就想删个字符）。
        #
        # modifiers 命名在不同平台 / 窗口后端下不稳定：
        #   X11 后端给 'ctrl'；SDL2 可能给 'lctrl'/'rctrl'。
        #   根因：kivy/core/window/keycodes.py 里 'ctrl' 和 'lctrl'
        #   共享 keycode 305，反查回哪个字符串取决于字典遍历顺序。
        # 三种命名全接受，避免"按左 Ctrl 反而失效"这种反转。
        # Kivy 官方 FocusBehavior 内部也是用集合交集兼容：
        #   {'ctrl', 'alt', 'meta', 'super', 'compose'} & modifiers
        _CTRL_MODS = {'ctrl', 'lctrl', 'rctrl'}
        if not (_CTRL_MODS & set(modifiers)):
            return False

        self.delete_selected()
        return True

    # ---------- 拖拽 ----------
    def _overlay(self):
        from kivy.app import App
        app = App.get_running_app()
        return getattr(app, "root_layout", None)

    def start_drag(self, kind, wx, wy):
        mx, my = Window.mouse_pos      # 用 mouse_pos 覆盖
        overlay = self._overlay()
        if overlay is None:
            log.warning("start_drag: overlay 层不存在")
            return
        self._drag_kind = kind
        ghost = Label(
            text=f"+ {kind}", color=(1, 1, 0.6, 1), font_size="14sp",
            size_hint=(None, None), size=(dp(140), dp(28)),
        )
        overlay.add_widget(ghost)
        ghost.center = (mx, my)        # 用 mouse_pos
        self.ghost = ghost
        log.debug("start_drag kind=%s palette传参=(%.1f,%.1f) "
                  "mouse=(%.1f,%.1f) ghost.center=(%.1f,%.1f)",
                  kind, wx, wy, mx, my, ghost.center_x, ghost.center_y)

    def update_drag(self, wx, wy):
        if self.ghost:
            mx, my = Window.mouse_pos
            self.ghost.center = (mx, my)

    def _canvas_window_origin(self):
        """返回 canvas 相对窗口的坐标（左下角）。

        从日志观察：Kivy 在本环境下把嵌套的 Canvas.x 直接设成了
        相对窗口的绝对坐标（cw.x=180 就是 palette 宽度）。
        所以直接返回 (cw.x, cw.y)，不要再沿 parent 链累加，
        否则会多加一次 BoxLayout.x。
        """
        cw = self.canvas_widget
        log.debug("_canvas_window_origin canvas.pos=(%.1f,%.1f) "
                  "canvas.size=(%.1f,%.1f)",
                  cw.x, cw.y, cw.width, cw.height)
        return (cw.x, cw.y)

    def end_drag(self, wx, wy, kind):
        """松手时决定是否创建控件。

        ★ 用 Window.mouse_pos 作为权威窗口坐标（Kivy 官方 API）。
        palette 传来的坐标只作参考。
        """
        overlay = self._overlay()
        if self.ghost and overlay:
            overlay.remove_widget(self.ghost)
        self.ghost = None

        # ---- 用 mouse_pos 覆盖传入坐标 ----
        mx, my = Window.mouse_pos
        log.debug("end_drag 入口 kind=%s palette传参=(%.1f,%.1f) "
                  "mouse_pos=(%.1f,%.1f)",
                  kind, wx, wy, mx, my)
        wx, wy = mx, my

        cw = self.canvas_widget
        ox, oy = self._canvas_window_origin()
        x1 = ox + cw.width
        y1 = oy + cw.height

        in_canvas = (ox <= wx <= x1) and (oy <= wy <= y1)

        log.debug("end_drag canvas窗口矩形=[%.1f,%.1f]~[%.1f,%.1f] "
                  "mouse=(%.1f,%.1f) in_canvas=%s",
                  ox, oy, x1, y1, wx, wy, in_canvas)

        if in_canvas:
            lx = wx - ox
            ly = wy - oy
            log.info("end_drag 创建 kind=%s canvas局部=(%.1f,%.1f) "
                     "[win=(%.1f,%.1f) - canvas原点=(%.1f,%.1f)]",
                     kind, lx, ly, wx, wy, ox, oy)
            self.create_node(kind, drop_pos=(lx, ly))
        else:
            log.debug("end_drag 落点不在画布内，忽略 kind=%s", kind)

        log.debug("end_drag 出口 nodes数=%d selected=%s",
                  len(self.nodes),
                  self.selected.node.id if self.selected else None)

    # ---------- 节点管理 ----------
    def create_node(self, kind, drop_pos=None):
        log.debug("create_node 入口 kind=%s drop_pos=%s", kind, drop_pos)
        node = Node(kind)
        cn = CanvasNode(node, self)

        # 加到 root_layout，不用 canvas 当父级
        overlay = self._overlay()
        overlay.add_widget(cn)

        # 直接用鼠标窗口坐标，不再做任何转换
        mx, my = Window.mouse_pos
        cn.center = (mx, my)

        log.info("create_node id=%s overlay=%s cn.center=(%.1f,%.1f) "
                 "mouse=(%.1f,%.1f) delta=(%.1f,%.1f)",
                 node.id, type(overlay).__name__,
                 cn.center_x, cn.center_y, mx, my,
                 cn.center_x - mx, cn.center_y - my)

        node.props["size"] = (cn.width, cn.height)
        self.nodes.append(cn)
        self.sync_pos_hint(cn)
        self.select(cn)
        self.refresh_code()
        log.debug("create_node 出口 nodes数=%d", len(self.nodes))

    def sync_pos_hint(self, cn):
        cw = self.canvas_widget
        if cw.width <= 0 or cw.height <= 0:
            return
        lx = cn.center_x - cw.x
        ly = cn.center_y - cw.y
        cn.node.props["pos_hint"] = {
            "center_x": round(lx / cw.width, 3),
            "center_y": round(ly / cw.height, 3),
        }

    def select(self, cn):
        if self.selected and self.selected is not cn:
            self.selected.is_selected = False
        self.selected = cn
        cn.is_selected = True
        self.inspector.show_props(cn)
        log.debug("select 入口 id=%s kind=%s pos=(%.1f,%.1f)",
                  cn.node.id, cn.node.kind, cn.x, cn.y)

    def delete_selected(self, *a):
        if not self.selected:
            log.debug("delete_selected: 当前无选中")
            return
        log.info("delete_selected id=%s", self.selected.node.id)
        overlay = self._overlay()
        if overlay and self.selected.parent is overlay:
            overlay.remove_widget(self.selected)
        if self.selected in self.nodes:
            self.nodes.remove(self.selected)
        self.selected = None
        self.inspector.show_props(None)
        self.refresh_code()
        log.debug("delete_selected 出口 nodes数=%d", len(self.nodes))

    def clear_canvas(self, *a):
        log.info("clear_canvas 入口 nodes数=%d", len(self.nodes))
        overlay = self._overlay()
        for n in list(self.nodes):
            if overlay and n.parent is overlay:
                overlay.remove_widget(n)
        self.nodes.clear()
        self.selected = None
        self.inspector.show_props(None)
        self.refresh_code()
        log.debug("clear_canvas 出口 nodes数=%d", len(self.nodes))

    # ---------- 属性 ----------
    def set_prop(self, cn, key, value):
        old = cn.node.props.get(key)
        cn.node.props[key] = value
        if key == "text":
            cn.text = value
        log.info("set_prop id=%s %s: %r → %r", cn.node.id, key, old, value)
        self.refresh_code()

    def set_size(self, cn, axis, value):
        try:
            v = dp(float(value))
        except ValueError:
            log.warning("set_size 非法值 axis=%s value=%r", axis, value)
            return
        if axis == "width":
            cn.width = v
            cn.node.props["size"] = (v, cn.height)
        else:
            cn.height = v
            cn.node.props["size"] = (cn.width, v)
        cn.node.props["size_hint"] = (None, None)
        self.sync_pos_hint(cn)
        log.info("set_size id=%s %s=%.1f", cn.node.id, axis, v)
        self.refresh_code()
        self.inspector.show_props(cn)

    # ---------- KV ----------
    def refresh_code(self):
        lines = ["<EditorRoot@FloatLayout>:"]
        for n in self.nodes:
            lines.append(n.node.to_kv(1))
        self.inspector.set_code("\n".join(lines))
