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

    # ---------- KV ----------
    def to_kv(self, indent=0):
        # ========================================================
        # |一些烦人的东西|
        # ====================
        # 坑名：
        #     KV 里 `<Button>:` 是类规则，`Button:` 是实例
        # 证实方式：
        #     https://stackoverflow.com/questions/52689903/
        #     原文："mybutton: provides a rule for how to build Word
        #            objects. If you change mybutton: to Button: in
        #            your .kv file, then your call to Word() in build()
        #            will create a Word instance with a button already
        #            in it."
        #     `<Button>:` 给类加全局规则，多个会互相覆盖；
        #     `Button:` 才是在父级里放实例。这是语义修正。
        # ！！！绝对绝对绝对不要动它，现在能稳定跑是它对我们的宽容！！！
        # ====================
        # ========================================================
        pad = "    " * indent
        lines = [f"{pad}{self.kind}:"]
        # id 是 Kivy 标准属性，写在控件类型行下方、其它属性之前。
        # 用户在 py 里通过 self.ids.<id> 访问控件。
        lines.append(f"{pad}    id: {self.id}")
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

    # ---------- JSON ----------
    def to_json(self):
        """Node → JSON 可序列化 dict。

        ==========
        用于：
            导出时把节点树转成 JSON 结构。
        输入：
            A：self: Node
        输出：
            A：dict — {"id", "type", "props", "children"}
        ==========
        """
        return {
            "id": self.id,
            "type": self.kind,
            "props": self._props_to_json(self.props),
            "children": [c.to_json() for c in self.children],
        }

    @classmethod
    def from_json(cls, data):
        """JSON dict → Node。

        ==========
        用于：
            导入时把 JSON 结构转回节点树。
        输入：
            A：data: dict — {"id", "type", "props", "children"}
        输出：
            A：Node
        ==========
        """
        node = cls(data["type"])
        node.id = data["id"]
        node.props = cls._props_from_json(data["props"])
        node.children = [cls.from_json(c) for c in data["children"]]
        return node

    @staticmethod
    def _props_to_json(props):
        """tuple → list（JSON 没有 tuple）。"""
        result = {}
        for k, v in props.items():
            if isinstance(v, tuple):
                v = list(v)
            result[k] = v
        return result

    @staticmethod
    def _props_from_json(props):
        """list → tuple（读 JSON 时坐标统一转 tuple）。"""
        result = {}
        for k, v in props.items():
            if isinstance(v, list):
                v = tuple(v)
            result[k] = v
        return result
