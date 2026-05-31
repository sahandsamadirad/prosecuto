import logging
import sys

import structlog
from structlog.types import Processor


def configure_logging():
    """Configure structlog for JSON output in production, pretty-print in dev."""
    # Common processors for both loggers
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Use JSON output if not a TTY (standard for production/Docker)
    if not sys.stderr.isatty():
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.NOTSET),
        cache_logger_on_first_use=True,
    )

    # Bridge standard logging to structlog if needed (optional)
    # logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
