"""接口去重 - 基于指纹归并"""
import logging
from typing import Optional
from collector.models import NetworkEvent
from analyzer.normalizer import UrlNormalizer

logger = logging.getLogger(__name__)


class InterfaceDeduplicator:
    """
    接口去重器
    基于归一化后的指纹将相同接口归并为一个接口定义
    """

    def __init__(self, normalizer: Optional[UrlNormalizer] = None):
        self.normalizer = normalizer or UrlNormalizer()
        # fingerprint -> 接口定义
        self.interfaces: dict[str, dict] = {}

    def deduplicate(self, events: list[NetworkEvent], base_url: Optional[str] = None) -> dict:
        """
        对网络事件进行去重归并
        返回: {
            "interfaces": {fingerprint: interface_def},
            "event_mapping": {event_index: fingerprint},
        }
        """
        event_mapping = {}

        for idx, event in enumerate(events):
            # 归一化
            norm_result = self.normalizer.normalize_url(event.request.url, base_url)
            normalized_path = norm_result["normalized_path"]
            query_keys = norm_result["query_keys"]

            # 计算请求 Schema 哈希
            req_schema_hash = self.normalizer.compute_request_schema_hash(event.request.body)

            # 计算指纹
            fingerprint = self.normalizer.compute_fingerprint(
                method=event.request.method,
                normalized_path=normalized_path,
                query_keys=query_keys,
                request_schema_hash=req_schema_hash,
            )

            # 归并
            if fingerprint not in self.interfaces:
                self.interfaces[fingerprint] = {
                    "fingerprint": fingerprint,
                    "method": event.request.method,
                    "normalized_path": normalized_path,
                    "query_keys": query_keys,
                    "base_url": norm_result["base_url"],
                    "sample_count": 0,
                    "first_event_index": idx,
                    "events": [],
                }

            self.interfaces[fingerprint]["sample_count"] += 1
            self.interfaces[fingerprint]["events"].append(idx)
            event_mapping[idx] = fingerprint

        logger.info(
            f"去重完成: {len(events)} 个请求 -> {len(self.interfaces)} 个接口"
        )

        return {
            "interfaces": self.interfaces,
            "event_mapping": event_mapping,
        }

    def get_interface(self, fingerprint: str) -> Optional[dict]:
        """获取接口定义"""
        return self.interfaces.get(fingerprint)

    def reset(self):
        """重置"""
        self.interfaces.clear()
