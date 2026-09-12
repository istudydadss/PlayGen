"""执行报告生成器"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# 敏感字段列表（脱敏用）
SENSITIVE_KEYS = {"password", "token", "accessToken", "refreshToken", "secret",
                  "authorization", "cookie", "phone", "idCard"}


class ExecutionReporter:
    """
    执行报告生成器
    格式化执行结果，支持脱敏和统计
    """

    def __init__(self, sensitive_fields: Optional[list[str]] = None):
        self.sensitive_fields = set(sensitive_fields or SENSITIVE_KEYS)

    def generate_report(self, execution_result: dict, scenario_name: str = "") -> dict:
        """
        生成结构化报告
        返回: {
            "scenario_name": str,
            "status": str,
            "summary": dict,
            "steps": [formatted_step, ...],
            "timing": dict,
            "generated_at": str,
        }
        """
        summary = execution_result.get("summary", {})
        steps = execution_result.get("steps", [])

        # 格式化步骤
        formatted_steps = []
        for step in steps:
            formatted = self._format_step(step)
            formatted_steps.append(formatted)

        # 失败分类统计
        failure_categories = {}
        for step in steps:
            cat = step.get("failure_category")
            if cat:
                failure_categories[cat] = failure_categories.get(cat, 0) + 1

        return {
            "scenario_name": scenario_name,
            "status": execution_result.get("status", "unknown"),
            "summary": summary,
            "steps": formatted_steps,
            "timing": {
                "total_duration_ms": execution_result.get("total_duration_ms", 0),
            },
            "failure_categories": failure_categories,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def generate_text_report(self, execution_result: dict, scenario_name: str = "") -> str:
        """生成文本格式报告"""
        report = self.generate_report(execution_result, scenario_name)

        lines = []
        lines.append(f"{'='*60}")
        lines.append(f"场景: {report['scenario_name']}")
        lines.append(f"状态: {report['status'].upper()}")
        lines.append(f"耗时: {report['timing']['total_duration_ms']:.2f}ms")
        lines.append(f"{'='*60}")

        summary = report["summary"]
        lines.append(f"总计: {summary.get('total', 0)} | "
                     f"通过: {summary.get('passed', 0)} | "
                     f"失败: {summary.get('failed', 0)} | "
                     f"跳过: {summary.get('skipped', 0)}")
        lines.append("")

        for step in report["steps"]:
            status_icon = {"passed": "[PASS]", "failed": "[FAIL]", "skipped": "[SKIP]"}.get(step["status"], "[????]")
            lines.append(f"  {status_icon} 步骤 {step['sequence']}: {step['name']}")

            if step.get("duration_ms"):
                lines.append(f"         耗时: {step['duration_ms']:.2f}ms")

            if step.get("status_code"):
                lines.append(f"         状态码: {step['status_code']}")

            if step.get("error_message"):
                lines.append(f"         错误: {step['error_message']}")

            if step.get("assertion_failures"):
                for af in step["assertion_failures"]:
                    lines.append(f"         断言失败: {af.get('message', '')}")

        lines.append(f"{'='*60}")
        return "\n".join(lines)

    def _format_step(self, step: dict) -> dict:
        """格式化单个步骤结果"""
        formatted = {
            "sequence": step.get("sequence"),
            "step_id": step.get("step_id"),
            "name": step.get("name"),
            "status": step.get("status"),
            "duration_ms": step.get("duration_ms"),
            "error_message": step.get("error_message"),
            "failure_category": step.get("failure_category"),
        }

        # 请求信息（脱敏）
        if step.get("actual_request"):
            formatted["request"] = self._sanitize(step["actual_request"])

        # 响应信息（脱敏）
        if step.get("actual_response"):
            resp = step["actual_response"]
            formatted["status_code"] = resp.get("status_code")
            formatted["response"] = self._sanitize(resp)

        # 提取的变量
        formatted["extracted_variables"] = step.get("extracted_variables", {})

        # 断言结果
        assertion_results = step.get("assertion_results", [])
        formatted["assertions"] = assertion_results
        formatted["assertion_failures"] = [a for a in assertion_results if not a.get("passed")]

        return formatted

    def _sanitize(self, data: dict, depth: int = 0) -> dict:
        """脱敏处理"""
        if depth > 5:
            return data

        if not isinstance(data, dict):
            return data

        sanitized = {}
        for key, value in data.items():
            if key.lower() in self.sensitive_fields:
                sanitized[key] = "***MASKED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize(value, depth + 1)
            elif isinstance(value, list):
                sanitized[key] = [
                    self._sanitize(item, depth + 1) if isinstance(item, dict) else item
                    for item in value
                ]
            elif isinstance(value, str) and key.lower() in ("authorization", "cookie"):
                sanitized[key] = "***MASKED***"
            else:
                sanitized[key] = value

        return sanitized
