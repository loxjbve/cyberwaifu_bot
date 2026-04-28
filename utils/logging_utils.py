import logging
from typing import Optional


class ThirdPartyFilter(logging.Filter):
    third_party_libs = {
        "telegram",
        "httpcore",
        "httpx",
        "asyncio",
        "urllib3",
        "requests",
        "aiohttp",
        "websocket",
        "pydantic",
        "json",
        "sqlite3",
        "PIL",
        "openai",
        "matplotlib",
        "matplotlib.font_manager",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        logger_name = record.name.split(".")[0]
        if logger_name in self.third_party_libs:
            return record.levelno >= logging.WARNING
        return True


def _find_handler(root_logger: logging.Logger, handler_type: type[logging.Handler]) -> Optional[logging.Handler]:
    for handler in root_logger.handlers:
        if handler_type is logging.StreamHandler and isinstance(handler, logging.FileHandler):
            continue
        if isinstance(handler, handler_type):
            return handler
    return None


def setup_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    file_handler = _find_handler(root_logger, logging.FileHandler)
    if file_handler is None:
        file_handler = logging.FileHandler("bot.log", encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(ThirdPartyFilter())
        root_logger.addHandler(file_handler)

    stream_handler = _find_handler(root_logger, logging.StreamHandler)
    if stream_handler is None:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(ThirdPartyFilter())
        root_logger.addHandler(stream_handler)


if __name__ == "__main__":
    setup_logging()
