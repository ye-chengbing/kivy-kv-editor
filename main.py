"""KV IDE 入口：只负责组装模块 + 记录主日志。"""
from kivy.app import App
from kivy.core.window import Window
from kivy.uix.floatlayout import FloatLayout

from kv_ide.logger import get_main_logger, LOG_DIR

log = get_main_logger()

Window.size = (1400, 850)


class KVEditorApp(App):
    def build(self):
        log.info("========== KV IDE 启动 ==========")
        log.info("日志目录: %s", LOG_DIR)
        log.info("窗口尺寸: %s", Window.size)
        self.title = "Kivy KV 编辑器"

        log.debug("step 1/3: 创建 root FloatLayout")
        self.root_layout = FloatLayout()

        log.debug("step 2/3: 导入 KVEditor")
        from kv_ide.editor import KVEditor

        log.debug("step 3/3: 挂载 KVEditor")
        self.root_layout.add_widget(KVEditor())

        log.info("UI 构建完成，进入主循环")
        return self.root_layout

    def on_stop(self):
        log.info("========== KV IDE 退出 ==========")


if __name__ == "__main__":
    try:
        KVEditorApp().run()
    except Exception as e:
        log.exception("主循环异常退出: %s", e)
        raise
