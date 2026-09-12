"""Playwright 采集器模块"""
from collector.recorder import PlaywrightRecorder
from collector.network_interceptor import NetworkInterceptor
from collector.models import CapturedRequest, CapturedResponse, PageOperation

__all__ = ["PlaywrightRecorder", "NetworkInterceptor", "CapturedRequest", "CapturedResponse", "PageOperation"]
