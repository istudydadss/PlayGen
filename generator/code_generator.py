"""代码生成器 - 从 DSL 生成 pytest/httpx 测试代码"""
import os
import re
import yaml
import logging
from typing import Optional
from jinja2 import Environment, FileSystemLoader, BaseLoader

logger = logging.getLogger(__name__)

# 内置 pytest/httpx 模板
PYTEST_TEMPLATE = '''"""
{{ scenario_name }}
自动生成测试代码 - PlayGen 平台
"""
import pytest
import httpx
import os

# 环境变量
BASE_URL = os.getenv("BASE_URL", "{{ base_url }}")
TIMEOUT = {{ timeout }}


{% for var_name, var_value in variables.items() %}
{% if var_value.startswith('${env.') %}
{{ var_name }} = os.getenv("{{ var_value[6:-1] }}", "")
{% elif var_value.startswith('${secret.') %}
{{ var_name }} = os.getenv("{{ var_value[9:-1] }}", "")
{% else %}
{{ var_name }} = "{{ var_value }}"
{% endif %}
{% endfor %}


@pytest.fixture
def client():
    """HTTP 客户端"""
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as c:
        yield c


{% for step in steps %}
def _step_{{ step.safe_id }}(client: httpx.Client{% if step.extract %}, context: dict{% endif %}):
    """{{ step.name }}"""
    # 构建请求
    url = "{{ step.path }}"
    {% if step.path_params %}
    # Path 参数替换
    {% for param, var_ref in step.path_params.items() %}
    url = url.replace("{{" + "{" + param + "}" + "}}", str(context.get("{{ var_ref }}", "")))
    {% endfor %}
    {% endif %}

    headers = {
        {% for key, value in step.headers.items() %}
        "{{ key }}": "{{ value }}",
        {% endfor %}
    }
    {% if step.has_variable_headers %}
    # 变量引用替换
    {% for key, var_ref in step.variable_headers.items() %}
    headers["{{ key }}"] = str(context.get("{{ var_ref }}", ""))
    {% endfor %}
    {% endif %}

    {% if step.json_body is not none %}
    json_body = {{ step.json_body }}
    {% elif step.has_variable_body %}
    json_body = {}
    {% for key, var_ref in step.variable_body.items() %}
    json_body["{{ key }}"] = context.get("{{ var_ref }}", "")
    {% endfor %}
    {% endif %}

    # 发送请求
    response = client.{{ step.method_lower }}(
        url,
        headers=headers{% if step.json_body is not none or step.has_variable_body %},
        json=json_body{% endif %},
    )

    # 断言
    {% for assertion in step.assertions %}
    {% if assertion.path == "$status" %}
    assert response.status_code == {{ assertion.expected }}, f"状态码不匹配: 期望 {{ assertion.expected }}, 实际 {response.status_code}"
    {% elif assertion.operator == "equals" %}
    data = response.json()
    assert _get_value(data, "{{ assertion.path }}") == {{ _format_expected(assertion.expected) }}, \
        "{{ assertion.path }}: 期望 {{ assertion.expected }}, 实际 {_get_value(data, '{{ assertion.path }}')}"
    {% elif assertion.operator == "not_empty" %}
    data = response.json()
    assert _get_value(data, "{{ assertion.path }}"), "{{ assertion.path }} 不应为空"
    {% endif %}
    {% endfor %}

    {% if step.extract %}
    # 提取变量
    data = response.json()
    {% for var_name, json_path in step.extract.items() %}
    context["{{ var_name }}"] = _get_value(data, "{{ json_path }}")
    {% endfor %}
    {% endif %}

    return response


{% endfor %}

class Test{{ class_name }}:
    """{{ scenario_name }}"""

    def test_scenario(self, client):
        """完整场景执行"""
        context = {}

        {% for step in steps %}
        # 步骤 {{ step.sequence }}: {{ step.name }}
        {% if step.extract %}
        _step_{{ step.safe_id }}(client, context)
        {% else %}
        _step_{{ step.safe_id }}(client)
        {% endif %}
        {% endfor %}


def _get_value(data, path: str):
    """简易 JSONPath 取值"""
    if path == "$status":
        return None
    parts = path.lstrip("$.").split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current
'''


