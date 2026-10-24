# 这个文件用ai进行了大面积重构
# 经测试功能皆正常
# 但我还是不放心，对照旧版本修修补补了一下
# 以后可能在补功能时又大改
# 现在评估出的代码质量比较中肯，就先这样吧
# 好累

import json
import os
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scatterlayout import ScatterLayout

from .logger import get_logger
from .model import Node
from .palette import Palette
from .canvas import Canvas, CanvasNode
from .inspector import Inspector

log = get_logger("editor")

_CTRL_MODS = {"ctrl", "lctrl", "rctrl"}
# |一些烦人的东西|
# ====================
# modifiers 命名在不同平台/后端下不稳定
# Kivy 源码 keycodes 表同时有 'lctrl': 305 和 'rctrl': 306：
# https://kivy.org/doc/stable/api-kivy.core.window.html
# StackOverflow 2016 年实测给的是 'lctrl'：
# https://stackoverflow.com/questions/35669747/
# 当前环境实测给 'ctrl'，但不保证换平台也给 'ctrl'
# 三种全接受。


class KVEditor(BoxLayout):
    selected = ObjectProperty(None, allownone=True)
    ghost = ObjectProperty(None, allownone=True)

    def __init__(self, root_type="FloatLayout", **kw):
        kw.setdefault("size_hint", (1, 1))
        kw.setdefault("pos_hint", {"x": 0, "y": 0})
        super().__init__(orientation="horizontal", **kw)

        self.nodes = []
        self._drag_kind = None
        self.root_type = root_type
        self.root_class_name = "MyRoot"

        self._build_ui()
        self.canvas_widget.set_root_layout(self.root_type)

        self.inspector.show_props(None)
        log.info("KVEditor 初始化完成，Root: %s", self.root_type)

        from kivy.clock import Clock
        Clock.schedule_once(self._log_layout, 0.5)
        Window.bind(on_key_down=self._on_key_down)

        self.canvas_widget.bind(size=self._on_canvas_resize)

        if isinstance(self.canvas_widget.user_root, ScatterLayout):
            self.canvas_widget.user_root.bind(
                rotation=self._check_scatter_state,
                scale=self._check_scatter_state,
            )

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

        self.btn_reset_scatter = Button(text="Reset Scatter",
                                        size_hint_x=None, width=dp(100))
        self.btn_reset_scatter.bind(on_release=self.reset_scatter)
        if self.root_type != "ScatterLayout":
            self.btn_reset_scatter.disabled = True
            self.btn_reset_scatter.opacity = 0
        toolbar.add_widget(self.btn_reset_scatter)

        center.add_widget(toolbar)

        self.canvas_widget = Canvas(editor=self)
        center.add_widget(self.canvas_widget)
        self.add_widget(center)

        self.inspector = Inspector(self)
        self.add_widget(self.inspector)

    def _log_layout(self, *args):
        def box(w):
            return f"({w.x:.0f},{w.y:.0f}) {w.width:.0f}x{w.height:.0f}"
        log.info("=== 布局检查（窗口 %sx%s）===", Window.width, Window.height)
        log.info("  KVEditor  %s", box(self))
        log.info("  canvas    %s", box(self.canvas_widget))
        if self.canvas_widget.user_root:
            log.info("  user_root %s (type=%s)",
                     box(self.canvas_widget.user_root), self.root_type)


    def clamp_position(self, x, y, w, h):
        cw = self.canvas_widget
        if self.root_type == "FloatLayout":
            min_x = cw.x
            max_x = cw.x + cw.width - w
            min_y = cw.y
            max_y = cw.y + cw.height - h
        else:
            min_x = 0
            max_x = cw.width - w
            min_y = 0
            max_y = cw.height - h
        return max(min_x, min(x, max_x)), max(min_y, min(y, max_y))

    def _on_canvas_resize(self, *args):
        """Canvas 尺寸变化（窗口最大化/恢复）时，重新 clamp 所有节点。"""
        if not self.nodes:
            return
        
        log.info("Canvas resize 发生变化，重新 clamp %d 个节点", len(self.nodes))
        cw = self.canvas_widget
        for cn in self.nodes:
            ph = cn.node.props.get("pos_hint", {})
            rx = ph.get("center_x", 0.5)
            ry = ph.get("center_y", 0.5)

            if self.root_type == "FloatLayout":
                cn.center = (cw.x + rx * cw.width, cw.y + ry * cw.height)
            else:
                cn.center = (rx * cw.width, ry * cw.height)

    def sync_pos_hint(self, cn):
        cw = self.canvas_widget
        if not cw or cw.width <= 0 or cw.height <= 0:
            return

        if self.root_type == "FloatLayout":
            lx = cn.center_x - cw.x
            ly = cn.center_y - cw.y
        else:
            lx = cn.center_x
            ly = cn.center_y

        cn.node.props["pos_hint"] = {
            "center_x": round(lx / cw.width, 3),
            "center_y": round(ly / cw.height, 3),
        }


    def _check_scatter_state(self, *args):
        scatter = self.canvas_widget.user_root
        if not isinstance(scatter, ScatterLayout):
            return
        is_locked = (scatter.rotation != 0 or scatter.scale != 1.0)
        if is_locked:
            self.btn_reset_scatter.disabled = False
            self.btn_reset_scatter.opacity = 1
            self.inspector.lock_ui(
                "Scatter is transformed.\nPress Ctrl+Shift+Q to reset.")
        else:
            self.btn_reset_scatter.disabled = True
            self.btn_reset_scatter.opacity = 0
            self.inspector.unlock_ui()

    def reset_scatter(self, *args):
        scatter = self.canvas_widget.user_root
        if isinstance(scatter, ScatterLayout):
            scatter.rotation = 0
            scatter.scale = 1.0
            self._check_scatter_state()







    # 雷霆快捷键

    # 直接写def _on_key_down(self, window, key, keycode, codepoint, modifiers)就行，别问，这样才能用
    def _on_key_down(self, window, key, keycode, codepoint, modifiers):
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
        # ====================
        kb = getattr(window, "_system_keyboard", None)
        focus = getattr(kb, "widget", None) if kb else None
        if isinstance(focus, TextInput):
            return False

        # Kivy 里 Delete 键的 keycode 是 127，Backspace 是 8
        # Kivy 源码 textinput.py 的 interesting_keys：
        # https://github.com/kivy/kivy/blob/master/kivy/uix/textinput.py
        # 原文：`{ 8: 'backspace', 13: 'enter', 127: 'del', ... }`
        # 文档：https://kivy.readthedocs.io/en/master/api-kivy.uix.textinput.html
        # "Del — Delete the selection of character after the cursor"
        mods = set(modifiers)

        if key == ord('q') and ('ctrl' in mods or _CTRL_MODS & mods) \
                and 'shift' in mods:
            if self.root_type == "ScatterLayout":
                self.reset_scatter()
                return True
            return False

        if key != 127:
            return False
        if not (_CTRL_MODS & mods):
            return False
        self.delete_selected()
        return True






    # 拖拽
    def _overlay(self):
        from kivy.app import App
        return getattr(App.get_running_app(), "root_layout", None)

    def start_drag(self, kind, *args):
        mx, my = Window.mouse_pos
        overlay = self._overlay()
        if overlay is None:
            return
        self._drag_kind = kind

        ghost = Button(text=f"+ {kind}",
                       color=(1, 1, 1, 1), font_size="13sp",
                       size_hint=(None, None), size=(dp(120), dp(40)))
        ghost.background_normal = ""
        ghost.background_color = (0.25, 0.55, 0.85, 0.85)
        ghost.opacity = 0.6

        overlay.add_widget(ghost)
        ghost.center = (mx, my)
        self.ghost = ghost

    def update_drag(self, *args):
        if self.ghost:
            self.ghost.center = Window.mouse_pos

    def end_drag(self, kind, *args):
        overlay = self._overlay()
        if self.ghost and overlay:
            overlay.remove_widget(self.ghost)
        self.ghost = None

        mx, my = Window.mouse_pos
        cw = self.canvas_widget

        if cw.x <= mx <= cw.x + cw.width and cw.y <= my <= cw.y + cw.height:
            self.create_node(kind, window_pos=(mx, my))







    # 节点管理部分
    def create_node(self, kind, window_pos):
        # ========================================================
        # 【坐标语义·别动】节点挂在 canvas（FloatLayout）上
        # 但 FloatLayout 不转换子控件坐标 —— cn.center 就是[窗口坐标]。
        # 所以这里直接 cn.center = (mx, my)，不要写成 (mx - cw.x, ...)。
        # 证据：https://kivy.org/doc/stable-2.3.0/api-kivy.uix.relativelayout.html#coordinate-systems
        # ========================================================
        node = Node(kind)
        cn = CanvasNode(node, self)
        cw = self.canvas_widget
        mx, my = window_pos

        if self.root_type == "FloatLayout":
            cn.center = (mx, my)
            cn.x, cn.y = self.clamp_position(cn.x, cn.y, cn.width, cn.height)
            cw.user_root.add_widget(cn)

        elif self.root_type in ("RelativeLayout", "ScatterLayout"):
            local_x = mx - cw.x
            local_y = my - cw.y
            cn.center = (local_x, local_y)
            cn.x, cn.y = self.clamp_position(cn.x, cn.y, cn.width, cn.height)
            cw.user_root.add_widget(cn)

        node.props["size"] = (cn.width, cn.height)
        self.nodes.append(cn)
        self.select(cn)
        self.sync_pos_hint(cn)
        self.refresh_code()

    def select(self, cn):
        if self.selected and self.selected is not cn:
            self.selected.is_selected = False
        self.selected = cn
        cn.is_selected = True
        self.inspector.show_props(cn)

    def delete_selected(self, *a):
        if not self.selected:
            return
        user_root = self.canvas_widget.user_root
        if self.selected.parent is user_root:
            user_root.remove_widget(self.selected)
        if self.selected in self.nodes:
            self.nodes.remove(self.selected)
        self.selected = None
        self.inspector.show_props(None)
        self.refresh_code()

    # 其实我觉得这个clear可以去掉
    # 也没见哪个编辑器自带一键清除
    # 不过如果有谁嫌你布局写的丑
    # 你可以用这个一键爆破，因为我觉得UI布局对于一个项目来说还是挺重要的
    def clear_canvas(self, *a):
        user_root = self.canvas_widget.user_root
        if user_root:
            for n in list(self.nodes):
                if n.parent is user_root:
                    user_root.remove_widget(n)
        self.nodes.clear()
        self.selected = None
        self.inspector.show_props(None)
        self.refresh_code()






    # 下面是属性修改部分
    # 我在想要不要单独独立出一个文件写这些
    # 因为如果后面要补齐kv的其他属性要加的东西会很多
    # 都堆在一个类里不太妥
    def set_prop(self, cn, key, value):
        old = cn.node.props.get(key)
        cn.node.props[key] = value
        if key == "text":
            cn.text = value
        log.info("set_prop id=%s %s: %r → %r", cn.node.id, key, old, value)
        self.refresh_code()

    def set_id(self, cn, new_id):
        """修改节点 id。id 是数据层字段，不是 cn.node.props 里的属性。"""
        new_id = new_id.strip()
        if not new_id or cn.node.id == new_id:
            return
        cn.node.id = new_id
        self.refresh_code()
        self.inspector.show_props(cn)

    def set_root_class_name(self, name):
        """修改根节点类名（KV 首行 `<XXX>:` 里的 XXX）。"""
        name = name.strip()
        if not name or name == self.root_class_name:
            return
        self.root_class_name = name
        self.refresh_code()

    def set_size(self, cn, axis, value):
        try:
            v = dp(float(value))
        except ValueError:
            return
        if axis == "width":
            cn.width = v
            cn.node.props["size"] = (v, cn.height)
        else:
            cn.height = v
            cn.node.props["size"] = (cn.width, v)
        cn.node.props["size_hint"] = (None, None)

        self.sync_pos_hint(cn)
        self.refresh_code()
        self.inspector.show_props(cn)

























    # 文件导出导入部分
    # 我觉得已经足够耐用了
    # 以后可以忽略不管它了
    # 除非KV大改或着我要加点啥
    def export_files(self, *a):
        from kivy.uix.popup import Popup
        from kivy.uix.filechooser import FileChooserListView

        content = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        filechooser = FileChooserListView(path=".", dirselect=False)
        content.add_widget(filechooser)

        name_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        name_row.add_widget(Label(text="Filename:", size_hint_x=None, width=dp(90)))
        name_input = TextInput(text="layout", multiline=False)
        name_row.add_widget(name_input)
        content.add_widget(name_row)

        btn_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        btn_save, btn_cancel = Button(text="Save"), Button(text="Cancel")
        btn_row.add_widget(btn_save)
        btn_row.add_widget(btn_cancel)
        content.add_widget(btn_row)

        popup = Popup(title="Export KV + JSON", content=content,
                      size_hint=(0.9, 0.9))

        def do_save(*_):
            fname = name_input.text.strip() or "layout"
            if fname.endswith(".kv"):
                fname = fname[:-3]
            elif fname.endswith(".json"):
                fname = fname[:-5]
            base = os.path.join(filechooser.path, fname)
            try:
                with open(base + ".kv", "w", encoding="utf-8") as f:
                    f.write(self.inspector.code_out.text)
                data = {
                    "version": 1,
                    "root": {
                        "type": self.root_type,
                        "props": {},
                        "children": [n.node.to_json() for n in self.nodes],
                    },
                }
                with open(base + ".json", "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                log.exception("导出失败")
            popup.dismiss()

        btn_save.bind(on_release=do_save)
        btn_cancel.bind(on_release=popup.dismiss)
        popup.open()

    def import_json(self, *a):
        from kivy.uix.popup import Popup
        from kivy.uix.filechooser import FileChooserListView

        content = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        filechooser = FileChooserListView(path=".", filters=["*.json"])
        content.add_widget(filechooser)

        btn_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        btn_load, btn_cancel = Button(text="Load"), Button(text="Cancel")
        btn_row.add_widget(btn_load)
        btn_row.add_widget(btn_cancel)
        content.add_widget(btn_row)

        popup = Popup(title="Import JSON", content=content,
                      size_hint=(0.9, 0.9))
        # ai写的雷霆def套def
        def do_load(*_):
            if not filechooser.selection:
                return
            path = filechooser.selection[0]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                log.exception("导入 JSON 失败: %s", e)
                popup.dismiss()
                return

            if data.get("root", {}).get("type") != self.root_type:
                popup.dismiss()
                return

            self.clear_canvas()
            user_root = self.canvas_widget.user_root
            cw = self.canvas_widget
            max_num = 0

            for child_data in data["root"]["children"]:
                node = Node.from_json(child_data)
                cn = CanvasNode(node, self)

                ph = node.props.get("pos_hint", {})
                rx = ph.get("center_x", 0.5)
                ry = ph.get("center_y", 0.5)

                if self.root_type == "FloatLayout":
                    cn.center = (cw.x + rx * cw.width, cw.y + ry * cw.height)
                else:
                    cn.center = (rx * cw.width, ry * cw.height)

                user_root.add_widget(cn)
                self.nodes.append(cn)

                if node.id.startswith("w"):
                    try:
                        max_num = max(max_num, int(node.id[1:]))
                    except ValueError:
                        pass

            Node._counter = max_num
            self.inspector.show_props(None)
            self.refresh_code()
            popup.dismiss()
        # 雷霆def套def到这里就结束了，而且马上就用上了，不知道何意味
        btn_load.bind(on_release=do_load)
        btn_cancel.bind(on_release=popup.dismiss)
        popup.open()

    def refresh_code(self):
        lines = [f"<{self.root_class_name}>:"]
        for n in self.nodes:
            lines.append(n.node.to_kv(1))
        self.inspector.set_code("\n".join(lines))
