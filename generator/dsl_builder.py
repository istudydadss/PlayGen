"""DSL 构建器 - 从录制数据构建语言无关的测试 DSL"""
import yaml
import logging
from typing import Optional
from collector.models import NetworkEvent
from analyzer.normalizer import UrlNormalizer
from analyzer.dependency import DependencyAnalyzer

logger = logging.getLogger(__name__)


class DslBuilder:
    """
    DSL 构建器
    从录制的网络事件和依赖分析结果构建 YAML DSL
    """

    def __init__(self, normalizer: Optional[UrlNormalizer] = None):
        self.normalizer = normalizer or UrlNormalizer()

    def build_from_events(
        self,
        events: list[NetworkEvent],
        selected_indices: list[int],
        name: str = "未命名场景",
        risk_level: str = "CONTROLLED",
        base_url: Optional[str] = None,
        dependencies: Optional[list[dict]] = None,
    ) -> str:
        """
        从网络事件构建 DSL
        events: 所有网络事件
        selected_indices: 选中的事件索引
        dependencies: 依赖分析结果
        """
        dsl = {
            "name": name,
            "risk_level": risk_level,
            "variables": {},
            "steps": [],
        }

        # 收集变量（从依赖关系）
        variables = {}
        dep_map = {}  # target_index -> [dependency]
        if dependencies:
            for dep in dependencies:
                target_idx = dep.get("target_step_index")
                if target_idx not in dep_map:
                    dep_map[target_idx] = []
                dep_map[target_idx].append(dep)

        # 构建步骤
        for seq, idx in enumerate(selected_indices, 1):
            if idx >= len(events):
                continue

            event = events[idx]
            step = self._build_step(event, seq, base_url)

            # 添加变量提取
            if dependencies and idx in dep_map:
                for dep in dep_map[idx]:
                    var_name = self._generate_var_name(dep["source_json_path"])
                    variables[var_name] = f"${{extract.{dep['source_json_path']}}}"
                    # 在对应步骤添加 extract
                    if "extract" not in step:
                        step["extract"] = {}
                    step["extract"][var_name] = dep["source_json_path"]

            dsl["steps"].append(step)

        dsl["variables"] = variables

        return yaml.dump(dsl, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def build_empty(self, name: str = "未命名场景") -> str:
        """构建空 DSL 模板"""
        dsl = {
            "name": name,
            "risk_level": "CONTROLLED",
            "variables": {},
            "steps": [
                {
                    "id": "step_1",
                    "name": "步骤 1",
                    "request": {
                        "method": "GET",
                        "path": "/api/example",
                    },
                    "assertions": [
                        {"path": "$.code", "operator": "equals", "expected": 0},
                    ],
                }
            ],
        }
        return yaml.dump(dsl, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def _build_step(self, event: NetworkEvent, sequence: int, base_url: Optional[str] = None) -> dict:
        """从网络事件构建单个步骤"""
        norm = self.normalizer.normalize_url(event.request.url, base_url)
        path = norm["normalized_path"]

        # 构建请求配置
        request_config = {
            "method": event.request.method,
            "path": path,
        }

        # Query 参数
        if event.request.query_params:
            request_config["query"] = event.request.query_params

        # Headers（过滤通用头）
        important_headers = {}
        skip_headers = {"accept", "accept-language", "user-agent", "content-type",
                        "accept-encoding", "connection", "host", "referer",
                        "origin", "sec-ch-ua", "sec-fetch-dest", "sec-fetch-mode",
                        "sec-fetch-site", "sec-ch-ua-mobile", "sec-ch-ua-platform"}
        for k, v in event.request.headers.items():
            if k.lower() not in skip_headers:
                important_headers[k] = v
        if important_headers:
            request_config["headers"] = important_headers

        # Body
        if event.request.body:
            request_config["json"] = event.request.body
        elif event.request.body_raw and event.request.method in ("POST", "PUT", "PATCH"):
            request_config["body"] = event.request.body_raw

        step = {
            "id": f"step_{sequence}",
            "name": f"{event.request.method} {path}",
            "request": request_config,
        }

        # 基础断言
        assertions = []
        if event.response:
            assertions.append({
                "path": "$status",
                "operator": "equals",
                "expected": event.response.status,
                "source": "auto",
            })

            # 如果有标准业务结构，添加 code 断言
            if event.response.body and isinstance(event.response.body, dict):
                body = event.response.body
                if "code" in body:
                    assertions.append({
                        "path": "$.code",
                        "operator": "equals",
                        "expected": body["code"],
                        "source": "auto",
                    })
                elif "success" in body:
                    assertions.append({
                        "path": "$.success",
                        "operator": "equals",
                        "expected": body["success"],
                        "source": "auto",
                    })

        if assertions:
            step["assertions"] = assertions

        return step

    def _generate_var_name(self, json_path: str) -> str:
        """从 JSONPath 生成变量名"""
        # $.data.accessToken -> access_token
        parts = json_path.replace("$.", "").replace("[", "_").replace("]", "").split(".")
        name = parts[-1] if parts else "var"
        # camelCase -> snake_case
        name = "".join(f"_{c.lower()}" if c.isupper() else c for c in name).lstrip("_")
        return name
