"""日志基础设施：每个模块独立日志文件，主程序额外输出到控制台。

【日志格式规范·v0.0.6 起】
    [等级    ][年/月/日-时:分:秒][line:行号]消息

    例：
    [INFO   ][2026/10/01-14:09:35][line:47]KVEditor 初始化完成
    [DEBUG  ][2026/10/01-14:09:35][line:52]end_drag 入口 kind=Button
    [WARNING][2026/10/01-14:09:35][line:88]set_size 非法值 axis=...

    等级统一 7 字符宽度（%(levelname)-7s），视觉对齐。

【行号怎么来的】
    logging 的 %(lineno)d = 【调用 log.xxx() 那一行】的行号。
    因此：绝不要用装饰器包住 logger 调用——会把行号带偏到装饰器
    内部去。本项目【不使用】log_call 装饰器。
"""
import logging
import os
from logging.handlers import RotatingFileHandler

# logs/ 位于项目根目录
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_FORMAT = "[%(levelname)-7s][%(asctime)s][line:%(lineno)d]%(message)s"
_DATE = "%Y/%m/%d-%H:%M:%S"

_configured = set()


def get_logger(name: str) -> logging.Logger:
    """模块 logger：写入 logs/<name>.log，不向 root 冒泡。

    ==========
    用于：
        给每个业务模块（editor / canvas / palette / ...）取一个专属
        logger，日志落到 logs/<name>.log。
    输入：
        A：name: str — 模块名，如 "editor"、"canvas"
    输出：
        A：logging.Logger — 配置好的 logger 实例（幂等，同名只配一次）
    ==========
    """
    full = f"kv_ide.{name}"
    logger = logging.getLogger(full)
    if full in _configured:
        return logger
    _configured.add(full)

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    fh = RotatingFileHandler(
        os.path.join(LOG_DIR, f"{name}.log"),
        maxBytes=512 * 1024, backupCount=3, encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE))
    logger.addHandler(fh)
    return logger


def get_main_logger() -> logging.Logger:
    """主程序 logger：同时写文件 + 控制台。

    ==========
    用于：
        给 main.py 用。日志同时落到 logs/main.log 和 stdout，
        方便在终端直接看启动/退出等关键事件。
    输入：
        无
    输出：
        A：logging.Logger — 配置好的 logger 实例（幂等）
    ==========
    """
    name = "kv_ide.main"
    logger = logging.getLogger(name)
    if name in _configured:
        return logger
    _configured.add(name)

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    fh = RotatingFileHandler(
        os.path.join(LOG_DIR, "main.log"),
        maxBytes=1024 * 1024, backupCount=5, encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE))
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE))
    logger.addHandler(ch)

    return logger
