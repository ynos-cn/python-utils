import logging


def _get_logger():
    log = logging.getLogger("log")
    log.setLevel(logging.INFO)
    return log


# 日志句柄
logger = _get_logger()
