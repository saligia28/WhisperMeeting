"""
WhisperMeeting package entry point.

Provides convenience factories for core services so that both FastAPI
endpoints和命令行工具可以共享同一批依赖。
"""

from .container import build_container

__all__ = ["build_container"]
