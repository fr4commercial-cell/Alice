# Make cogs a package so imports like 'from cogs.console_logger import logger' work.
# Export logger for convenience.
try:
    from .console_logger import logger  # noqa: F401
except Exception:
    logger = None