class CodeGenerator:
    """
    代码生成器
    使用 Jinja2 模板从 DSL 生成测试代码
    """

    def __init__(self, templates_dir: Optional[str] = None):
        if templates_dir and os.path.isdir(templates_dir):
            self.env = Environment(
                loader=FileSystemLoader(templates_dir),
                keep_trailing_newline=True,
                trim_blocks=True,
                lstrip_blocks=True,
            )
        else:
            self.env = Environment(
                loader=BaseLoader(),
                keep_trailing_newline=True,
                trim_blocks=True,
                lstrip_blocks=True,
            )
            self.env.from_string = self.env.from_string

        # 注册辅助函数
        self.env.globals["_format_expected"] = self._format_expected

    def generate(self, dsl_yaml: str, language: str = "pytest", base_url: str = "http://localhost") -> dict:
        """
        从 DSL 生成代码
        返回: {"code": str, "filename": str, "language": str}
        """
        dsl = yaml.safe_load(dsl_yaml)
        if not isinstance(dsl, dict):
            raise ValueError("DSL 格式错误")

        scenario_name = dsl.get("name", "未命名场景")
        variables = dsl.get("variables", {})
        steps = dsl.get("steps", [])

        if language == "pytest":
            return self._generate_pytest(scenario_name, variables, steps, base_url)
        else:
            raise ValueError(f"不支持的语言: {language}")

    def _generate_pytest(self, name: str, variables: dict, steps: list, base_url: str) -> dict:
        """生成 pytest 代码"""
        template = self.env.from_string(PYTEST_TEMPLATE)

        # 预处理步骤数据
        processed_steps = []
        for idx, step in enumerate(steps, 1):
            request = step.get("request", {})
            safe_id = re.sub(r'[^a-zA-Z0-9_]', '_', step.get("id", f"step_{idx}"))

            # 处理 headers 中的变量引用
            headers = request.get("headers", {})
            variable_headers = {}
            clean_headers = {}
            for k, v in headers.items():
                if isinstance(v, str) and "${" in v:
                    var_ref = self._extract_var_ref(v)
                    variable_headers[k] = var_ref
                else:
                    clean_headers[k] = v

            # 处理 body 中的变量引用
            json_body = request.get("json")
            has_variable_body = False
            variable_body = {}
            if json_body and isinstance(json_body, dict):
                for k, v in json_body.items():
                    if isinstance(v, str) and "${" in v:
                        variable_body[k] = self._extract_var_ref(v)
                        has_variable_body = True
                if has_variable_body:
                    json_body = {k: v for k, v in json_body.items() if k not in variable_body}
                    if not json_body:
                        json_body = None

            # 处理 path 参数
            path = request.get("path", "/")
            path_params = {}
            import re as re_mod
            for match in re_mod.finditer(r'\{(\w+)\}', path):
                param_name = match.group(1)
                path_params[param_name] = param_name

            processed_step = {
                "sequence": idx,
                "safe_id": safe_id,
                "name": step.get("name", f"步骤 {idx}"),
                "method_lower": request.get("method", "GET").lower(),
                "path": path,
                "path_params": path_params,
                "headers": clean_headers,
                "has_variable_headers": bool(variable_headers),
                "variable_headers": variable_headers,
                "json_body": json_body,
                "has_variable_body": has_variable_body,
                "variable_body": variable_body,
                "extract": step.get("extract", {}),
                "assertions": step.get("assertions", []),
            }
            processed_steps.append(processed_step)

        # 生成类名
        class_name = "".join(w.capitalize() for w in re.split(r'[^a-zA-Z0-9]', name) if w)
        if not class_name:
            class_name = "TestScenario"

        code = template.render(
            scenario_name=name,
            base_url=base_url,
            timeout=30,
            variables=variables,
            steps=processed_steps,
            class_name=class_name,
        )

        filename = f"test_{re.sub(r'[^a-zA-Z0-9_]', '_', name).lower()}.py"

        return {
            "code": code,
            "filename": filename,
            "language": "pytest",
        }

    def _extract_var_ref(self, value: str) -> str:
        """从 ${var_name} 提取变量名"""
        match = re.search(r'\$\{([^}]+)\}', value)
        return match.group(1) if match else value

    def _format_expected(self, expected) -> str:
        """格式化期望值"""
        if isinstance(expected, bool):
            return str(expected)
        if isinstance(expected, int):
            return str(expected)
        if isinstance(expected, str):
            if expected.isdigit():
                return expected
            return f'"{expected}"'
        return f'"{expected}"'
