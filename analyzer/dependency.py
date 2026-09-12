"""动态参数依赖分析引擎"""
import re
import logging
from typing import Any, Optional
from difflib import SequenceMatcher
from collector.models import NetworkEvent

logger = logging.getLogger(__name__)

# 低信息量值（应排除）
LOW_INFO_VALUES = {"", "true", "false", "null", "0", "1", "yes", "no", "[]", "{}"}
LOW_INFO_MIN_LENGTH = 3


class DependencyAnalyzer:
    """
    动态参数依赖分析器
    检测上游响应值是否被下游请求引用

    按文档 5.7 节和 9.3 节实现：
    1. 展开上游响应 JSON 为 JSONPath-值 集合
    2. 展开下游请求各位置的值
    3. 值匹配 + 常见变换
    4. 排除低信息量值
    5. 评分：值匹配 + 时间顺序 + 字段名相似度 + 唯一性
    6. 输出依赖候选及置信度
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        # 置信度阈值
        self.high_confidence_threshold = self.config.get("high_confidence", 0.8)
        self.medium_confidence_threshold = self.config.get("medium_confidence", 0.5)

    def analyze(self, events: list[NetworkEvent]) -> list[dict]:
        """
        分析网络事件序列中的参数依赖
        返回依赖候选列表，按置信度降序排列
        """
        candidates = []

        # 按时间顺序处理事件
        for i, upstream_event in enumerate(events):
            if not upstream_event.response or not upstream_event.response.body:
                continue
            if not isinstance(upstream_event.response.body, dict):
                continue

            # 展开上游响应为 JSONPath-值 集合
            upstream_values = self._expand_json(
                upstream_event.response.body, prefix="$"
            )

            # 过滤低信息量值
            upstream_values = self._filter_low_info(upstream_values)

            if not upstream_values:
                continue

            # 查找下游请求中的引用
            for j in range(i + 1, len(events)):
                downstream_event = events[j]
                downstream_values = self._expand_request(downstream_event)

                # 匹配值
                matches = self._find_matches(upstream_values, downstream_values)

                for match in matches:
                    candidate = {
                        "source_step_index": i,
                        "source_request_id": upstream_event.request_id,
                        "source_json_path": match["source_path"],
                        "target_step_index": j,
                        "target_request_id": downstream_event.request_id,
                        "target_location": match["target_location"],
                        "matched_value": match["value"],
                        "transform": match.get("transform"),
                        "confidence": self._calculate_confidence(
                            match=match,
                            upstream_event=upstream_event,
                            downstream_event=downstream_event,
                            step_distance=j - i,
                            total_steps=len(events),
                        ),
                    }
                    candidates.append(candidate)

        # 按置信度降序排列
        candidates.sort(key=lambda x: x["confidence"], reverse=True)

        logger.info(f"依赖分析完成: 发现 {len(candidates)} 个依赖候选")
        return candidates

    def _expand_json(self, data: Any, prefix: str = "$") -> list[dict]:
        """
        将 JSON 展开为 JSONPath-值 集合
        [{"path": "$.data.token", "value": "abc123"}, ...]
        """
        results = []

        if isinstance(data, dict):
            for key, value in data.items():
                path = f"{prefix}.{key}"
                if isinstance(value, (dict, list)):
                    results.extend(self._expand_json(value, path))
                else:
                    results.append({"path": path, "value": str(value) if value is not None else "", "key": key})
        elif isinstance(data, list):
            for idx, item in enumerate(data):
                path = f"{prefix}[{idx}]"
                if isinstance(item, (dict, list)):
                    results.extend(self._expand_json(item, path))
                else:
                    results.append({"path": path, "value": str(item) if item is not None else "", "key": str(idx)})

        return results

    def _expand_request(self, event: NetworkEvent) -> list[dict]:
        """
        展开请求的各位置值
        包括: path, query, headers, body
        """
        results = []
        request = event.request

        # Path 参数
        path_parts = request.url.split("/")
        for part in path_parts:
            if part and not part.startswith("http"):
                results.append({
                    "location": f"path.{part}",
                    "value": part,
                    "key": part,
                })

        # Query 参数
        for key, value in request.query_params.items():
            results.append({
                "location": f"query.{key}",
                "value": str(value),
                "key": key,
            })

        # Headers
        for key, value in request.headers.items():
            # 跳过通用 headers
            if key.lower() in ("accept", "accept-language", "user-agent", "content-type",
                               "accept-encoding", "connection", "host", "referer",
                               "origin", "sec-ch-ua", "sec-fetch-dest"):
                continue
            results.append({
                "location": f"header.{key}",
                "value": str(value),
                "key": key,
            })

        # Body
        if request.body and isinstance(request.body, dict):
            body_values = self._expand_json(request.body, prefix="body")
            for bv in body_values:
                results.append({
                    "location": bv["path"],
                    "value": bv["value"],
                    "key": bv["key"],
                })

        return results

    def _filter_low_info(self, values: list[dict]) -> list[dict]:
        """过滤低信息量值"""
        filtered = []
        for v in values:
            val = v.get("value", "")
            # 排除空值、布尔、短字符串
            if val.lower() in LOW_INFO_VALUES:
                continue
            if len(val) < LOW_INFO_MIN_LENGTH:
                continue
            # 排除纯数字但长度很短的
            if val.isdigit() and len(val) < 4:
                continue
            filtered.append(v)
        return filtered

    def _find_matches(self, upstream_values: list[dict], downstream_values: list[dict]) -> list[dict]:
        """查找值匹配"""
        matches = []

        for up in upstream_values:
            up_val = up["value"]
            for down in downstream_values:
                down_val = down["value"]

                # 精确匹配
                if up_val == down_val:
                    matches.append({
                        "source_path": up["path"],
                        "target_location": down["location"],
                        "value": up_val,
                        "match_type": "exact",
                    })
                    continue

                # Bearer Token 变换
                if down_val.startswith("Bearer ") and down_val[7:] == up_val:
                    matches.append({
                        "source_path": up["path"],
                        "target_location": down["location"],
                        "value": up_val,
                        "match_type": "transform",
                        "transform": "Bearer ${value}",
                    })
                    continue

                # 包含关系（值的一部分匹配）
                if len(up_val) >= 8 and up_val in down_val:
                    matches.append({
                        "source_path": up["path"],
                        "target_location": down["location"],
                        "value": up_val,
                        "match_type": "contains",
                    })

        return matches

    def _calculate_confidence(
        self,
        match: dict,
        upstream_event: NetworkEvent,
        downstream_event: NetworkEvent,
        step_distance: int,
        total_steps: int,
    ) -> float:
        """
        计算依赖置信度
        confidence = value_match + temporal_order + field_name_similarity + value_uniqueness
        """
        score = 0.0

        # 1. 值匹配分 (0-0.4)
        match_type = match.get("match_type", "exact")
        if match_type == "exact":
            score += 0.4
        elif match_type == "transform":
            score += 0.35
        elif match_type == "contains":
            score += 0.2

        # 2. 时间顺序分 (0-0.2)
        # 相邻步骤得分更高
        if total_steps > 1:
            proximity = 1 - (step_distance / total_steps)
            score += 0.2 * proximity

        # 3. 字段名相似度 (0-0.2)
        source_key = match["source_path"].split(".")[-1]
        target_key = match["target_location"].split(".")[-1]
        name_similarity = SequenceMatcher(None, source_key.lower(), target_key.lower()).ratio()
        score += 0.2 * name_similarity

        # 4. 值唯一性 (0-0.2)
        value = match.get("value", "")
        uniqueness = self._estimate_uniqueness(value)
        score += 0.2 * uniqueness

        return min(round(score, 3), 1.0)

    def _estimate_uniqueness(self, value: str) -> float:
        """估计值的唯一性（高唯一性 = 更可能是有意义的依赖）"""
        # UUID 格式
        if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-', value, re.IGNORECASE):
            return 1.0
        # 长 token
        if len(value) > 32:
            return 0.9
        # 数字 ID
        if value.isdigit() and len(value) >= 6:
            return 0.7
        # 普通字符串
        if len(value) >= 8:
            return 0.5
        return 0.3
