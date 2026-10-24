"""KV IDE 入口：开始页 + 编辑器。"""
from kivy.app import App
from kivy.core.window import Window
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager, Screen

from kv_editor_src.logger import get_main_logger, LOG_DIR

log = get_main_logger()

Window.size = (1400, 850)


class StartScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        layout = BoxLayout(orientation="vertical", padding=100, spacing=20)
        layout.add_widget(Label(text="[b]Select Root Layout[/b]", markup=True,
                                font_size="24sp", size_hint_y=None, height=60))

        for root_type in ("FloatLayout", "RelativeLayout", "ScatterLayout"):
            btn = Button(text=root_type, size_hint_y=None, height=60)
            btn.bind(on_release=lambda btn, rt=root_type: self.go_editor(rt))
            layout.add_widget(btn)

        layout.add_widget(Label(text="More layouts coming soon...",
                                color=(0.6, 0.6, 0.6, 1),
                                size_hint_y=None, height=40))
        self.add_widget(layout)

    def go_editor(self, root_type):
        log.info("用户选择根布局: %s", root_type)
        App.get_running_app().start_editor(root_type)


class EditorScreen(Screen):
    pass


class KVEditorApp(App):
    def build(self):
        log.info("========== KV IDE 启动 ==========")
        log.info("日志目录: %s", LOG_DIR)
        log.info("窗口尺寸: %s", Window.size)
        self.title = "Kivy KV Editor"

        self.root_layout = FloatLayout()
        self.sm = ScreenManager()
        self.sm.add_widget(StartScreen(name="start"))
        self.root_layout.add_widget(self.sm)
        return self.root_layout

    def start_editor(self, root_type):
        from kv_editor_src.editor import KVEditor

        if self.sm.has_screen("editor"):
            old = self.sm.get_screen("editor")
            self.sm.remove_widget(old)

        editor_screen = EditorScreen(name="editor")
        editor_screen.add_widget(KVEditor(root_type=root_type))
        self.sm.add_widget(editor_screen)
        self.sm.current = "editor"

    def on_stop(self):
        log.info("========== KV IDE 退出 ==========")


if __name__ == "__main__":
    try:
        KVEditorApp().run()
    except Exception as e:
        log.exception("主循环异常退出: %s", e)
        raise
