"""场景执行器 - 解析 DSL 并执行 HTTP 请求"""
import re
import json
import time
import logging
import yaml
import httpx
from datetime import datetime
from typing import Any, Optional
from jsonpath_ng import parse as jsonpath_parse

logger = logging.getLogger(__name__)


class ScenarioRunner:
    """
    场景执行器
    解析 DSL YAML，按步骤执行 HTTP 请求
    支持变量提取/注入、断言验证、失败分类
    """

    def __init__(self, base_url: str = "", timeout: int = 30, env_variables: Optional[dict] = None,
                 secrets: Optional[dict] = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.env_variables = env_variables or {}
        self.secrets = secrets or {}

    def run(self, dsl_yaml: str) -> dict:
        """
        执行场景
        返回: {
            "status": "passed" | "failed",
            "steps": [step_result, ...],
            "total_duration_ms": float,
            "summary": {...}
        }
        """
        dsl = yaml.safe_load(dsl_yaml)
        if not isinstance(dsl, dict):
            raise ValueError("DSL 格式错误")

        steps = dsl.get("steps", [])
        variables = dict(dsl.get("variables", {}))
        context = {}  # 运行时变量（提取的值）

        # 解析环境变量引用
        resolved_vars = {}
        for var_name, var_value in variables.items():
            resolved_vars[var_name] = self._resolve_variable(str(var_value))

        results = []
        overall_status = "passed"
        start_time = time.time()

        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            for idx, step in enumerate(steps, 1):
                step_result = self._execute_step(client, step, idx, resolved_vars, context)
                results.append(step_result)

                if step_result["status"] == "failed":
                    overall_status = "failed"
                    # 默认断言失败不继续
                    if not dsl.get("continue_on_failure", False):
                        # 标记后续步骤为 skipped
                        for remaining in range(idx, len(steps)):
                            results.append({
                                "sequence": remaining + 1,
                                "step_id": steps[remaining].get("id", f"step_{remaining + 1}"),
                                "name": steps[remaining].get("name", ""),
                                "status": "skipped",
                                "duration_ms": 0,
                            })
                        break

        total_duration = (time.time() - start_time) * 1000

        passed = sum(1 for r in results if r["status"] == "passed")
        failed = sum(1 for r in results if r["status"] == "failed")
        skipped = sum(1 for r in results if r["status"] == "skipped")

        return {
            "status": overall_status,
            "steps": results,
            "total_duration_ms": round(total_duration, 2),
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
            },
        }

    def _execute_step(self, client: httpx.Client, step: dict, sequence: int,
                      variables: dict, context: dict) -> dict:
        """执行单个步骤"""
        step_id = step.get("id", f"step_{sequence}")
        step_name = step.get("name", f"步骤 {sequence}")
        request = step.get("request", {})
        extract = step.get("extract", {})
        assertions = step.get("assertions", [])

        result = {
            "sequence": sequence,
            "step_id": step_id,
            "name": step_name,
            "status": "passed",
            "started_at": datetime.utcnow().isoformat(),
        }

        start_time = time.time()

        try:
            # 构建请求
            method = request.get("method", "GET").upper()
            path = request.get("path", "/")

            # 替换路径参数
            path = self._replace_path_params(path, variables, context)

            # 构建 headers
            headers = {}
            for k, v in request.get("headers", {}).items():
                headers[k] = self._replace_variables(str(v), variables, context)

            # 构建 query
            query = {}
            for k, v in request.get("query", {}).items():
                query[k] = self._replace_variables(str(v), variables, context)

            # 构建 body
            json_body = None
            raw_body = request.get("json") or request.get("body")
            if raw_body and isinstance(raw_body, dict):
                json_body = self._replace_variables_in_dict(raw_body, variables, context)
            elif raw_body and isinstance(raw_body, str):
                raw_body = self._replace_variables(raw_body, variables, context)

            # 记录实际请求
            actual_request = {
                "method": method,
                "url": path,
                "headers": headers,
                "query": query,
                "body": json_body or raw_body,
            }
            result["actual_request"] = actual_request

            # 发送请求
            response = client.request(
                method=method,
                url=path,
                headers=headers,
                params=query if query else None,
                json=json_body,
                content=raw_body if isinstance(raw_body, str) and not json_body else None,
            )

            duration_ms = (time.time() - start_time) * 1000

            # 记录响应
            response_body = None
            try:
                response_body = response.json()
            except Exception:
                response_body = response.text[:1000]

            result["actual_response"] = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
            }
            result["duration_ms"] = round(duration_ms, 2)

            # 提取变量
            extracted = {}
            if extract and response_body:
                for var_name, json_path in extract.items():
                    value = self._extract_jsonpath(response_body, json_path)
                    if value is not None:
                        extracted[var_name] = value
                        context[var_name] = value
            result["extracted_variables"] = extracted

            # 执行断言
            assertion_results = []
            for assertion in assertions:
                assert_result = self._check_assertion(assertion, response, response_body)
                assertion_results.append(assert_result)

            result["assertion_results"] = assertion_results

            # 判断步骤状态
            if any(not a["passed"] for a in assertion_results):
                result["status"] = "failed"
                result["failure_category"] = "assertion"
                failed_assertions = [a for a in assertion_results if not a["passed"]]
                result["error_message"] = f"断言失败: {failed_assertions[0].get('message', '')}"
            elif response.status_code >= 500:
                result["status"] = "failed"
                result["failure_category"] = "business"
                result["error_message"] = f"服务端错误: {response.status_code}"
            elif response.status_code == 401 or response.status_code == 403:
                result["status"] = "failed"
                result["failure_category"] = "auth"
                result["error_message"] = f"鉴权失败: {response.status_code}"

        except httpx.ConnectError as e:
            result["status"] = "failed"
            result["failure_category"] = "network"
            result["error_message"] = f"连接失败: {str(e)}"
            result["duration_ms"] = round((time.time() - start_time) * 1000, 2)
        except httpx.TimeoutException as e:
            result["status"] = "failed"
            result["failure_category"] = "network"
            result["error_message"] = f"请求超时: {str(e)}"
            result["duration_ms"] = round((time.time() - start_time) * 1000, 2)
        except Exception as e:
            result["status"] = "failed"
            result["failure_category"] = "script"
            result["error_message"] = f"执行异常: {str(e)}"
            result["duration_ms"] = round((time.time() - start_time) * 1000, 2)

        result["finished_at"] = datetime.utcnow().isoformat()
        return result

    def _resolve_variable(self, value: str) -> str:
        """解析变量引用 ${env.XXX} 或 ${secret.XXX}"""
        pattern = r'\$\{env\.(\w+)\}'
        match = re.search(pattern, value)
        if match:
            env_key = match.group(1)
            return self.env_variables.get(env_key, "")

        pattern = r'\$\{secret\.(\w+)\}'
        match = re.search(pattern, value)
        if match:
            secret_key = match.group(1)
            return self.secrets.get(secret_key, "")

        return value

    def _replace_variables(self, value: str, variables: dict, context: dict) -> str:
        """替换字符串中的变量引用"""
        def replacer(match):
            var_ref = match.group(1)
            # 先查 context（运行时提取的变量）
            if var_ref in context:
                return str(context[var_ref])
            # 再查 variables（预设变量）
            if var_ref in variables:
                return str(variables[var_ref])
            return match.group(0)

        return re.sub(r'\$\{([^}]+)\}', replacer, value)

    def _replace_path_params(self, path: str, variables: dict, context: dict) -> str:
        """替换路径中的 {param} 参数"""
        def replacer(match):
            param_name = match.group(1)
            if param_name in context:
                return str(context[param_name])
            if param_name in variables:
                return str(variables[param_name])
            return match.group(0)

        return re.sub(r'\{(\w+)\}', replacer, path)

    def _replace_variables_in_dict(self, data: Any, variables: dict, context: dict) -> Any:
        """递归替换字典中的变量"""
        if isinstance(data, dict):
            return {k: self._replace_variables_in_dict(v, variables, context) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._replace_variables_in_dict(item, variables, context) for item in data]
        elif isinstance(data, str):
            return self._replace_variables(data, variables, context)
        return data

    def _extract_jsonpath(self, data: Any, path: str) -> Any:
        """从 JSON 数据中提取 JSONPath 值"""
        if not path or path == "$":
            return data

        # 简易实现：支持 $.field.subfield 和 $.field[0]
        try:
            parts = path.lstrip("$").lstrip(".")
            current = data
            for part in re.split(r'[.\[\]]', parts):
                if not part:
                    continue
                if isinstance(current, dict):
                    current = current.get(part)
                elif isinstance(current, list) and part.isdigit():
                    current = current[int(part)]
                else:
                    return None
                if current is None:
                    return None
            return current
        except Exception:
            return None

    def _check_assertion(self, assertion: dict, response: httpx.Response, body: Any) -> dict:
        """检查单个断言"""
        path = assertion.get("path", "")
        operator = assertion.get("operator", "equals")
        expected = assertion.get("expected")

        result = {
            "path": path,
            "operator": operator,
            "expected": expected,
            "passed": False,
        }

        try:
            # 特殊路径：$status
            if path == "$status":
                actual = response.status_code
            else:
                actual = self._extract_jsonpath(body, path)

            result["actual"] = actual

            if operator == "equals":
                # 类型兼容比较
                if isinstance(expected, int) and isinstance(actual, (int, float)):
                    result["passed"] = actual == expected
                elif isinstance(expected, str):
                    result["passed"] = str(actual) == expected
                else:
                    result["passed"] = actual == expected

            elif operator == "not_equals":
                result["passed"] = actual != expected

            elif operator == "not_empty":
                result["passed"] = actual is not None and actual != "" and actual != []

            elif operator == "contains":
                result["passed"] = expected in str(actual)

            elif operator == "gt":
                result["passed"] = float(actual) > float(expected)

            elif operator == "lt":
                result["passed"] = float(actual) < float(expected)

            elif operator == "gte":
                result["passed"] = float(actual) >= float(expected)

            elif operator == "lte":
                result["passed"] = float(actual) <= float(expected)

            elif operator == "type":
                type_map = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
                expected_type = type_map.get(str(expected))
                if expected_type:
                    result["passed"] = isinstance(actual, expected_type)

            else:
                result["passed"] = False
                result["message"] = f"未知操作符: {operator}"

            if not result["passed"]:
                result["message"] = f"期望 {expected}, 实际 {actual}"

        except Exception as e:
            result["passed"] = False
            result["message"] = f"断言执行异常: {str(e)}"

        return result
