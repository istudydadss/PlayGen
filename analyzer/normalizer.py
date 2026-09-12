"""URL 归一化 - Path 变量化、Query 排序、指纹计算"""
import re
import hashlib
import json
import logging
from urllib.parse import urlparse, urlencode, parse_qs
from typing import Optional

logger = logging.getLogger(__name__)

# UUID 正则
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

# 纯数字
NUMERIC_PATTERN = re.compile(r'^\d+$')

# 日期格式
DATE_PATTERNS = [
    re.compile(r'^\d{4}-\d{2}-\d{2}$'),  # 2024-01-01
    re.compile(r'^\d{4}/\d{2}/\d{2}$'),  # 2024/01/01
    re.compile(r'^\d{8}$'),               # 20240101
    re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'),  # ISO 8601
]

# 动态 Query 参数名（应忽略）
DYNAMIC_QUERY_PARAMS = {
    "_", "t", "timestamp", "nonce", "rand", "random", "callback",
    "sign", "signature", "_t", "v", "version",
}


class UrlNormalizer:
    """
    URL 归一化引擎
    - Host 映射为 Base URL
    - 数字 ID / UUID / 日期转 Path 变量
    - Query 参数排序，忽略动态参数
    - 计算接口指纹
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.dynamic_query_params = set(
            self.config.get("dynamic_query_params", DYNAMIC_QUERY_PARAMS)
        )

    def normalize_url(self, url: str, base_url: Optional[str] = None) -> dict:
        """
        归一化 URL
        返回: {
            "normalized_path": str,
            "base_url": str,
            "query_keys": list,
            "path_params": dict,
        }
        """
        parsed = urlparse(url)
        host = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else ""
        path = parsed.path

        # 解析路径段
        segments = [s for s in path.split("/") if s]
        normalized_segments = []
        path_params = {}

        for i, segment in enumerate(segments):
            param_name = self._detect_path_param(segment, segments, i)
            if param_name:
                normalized_segments.append(f"{{{param_name}}}")
                path_params[param_name] = segment
            else:
                normalized_segments.append(segment)

        normalized_path = "/" + "/".join(normalized_segments)

        # 处理 Query 参数
        query_params = parse_qs(parsed.query)
        # 过滤动态参数
        filtered_query = {
            k: v for k, v in query_params.items()
            if k.lower() not in self.dynamic_query_params
        }
        # 按名称排序
        query_keys = sorted(filtered_query.keys())

        # 确定 base_url
        result_base_url = base_url or host

        return {
            "normalized_path": normalized_path,
            "base_url": result_base_url,
            "query_keys": query_keys,
            "path_params": path_params,
        }

    def compute_fingerprint(
        self,
        method: str,
        normalized_path: str,
        query_keys: list[str],
        request_schema_hash: Optional[str] = None,
    ) -> str:
        """
        计算接口指纹
        hash(method + normalized_path + query_key_set + request_schema_hash)
        """
        parts = [
            method.upper(),
            normalized_path,
            ",".join(sorted(query_keys)),
            request_schema_hash or "",
        ]
        fingerprint_str = "|".join(parts)
        return hashlib.sha256(fingerprint_str.encode("utf-8")).hexdigest()[:32]

    def compute_request_schema_hash(self, body: Optional[dict]) -> Optional[str]:
        """计算请求体 Schema 哈希"""
        if not body:
            return None
        schema = self._extract_schema(body)
        schema_json = json.dumps(schema, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(schema_json.encode("utf-8")).hexdigest()[:16]

    def _detect_path_param(self, segment: str, segments: list, index: int) -> Optional[str]:
        """检测路径段是否为动态参数"""
        # UUID
        if UUID_PATTERN.match(segment):
            return "id"

        # 纯数字（可能是 ID）
        if NUMERIC_PATTERN.match(segment):
            # 尝试从上一段推断名称
            if index > 0:
                prev = segments[index - 1].lower()
                # 常见复数名词 -> 单数参数名
                if prev.endswith("ies"):
                    return prev[:-3] + "Id"
                elif prev.endswith("ses") or prev.endswith("xes"):
                    return prev[:-2] + "Id"
                elif prev.endswith("s"):
                    return prev[:-1] + "Id"
            return "id"

        # 日期格式
        for pattern in DATE_PATTERNS:
            if pattern.match(segment):
                return "date"

        return None

    def _extract_schema(self, data) -> dict:
        """从数据中提取结构 Schema"""
        if isinstance(data, dict):
            properties = {}
            for key, value in sorted(data.items()):
                properties[key] = self._extract_schema(value)
            return {"type": "object", "properties": properties}
        elif isinstance(data, list):
            if data:
                return {"type": "array", "items": self._extract_schema(data[0])}
            return {"type": "array", "items": {}}
        elif isinstance(data, bool):
            return {"type": "boolean"}
        elif isinstance(data, int):
            return {"type": "integer"}
        elif isinstance(data, float):
            return {"type": "number"}
        elif data is None:
            return {"type": "null"}
        else:
            return {"type": "string"}
