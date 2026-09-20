import logging
import sys
import json
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional
from contextvars import ContextVar

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Context variables for automatic log correlation/tracing
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
tenant_id_var: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)
job_id_var: ContextVar[Optional[str]] = ContextVar("job_id", default=None)


class JsonFormatter(logging.Formatter):
    """
    JSON formatter that structures all log records as queryable JSON,
    incorporating context correlation variables (request_id, tenant_id, job_id).
    Perfect for production log ingestion engines (Elasticsearch, Datadog, Splunk).
    """
    def format(self, record: logging.LogRecord) -> str:
        # Core structured payload
        log_data = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Automatic Context Propagation
        req_id = request_id_var.get()
        if req_id:
            log_data["request_id"] = req_id

        ten_id = tenant_id_var.get()
        if ten_id:
            log_data["tenant_id"] = ten_id

        j_id = job_id_var.get()
        if j_id:
            log_data["job_id"] = j_id

        # Merge any explicit "extra" fields passed to the log call
        for field in ["event", "status", "job_type", "error"]:
            if hasattr(record, field):
                log_data[field] = getattr(record, field)

        # Include exception tracebacks if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """
    Highly readable, clean, and colorful plain-text formatter designed for
    developers reading console outputs locally during terminal runs.
    """
    # Color codes for terminal outputs
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[41m",  # Red background
        "RESET": "\033[0m"
    }

    def format(self, record: logging.LogRecord) -> str:
        level_color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset_color = self.COLORS["RESET"]
        
        # Retrieve context correlation variables if present
        req_id = request_id_var.get()
        j_id = job_id_var.get()
        ten_id = tenant_id_var.get()
        
        context_str = ""
        if req_id or j_id or ten_id:
            parts = []
            if ten_id:
                parts.append(f"tenant={ten_id}")
            if req_id:
                parts.append(f"request={req_id[:8]}")
            if j_id:
                parts.append(f"job={j_id[:8]}")
            context_str = f" [{', '.join(parts)}]"
            
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        log_line = f"{timestamp} - {level_color}{record.levelname:<8}{reset_color} - {record.name:<18} - {record.getMessage()}{context_str}"
        
        if record.exc_info:
            log_line += f"\n{self.formatException(record.exc_info)}"
            
        return log_line


def get_logger(
    name: str,
    log_file: Optional[str] = None,
    level: str = "INFO"
) -> logging.Logger:
    logger = logging.getLogger(name)
    
    if logger.hasHandlers():
        return logger
    
    logger.setLevel(level)
    
    # console uses colorful clean text formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(ConsoleFormatter())
    logger.addHandler(console_handler)
    
    if log_file is None:
        log_file = f"{name.split('.')[-1]}.log"
    
    try:
        log_path = LOG_DIR / log_file
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        # file log retains structured JSON
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)
    except Exception as e:
        logger.error(f"Failed to setup file handler: {e}")
    
    return logger
