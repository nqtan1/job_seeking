"""pdfium is not thread-safe: every module that opens a PDF with it takes this one lock."""

import threading

lock = threading.Lock()
