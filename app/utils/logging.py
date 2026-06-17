import logging
import sys

import structlog

from app.utils.trace import get_trace_id


def _add_trace_id(logger, method, event_dict):
    event_dict.setdefault("trace_id", get_trace_id())
    return event_dict


def _add_log_level(logger, method, event_dict):
    if "level" not in event_dict:
        event_dict["level"] = method
    return event_dict


class SensitiveFilter:
    SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "smtp_password", "db_password", "authorization"}

    def __call__(self, logger, method, event_dict):
        for key in list(event_dict.keys()):
            lower_key = key.lower()
            if any(s in lower_key for s in self.SENSITIVE_KEYS):
                event_dict[key] = "***REDACTED***"
        return event_dict


def setup_logging(log_level: str = "INFO"):
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_log_level,
            _add_trace_id,
            SensitiveFilter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__):
    return structlog.get_logger(name)
