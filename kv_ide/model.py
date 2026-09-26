"""Node：纯数据模型，不依赖任何 UI。"""
from kivy.metrics import dp
from .logger import get_logger

log = get_logger("model")


class Node:
    _counter = 0

    @classmethod
    def new_id(cls):
        cls._counter += 1
        return f"w{cls._counter}"

    def __init__(self, kind, **props):
        self.id = Node.new_id()          # 走 new_id()，方便将来换规则
        self.kind = kind
        self.props = {}
        self.children = []

        if kind in ("Button", "Label", "TextInput", "ToggleButton"):
            self.props["text"] = kind
        if kind in ("BoxLayout", "GridLayout"):
            self.props["orientation"] = "vertical"
        self.props["size_hint"] = (None, None)
        self.props["size"] = (float(dp(120)), float(dp(40)))
        self.props["pos_hint"] = {"center_x": 0.5, "center_y": 0.5}
        self.props.update(props)

        log.debug("Node 创建 id=%s kind=%s props=%s",
                  self.id, kind, list(self.props.keys()))

    def to_kv(self, indent=0):
        pad = "    " * indent
        lines = [f"{pad}{self.kind}:"]     # 去掉尖括号
        for k, val in self.props.items():
            lines.append(f"{pad}    {k}: {self._fmt(val)}")
        for c in self.children:
            lines.append(c.to_kv(indent + 1))
        return "\n".join(lines)

    @staticmethod
    def _fmt(val):
        if isinstance(val, str):
            return f"'{val}'"
        if isinstance(val, dict):
            inner = ", ".join(f"'{k}': {Node._fmt(v)}" for k, v in val.items())
            return "{" + inner + "}"
        if isinstance(val, (tuple, list)):
            # KV 里 tuple 写成 `120, 40`，不带括号
            return ", ".join(Node._fmt(v) for v in val)
        if isinstance(val, float) and val.is_integer():
            # 120.0 → 120；0.5 天然 is_integer()==False，安全
            return str(int(val))
        return str(val)
