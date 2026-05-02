"""
Shared fixtures. Forces Qt's offscreen platform so tests run headless in CI.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
