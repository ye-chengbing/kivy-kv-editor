"""编辑器主协调器：连接 palette / canvas / inspector，处理拖拽和节点管理。"""
import json
import os

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
        # 根节点信息：用户在 Inspector 里改类名，导出时用来生成 KV 首行
        self.root_class_name = "MyRoot"
        self.root_type = "FloatLayout"
        self._build_ui()
        self.inspector.show_props(None)   # 初始显示根名输入框
        log.info("KVEditor 初始化完成")
        from kivy.clock import Clock
        Clock.schedule_once(self._log_layout, 0.5)
        Window.bind(on_key_down=self._on_key_down)
        # 【v0.0.5 修复】Canvas 尺寸变化时重新 clamp 所有节点。
        self.canvas_widget.bind(size=self._on_canvas_resize)

    # ---------- UI ----------
    def _build_ui(self):
        self.palette = Palette(self)
        self.add_widget(self.palette)

        center = BoxLayout(orientation="vertical",
                           size_hint_x=1, size_hint_y=1)

        toolbar = BoxLayout(size_hint_y=None, height=dp(44),
                            padding=dp(6), spacing=dp(6))
        toolbar.add_widget(Label(text="Canvas", color=(0.85, 0.85, 0.85, 1),
                                 size_hint_x=None, width=dp(60)))
        btn_del = Button(text="Delete", size_hint_x=None, width=dp(70))
        btn_del.bind(on_release=self.delete_selected)
        toolbar.add_widget(btn_del)
        btn_clear = Button(text="Clear", size_hint_x=None, width=dp(60))
        btn_clear.bind(on_release=self.clear_canvas)
        toolbar.add_widget(btn_clear)
        btn_export = Button(text="Export", size_hint_x=None, width=dp(70))
        btn_export.bind(on_release=self.export_files)
        toolbar.add_widget(btn_export)
        btn_import = Button(text="Import", size_hint_x=None, width=dp(70))
        btn_import.bind(on_release=self.import_json)
        toolbar.add_widget(btn_import)
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
        """Canvas 尺寸变化（窗口最大化/恢复）时，重新 clamp 所有节点。"""
        if not self.nodes:
            return
        log.info("Canvas resize → %dx%d，重新 clamp %d 个节点",
                 int(new_size[0]), int(new_size[1]), len(self.nodes))
        for cn in self.nodes:
            self._clamp_node(cn)

    def _clamp_node(self, cn):
        """把单个节点夹回 Canvas 内（窗口坐标）。

        ==========
        用于：
            统一三处调用点：create_node / set_size / _on_canvas_resize。
            所有比较和赋值都在窗口坐标系里做——cn.center 是窗口坐标，
            cw.x/cw.y/cw.width/cw.height 也是窗口坐标。
        输入：
            A：cn: CanvasNode — 待夹紧的节点
        输出：
            无返回值。副作用：必要时改 cn.center，并刷新 pos_hint。
        ==========
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
        # ========================================================
        # |一些烦人的东西|
        # ====================
        # 坑名：
        #     Window.on_key_down 与焦点链是并行两条路，无条件触发
        # 证实方式：
        #     https://kivy.org/doc/stable/api-kivy.core.window.html
        #     #kivy.core.window.Window.on_key_down
        #     TextInput 的 keyboard_on_key_down 是另一条路：
        #     https://kivy.readthedocs.io/en/master/api-kivy.uix.textinput
        #     .html#kivy.uix.textinput.TextInput.keyboard_on_key_down
        #     原文："The method bound to the keyboard when the instance
        #            has focus... will be called for every input press."
        #     两条路并行，不互相拦截。所以 Window.on_key_down 里
        #     必须手动检查焦点是否在 TextInput。
        # ！！！绝对绝对绝对不要动它，现在能稳定跑是它对我们的宽容！！！
        # ====================
        # ========================================================
        kb = getattr(window, "_system_keyboard", None)
        focus = getattr(kb, "widget", None) if kb else None
        if isinstance(focus, TextInput):
            return False

        # ========================================================
        # |一些烦人的东西|
        # ====================
        # 坑名：
        #     Kivy 里 Delete 键的 keycode 是 127，Backspace 是 8
        # 证实方式：
        #     Kivy 源码 textinput.py 的 interesting_keys：
        #     https://github.com/kivy/kivy/blob/master/kivy/uix/textinput.py
        #     原文：`{ 8: 'backspace', 13: 'enter', 127: 'del', ... }`
        #     文档：https://kivy.readthedocs.io/en/master/api-kivy.uix
        #     .textinput.html
        #     "Del — Delete the selection of character after the cursor"
        # ！！！绝对绝对绝对不要动它，现在能稳定跑是它对我们的宽容！！！
        # ====================
        # ========================================================
        if key != 127:
            return False

        # 【实测用】无论带不带 Ctrl 都打印。实测确认后可删。
        log.debug("Delete 键触发 modifiers=%r", modifiers)

        # ========================================================
        # |一些烦人的东西|
        # ====================
        # 坑名：
        #     modifiers 命名在不同平台/后端下不稳定
        # 证实方式：
        #     Kivy 源码 keycodes 表同时有 'lctrl': 305 和 'rctrl': 306：
        #     https://kivy.org/doc/stable/api-kivy.core.window.html
        #     StackOverflow 2016 年实测给的是 'lctrl'：
        #     https://stackoverflow.com/questions/35669747/
        #     当前环境实测给 'ctrl'（见 editor.log），但不保证换平台
        #     也给 'ctrl'。三种全接受。
        # ！！！绝对绝对绝对不要动它，现在能稳定跑是它对我们的宽容！！！
        # ====================
        # ========================================================
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

        |一些烦人的东西|
        ====================
        坑名：
            本环境下 Kivy 把嵌套 Canvas.x 设成了相对窗口的绝对坐标
        证实方式：
            不清楚咋回事，没查到资料，但这样写能用。
            （cw.x=180 就是 palette 宽度，直接在日志里观察到，
             但没找到 Kivy 官方文档或社区解释这个行为。）
        ！！！绝对绝对绝对不要动它，现在能稳定跑是它对我们的宽容！！！
        ====================
        """
        cw = self.canvas_widget
        log.debug("_canvas_window_origin canvas.pos=(%.1f,%.1f) "
                  "canvas.size=(%.1f,%.1f)",
                  cw.x, cw.y, cw.width, cw.height)
        return (cw.x, cw.y)

    def end_drag(self, wx, wy, kind):
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
        # v0.0.4 → v0.0.5 在这个点来回折腾两天，别重犯。
        # ========================================================
        log.debug("create_node 入口 kind=%s drop_pos=%s", kind, drop_pos)
        node = Node(kind)
        cn = CanvasNode(node, self)

        cw = self.canvas_widget
        cw.add_widget(cn)

        mx, my = Window.mouse_pos
        cn.center = (mx, my)

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
        old = cn.node.props.get(key)
        cn.node.props[key] = value
        if key == "text":
            cn.text = value
        log.info("set_prop id=%s %s: %r → %r", cn.node.id, key, old, value)
        self.refresh_code()

    def set_id(self, cn, new_id):
        """修改节点 id。id 是数据层字段，不是 cn.node.props 里的属性。

        ==========
        用于：
            用户改 Inspector 里的 ID 输入框时调用。改完刷新 KV。
        输入：
            A：cn: CanvasNode — 待改 id 的节点
            B：new_id: str — 新 id（去首尾空白；空则忽略）
        输出：
            无返回值。副作用：改 cn.node.id，刷新 KV + 属性面板。
        ==========
        """
        new_id = new_id.strip()
        if not new_id:
            return
        old = cn.node.id
        if old == new_id:
            return
        cn.node.id = new_id
        log.info("set_id %s → %s", old, new_id)
        self.refresh_code()
        self.inspector.show_props(cn)

    def set_root_class_name(self, name):
        """修改根节点类名（KV 首行 `<XXX>:` 里的 XXX）。

        ==========
        用于：
            用户改 Inspector 的 Root Name 输入框时调用。
        输入：
            A：name: str — 新类名（去首尾空白；空则忽略）
        输出：
            无返回值。副作用：改 self.root_class_name，刷新 KV。
        ==========
        """
        name = name.strip()
        if not name or name == self.root_class_name:
            return
        log.info("根类名 %s → %s", self.root_class_name, name)
        self.root_class_name = name
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

        self._clamp_node(cn)
        self.sync_pos_hint(cn)
        log.info("set_size id=%s %s=%.1f", cn.node.id, axis, v)
        self.refresh_code()
        # ========================================================
        # |一些烦人的东西|
        # ====================
        # 坑名：
        #     show_props 的 clear_widgets 导致输入框焦点丢失，
        #     进而 Backspace 误删控件
        # 证实方式：
        #     不清楚咋回事，没查到资料，但这样写能用。
        #     （只知道 clear_widgets 会销毁旧输入框，焦点凭空消失，
        #       但没找到 Kivy 官方文档解释焦点链的恢复机制。）
        # ！！！绝对绝对绝对不要动它，现在能稳定跑是它对我们的宽容！！！
        # ====================
        # ========================================================
        self.inspector.show_props(cn)

    # ---------- 导出 / 导入 ----------
    def export_files(self, *a):
        """弹出文件对话框，导出 .kv + .json 两个文件。

        ==========
        用于：
            工具栏 Export 按钮。
            .kv 是给用户的 Kivy 布局；.json 是编辑器元数据（含层级/数据/id）。
        输入：
            无
        输出：
            无返回值。副作用：写两个文件到用户选定目录。
        ==========
        """
        from kivy.uix.popup import Popup
        from kivy.uix.filechooser import FileChooserListView

        content = BoxLayout(orientation="vertical",
                            spacing=dp(6), padding=dp(6))
        filechooser = FileChooserListView(path=".", dirselect=False)
        content.add_widget(filechooser)

        name_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        name_row.add_widget(Label(text="Filename:", size_hint_x=None,
                                  width=dp(90),
                                  color=(0.85, 0.85, 0.85, 1)))
        name_input = TextInput(text="layout", multiline=False)
        name_row.add_widget(name_input)
        content.add_widget(name_row)

        btn_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        btn_save = Button(text="Save")
        btn_cancel = Button(text="Cancel")
        btn_row.add_widget(btn_save)
        btn_row.add_widget(btn_cancel)
        content.add_widget(btn_row)

        popup = Popup(title="Export KV + JSON", content=content,
                      size_hint=(0.9, 0.9))

        def do_save(*a):
            fname = name_input.text.strip() or "layout"
            base = os.path.join(filechooser.path, fname)
            kv_path = base + ".kv"
            json_path = base + ".json"
            try:
                with open(kv_path, "w", encoding="utf-8") as f:
                    f.write(self.inspector.code_out.text)
                data = {
                    "version": 1,
                    "root": {
                        "type": self.root_type,
                        "props": {},
                        "children": [n.node.to_json() for n in self.nodes],
                    },
                }
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                log.info("导出成功: %s, %s", kv_path, json_path)
            except Exception as e:
                log.exception("导出失败: %s", e)
            popup.dismiss()

        btn_save.bind(on_release=do_save)
        btn_cancel.bind(on_release=popup.dismiss)
        popup.open()

    def import_json(self, *a):
        """弹出文件对话框，读取 .json 恢复节点树。

        ==========
        用于：
            工具栏 Import 按钮。读取之前导出的 .json，
            清空画布并按 pos_hint 反算位置重建所有节点。
        输入：
            无
        输出：
            无返回值。副作用：重写 self.nodes，刷新画布和 KV。
        ==========
        """
        from kivy.uix.popup import Popup
        from kivy.uix.filechooser import FileChooserListView

        content = BoxLayout(orientation="vertical",
                            spacing=dp(6), padding=dp(6))
        filechooser = FileChooserListView(path=".", filters=["*.json"])
        content.add_widget(filechooser)

        btn_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        btn_load = Button(text="Load")
        btn_cancel = Button(text="Cancel")
        btn_row.add_widget(btn_load)
        btn_row.add_widget(btn_cancel)
        content.add_widget(btn_row)

        popup = Popup(title="Import JSON", content=content,
                      size_hint=(0.9, 0.9))

        def do_load(*a):
            if not filechooser.selection:
                log.warning("import_json: 未选中文件")
                return
            path = filechooser.selection[0]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                log.exception("读 JSON 失败: %s", e)
                popup.dismiss()
                return

            # 清空画布（不调 clear_canvas，避免中途 refresh）
            cw = self.canvas_widget
            for n in list(self.nodes):
                if n.parent is cw:
                    cw.remove_widget(n)
            self.nodes.clear()
            self.selected = None

            # 重建
            max_num = 0
            for child_data in data.get("root", {}).get("children", []):
                node = Node.from_json(child_data)
                cn = CanvasNode(node, self)
                cw.add_widget(cn)

                # 从 pos_hint 反算窗口坐标
                ph = node.props.get("pos_hint", {})
                cx = ph.get("center_x", 0.5)
                cy = ph.get("center_y", 0.5)
                win_cx = cw.x + cx * cw.width
                win_cy = cw.y + cy * cw.height
                cn.center = (win_cx, win_cy)
                self._clamp_node(cn)

                self.nodes.append(cn)

                # 更新 _counter 防撞 id
                nid = node.id
                if nid.startswith("w"):
                    try:
                        max_num = max(max_num, int(nid[1:]))
                    except ValueError:
                        pass

            Node._counter = max_num
            self.inspector.show_props(None)
            self.refresh_code()
            log.info("导入成功: %s (%d 个节点)", path, len(self.nodes))
            popup.dismiss()

        btn_load.bind(on_release=do_load)
        btn_cancel.bind(on_release=popup.dismiss)
        popup.open()

    # ---------- KV ----------
    def refresh_code(self):
        # 【API 事实 3.4】外层是类规则 `<XXX>:`，XXX 由 self.root_class_name
        # 决定（用户在 Inspector 无选中时改）。用户 py 里写
        # `class XXX(FloatLayout):` 对应。
        lines = [f"<{self.root_class_name}>:"]
        for n in self.nodes:
            lines.append(n.node.to_kv(1))
        self.inspector.set_code("\n".join(lines))
