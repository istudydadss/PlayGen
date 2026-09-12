"""业务接口过滤器 - 多层过滤 + 评分模型"""
import re
import logging
from urllib.parse import urlparse
from typing import Optional
from collector.models import NetworkEvent

logger = logging.getLogger(__name__)

# 静态资源后缀
STATIC_SUFFIXES = {
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".webm",
    ".webp", ".avif", ".map", ".txt", ".xml", ".pdf",
}

# 非业务资源类型
NON_BUSINESS_RESOURCE_TYPES = {"stylesheet", "image", "font", "media", "script"}

# 已知埋点/监控域名关键词
TRACKER_DOMAIN_KEYWORDS = {
    "tracker", "analytics", "beacon", "collect", "log", "monitor",
    "telemetry", "sentry", "bugsnag", "datadog", "newrelic",
    "google-analytics", "googletagmanager", "facebook", "doubleclick",
}

# 心跳/监控路径关键词
HEARTBEAT_PATH_KEYWORDS = {
    "/heartbeat", "/health", "/ping", "/alive", "/ready",
    "/polling", "/long-poll", "/event-stream",
}

# 业务关键词（用于评分，可配置）
DEFAULT_BUSINESS_KEYWORDS = {
    "user", "order", "product", "cart", "payment", "login", "logout",
    "register", "auth", "token", "api", "data", "list", "detail",
    "create", "update", "delete", "search", "query", "info", "config",
    "admin", "manage", "report", "dashboard", "profile", "account",
    "item", "category", "comment", "review", "address", "shipping",
}


class TrafficFilter:
    """
    多层业务接口过滤器
    按文档 5.4 节实现：资源类型 -> 域名 -> 路径 -> 心跳/埋点 -> 评分
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

        # 域名配置
        domains = self.config.get("domains", {})
        self.include_domains: set = set(domains.get("include", []))
        self.exclude_domains: set = set(domains.get("exclude", []))

        # 过滤规则
        filters = self.config.get("filters", {})
        self.exclude_paths: list = filters.get("exclude_paths", [])
        self.exclude_suffixes: set = set(filters.get("exclude_suffixes", STATIC_SUFFIXES))
        self.exclude_content_types: list = filters.get("exclude_content_types", [])

        # 评分配置
        scoring = self.config.get("scoring", {})
        self.scores = {
            "json_response": scoring.get("json_response", 20),
            "write_method": scoring.get("write_method", 15),
            "business_keyword": scoring.get("business_keyword", 20),
            "temporal_proximity": scoring.get("temporal_proximity", 15),
            "success_structure": scoring.get("success_structure", 15),
            "static_resource": scoring.get("static_resource", -100),
            "known_tracker": scoring.get("known_tracker", -80),
            "heartbeat": scoring.get("heartbeat", -50),
        }

        # 阈值
        self.business_threshold = self.config.get("business_threshold", 10)

        # 业务关键词
        self.business_keywords = set(
            self.config.get("business_keywords", DEFAULT_BUSINESS_KEYWORDS)
        )

    def filter_and_score(self, events: list[NetworkEvent]) -> list[dict]:
        """
        过滤并评分所有网络事件
        返回: [{"event": NetworkEvent, "is_business": bool, "score": float, "reasons": list}]
        """
        results = []
        for event in events:
            result = self._evaluate_event(event)
            results.append(result)
        return results

    def _evaluate_event(self, event: NetworkEvent) -> dict:
        """评估单个网络事件"""
        reasons = []
        score = 0.0
        is_excluded = False

        url = event.request.url
        parsed = urlparse(url)
        host = parsed.hostname or ""
        path = parsed.path.lower()
        resource_type = event.request.resource_type

        # === 第一层：资源类型过滤 ===
        if resource_type in NON_BUSINESS_RESOURCE_TYPES:
            score += self.scores["static_resource"]
            reasons.append(f"静态资源类型: {resource_type}")
            is_excluded = True

        # === 第二层：文件后缀过滤 ===
        suffix = self._get_path_suffix(path)
        if suffix in self.exclude_suffixes:
            score += self.scores["static_resource"]
            reasons.append(f"静态文件后缀: {suffix}")
            is_excluded = True

        # === 第三层：域名过滤 ===
        if self.include_domains:
            if not any(host.endswith(d) for d in self.include_domains):
                score -= 30
                reasons.append(f"不在域名白名单: {host}")
                is_excluded = True

        if self.exclude_domains:
            if any(host.endswith(d) for d in self.exclude_domains):
                score += self.scores["known_tracker"]
                reasons.append(f"在排除域名列表: {host}")
                is_excluded = True

        # === 第四层：路径过滤 ===
        for exclude_path in self.exclude_paths:
            if exclude_path in path:
                score -= 30
                reasons.append(f"排除路径匹配: {exclude_path}")
                is_excluded = True

        # === 第五层：心跳/埋点识别 ===
        for keyword in TRACKER_DOMAIN_KEYWORDS:
            if keyword in host.lower():
                score += self.scores["known_tracker"]
                reasons.append(f"疑似埋点域名: {keyword}")
                is_excluded = True
                break

        for keyword in HEARTBEAT_PATH_KEYWORDS:
            if keyword in path:
                score += self.scores["heartbeat"]
                reasons.append(f"疑似心跳路径: {keyword}")
                is_excluded = True
                break

        # === 第六层：业务评分 ===
        if not is_excluded:
            # JSON 响应加分
            if event.response:
                content_type = event.response.content_type or ""
                if "json" in content_type:
                    score += self.scores["json_response"]
                    reasons.append("JSON 响应")

                # 标准成功结构加分
                if event.response.body and isinstance(event.response.body, dict):
                    body = event.response.body
                    if any(k in body for k in ["code", "success", "status", "message", "data"]):
                        score += self.scores["success_structure"]
                        reasons.append("标准业务响应结构")

            # 写操作加分
            if event.request.method in ("POST", "PUT", "PATCH", "DELETE"):
                score += self.scores["write_method"]
                reasons.append(f"写操作: {event.request.method}")

            # 业务关键词加分
            path_parts = set(re.findall(r'[a-z]+', path))
            matched_keywords = path_parts & self.business_keywords
            if matched_keywords:
                score += self.scores["business_keyword"]
                reasons.append(f"业务关键词: {', '.join(matched_keywords)}")

        # 判断是否为业务接口
        is_business = (not is_excluded) and (score >= self.business_threshold)

        return {
            "event": event,
            "is_business": is_business,
            "score": score,
            "reasons": reasons,
        }

    def _get_path_suffix(self, path: str) -> str:
        """获取路径后缀"""
        dot_idx = path.rfind(".")
        if dot_idx > 0:
            suffix = path[dot_idx:].lower()
            # 排除查询参数
            q_idx = suffix.find("?")
            if q_idx > 0:
                suffix = suffix[:q_idx]
            return suffix
        return ""
