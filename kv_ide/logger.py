"""日志基础设施：每个模块独立日志文件，主程序额外输出到控制台。"""
import logging
import os
from logging.handlers import RotatingFileHandler

# logs/ 位于项目根目录
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_FORMAT = "[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s"
_DATE = "%Y-%m-%d %H:%M:%S"

_configured = set()


def get_logger(name: str) -> logging.Logger:
    """模块 logger：写入 logs/<name>.log，不向 root 冒泡。"""
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
    """主程序 logger：同时写文件 + 控制台。"""
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


def log_call(module_logger):
    """装饰器：记录函数进入/返回/异常。"""
    def deco(fn):
        def wrapper(*a, **kw):
            module_logger.debug("→ %s(%s)", fn.__name__, _fmt_args(a, kw))
            try:
                r = fn(*a, **kw)
                module_logger.debug("← %s 返回 %r", fn.__name__, r)
                return r
            except Exception as e:
                module_logger.exception("✗ %s 抛出异常: %s", fn.__name__, e)
                raise
        return wrapper
    return deco


def _fmt_args(a, kw):
    parts = [repr(x) for x in a[:2]]  # 避免把 touch 对象塞进日志
    parts += [f"{k}={v!r}" for k, v in kw.items()]
    return ", ".join(parts)
