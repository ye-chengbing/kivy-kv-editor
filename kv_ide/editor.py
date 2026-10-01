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
        # 【v0.0.5 修复】Canvas 尺寸变化时重新 clamp 所有节点。
        # 不加这个的话：窗口从最大化恢复后，原来在新边界内合法的
        # 节点位置会超出缩小后的边界，看上去"卡在画布外回不来"。
        self.canvas_widget.bind(size=self._on_canvas_resize)

    # ---------- UI ----------
    def _build_ui(self):
        self.palette = Palette(self)
        self.add_widget(self.palette)

        center = BoxLayout(orientation="vertical",
                           size_hint_x=1, size_hint_y=1)

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
        cw = self.canvas_widget
        log.info("  canvas窗口原点 应为 (%(x).0f,%(y).0f), 覆盖窗口"
                 " x∈[%(x0).0f,%(x1).0f] y∈[%(y0).0f,%(y1).0f]",
                 {"x": cw.x, "y": cw.y,
                  "x0": cw.x, "x1": cw.x + cw.width,
                  "y0": cw.y, "y1": cw.y + cw.height})

    # ---------- Canvas 尺寸变化 ----------
    def _on_canvas_resize(self, canvas, new_size):
        """Canvas 尺寸变化（窗口最大化/恢复）时，重新 clamp 所有节点。

        【v0.0.5 修复】原 bug：最大化时节点放在 y=900（合法，边界 979），
        恢复窗口后 cw.height 变回 806，节点还在 y=900，吊在画布外。
        这个方法在每次 canvas 尺寸变化时把节点拉回新边界内。
        """
        if not self.nodes:
            return
        log.info("Canvas resize → %dx%d，重新 clamp %d 个节点",
                 int(new_size[0]), int(new_size[1]), len(self.nodes))
        for cn in self.nodes:
            self._clamp_node(cn)

    def _clamp_node(self, cn):
        """把单个节点夹回 Canvas 内（窗口坐标）。

        统一三处调用点：create_node / set_size / _on_canvas_resize。
        所有比较和赋值都在窗口坐标系里做——cn.center 是窗口坐标，
        cw.x/cw.y/cw.width/cw.height 也是窗口坐标。
        """
        cw = self.canvas_widget
        if cw.width <= 0 or cw.height <= 0:
            return
        half_w = cn.width / 2
        half_h = cn.height / 2
        min_cx = cw.x + half_w
        max_cx = cw.x + cw.width - half_w
        min_cy = cw.y + half_h
        max_cy = cw.y + cw.height - half_h
        cx = max(min_cx, min(cn.center_x, max_cx))
        cy = max(min_cy, min(cn.center_y, max_cy))
        if (cx, cy) != (cn.center_x, cn.center_y):
            log.debug("clamp %s (%.1f,%.1f) → (%.1f,%.1f)",
                      cn.node.id, cn.center_x, cn.center_y, cx, cy)
            cn.center = (cx, cy)
            self.sync_pos_hint(cn)

    # ---------- 键盘 ----------
    def _on_key_down(self, window, key, scancode, codepoint, modifiers):
        # Window.on_key_down 与焦点链是并行两条路（SDL 层直接派发），
        # 无条件触发，不是"焦点组件处理了就冒泡终止"。
        # 所以必须手动检查"焦点是否在 TextInput"。
        # 见 Kivy 源码 window_sdl2.py 的 mainloop 与
        # window/__init__.py 的 _on_window_key_down。
        kb = getattr(window, "_system_keyboard", None)
        focus = getattr(kb, "widget", None) if kb else None
        if isinstance(focus, TextInput):
            return False

        # 焦点丢失时按 Backspace 会误删控件；Kivy 2.x TextInput 处理
        # DELETE(127)——本项目锁 2.x。
        if key != 127:
            return False

        # 【实测用】无论带不带 Ctrl 都打印。实测确认后可删。
        log.debug("Delete 键触发 modifiers=%r", modifiers)

        # Delete 必须配合 Ctrl 才删控件。
        # modifiers 命名在不同平台 / 窗口后端下不稳定：
        #   X11 后端给 'ctrl'；SDL2 可能给 'lctrl'/'rctrl'。
        #   根因：kivy/core/window/keycodes.py 里 'ctrl' 和 'lctrl'
        #   共享 keycode 305，反查回哪个字符串取决于字典遍历顺序。
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
        # ghost 是拖动预览，要跟随鼠标在整个窗口上跑，
        # 所以挂在 root_layout（覆盖全窗口），不挂 canvas。
        mx, my = Window.mouse_pos
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
        ghost.center = (mx, my)
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

        本环境下 Kivy 把嵌套 Canvas.x 设成了相对窗口的绝对坐标
        （cw.x=180 就是 palette 宽度）。直接返回 (cw.x, cw.y)。
        """
        cw = self.canvas_widget
        log.debug("_canvas_window_origin canvas.pos=(%.1f,%.1f) "
                  "canvas.size=(%.1f,%.1f)",
                  cw.x, cw.y, cw.width, cw.height)
        return (cw.x, cw.y)

    def end_drag(self, wx, wy, kind):
        """松手时决定是否创建控件。

        【坑 A】用 Window.mouse_pos 作为权威窗口坐标。
        palette 传来的坐标只作参考。
        """
        overlay = self._overlay()
        if self.ghost and overlay:
            overlay.remove_widget(self.ghost)
        self.ghost = None

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
        # ========================================================
        # 【坐标语义·别动】节点挂在 canvas（FloatLayout）上，但
        # FloatLayout 不转换子控件坐标 —— cn.center 就是【窗口坐标】。
        # 所以这里直接 cn.center = (mx, my)，不要写成 (mx - cw.x, ...)。
        # 证据：https://kivy.org/doc/stable-2.3.0/api-kivy.uix.relativelayout
        #       .html#coordinate-systems
        # ⚠️ v0.0.4 → v0.0.5 在这个点来回折腾两天，别重犯。
        # ========================================================
        log.debug("create_node 入口 kind=%s drop_pos=%s", kind, drop_pos)
        node = Node(kind)
        cn = CanvasNode(node, self)

        cw = self.canvas_widget
        cw.add_widget(cn)

        mx, my = Window.mouse_pos
        # 窗口坐标，和 mouse_pos 同一系统
        cn.center = (mx, my)

        # clamp：限制在画布的【窗口矩形】内（统一走 _clamp_node）
        self._clamp_node(cn)

        log.info("create_node id=%s canvas.pos=(%.1f,%.1f) "
                 "cn.center(win)=(%.1f,%.1f) mouse_pos=(%.1f,%.1f) "
                 "delta=(%.1f,%.1f)",
                 node.id, cw.x, cw.y,
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
        # 【窗口坐标 → 比例】cn.center 是窗口坐标，减 cw.x/y 得相对
        # canvas 的局部坐标，再除以 canvas 尺寸得 pos_hint 比例。
        # 注意：这里减 cw.x/y 是【只为了算比例】，不是把 cn.center
        # 本身改成局部坐标——cn.center 永远是窗口坐标。
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
        # 【v0.0.5】节点挂 canvas，不是 root_layout
        cw = self.canvas_widget
        if self.selected.parent is cw:
            cw.remove_widget(self.selected)
        if self.selected in self.nodes:
            self.nodes.remove(self.selected)
        self.selected = None
        self.inspector.show_props(None)
        self.refresh_code()
        log.debug("delete_selected 出口 nodes数=%d", len(self.nodes))

    def clear_canvas(self, *a):
        log.info("clear_canvas 入口 nodes数=%d", len(self.nodes))
        # 【v0.0.5】节点挂 canvas，不是 root_layout
        cw = self.canvas_widget
        for n in list(self.nodes):
            if n.parent is cw:
                cw.remove_widget(n)
        self.nodes.clear()
        self.selected = None
        self.inspector.show_props(None)
        self.refresh_code()
        log.debug("clear_canvas 出口 nodes数=%d", len(self.nodes))

    # ---------- 属性 ----------
    def set_prop(self, cn, key, value):
        # 【坑 C 的对应修复】文字修改走 cn.text（Kivy Button 的属性），
        # 不再碰 cn._label 这种幽灵字段。
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

        # 改尺寸后可能超出画布边界，同步 clamp（统一走 _clamp_node）
        self._clamp_node(cn)

        self.sync_pos_hint(cn)
        log.info("set_size id=%s %s=%.1f", cn.node.id, axis, v)
        self.refresh_code()
        # 【坑 D 源头】这里会重建整个属性面板 → 旧输入框销毁 → 焦点丢。
        # 短期修：_on_key_down 只响应 127 且必须带 Ctrl。
        # 中期修（v0.0.6）：show_props 只在选中对象换了才重建。
        self.inspector.show_props(cn)

    # ---------- KV ----------
    def refresh_code(self):
        # 【API 事实 3.4】外层包 <EditorRoot@FloatLayout>，里面放实例。
        lines = ["<EditorRoot@FloatLayout>:"]
        for n in self.nodes:
            lines.append(n.node.to_kv(1))
        self.inspector.set_code("\n".join(lines))
