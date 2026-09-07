"""
===========================================================================
统一日志工具 — 带时间戳、级别、模块名的格式化日志
===========================================================================
"""
import logging
import sys
from datetime import datetime


# 日志格式
SIMPLE_FORMAT = "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s"
DETAILED_FORMAT = "%(asctime)s [%(levelname)-5s] %(name)s:%(lineno)d: %(message)s"

# 时间格式
DATE_FORMAT = "%H:%M:%S"


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """获取一个已配置的日志器

    参数:
        name:  模块名 (建议传 __name__)
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)

    使用:
        logger = get_logger(__name__)
        logger.info("模型初始化完成")
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 控制台 handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(SIMPLE_FORMAT, datefmt=DATE_FORMAT)
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False  # 不传播到根日志器

    return logger
