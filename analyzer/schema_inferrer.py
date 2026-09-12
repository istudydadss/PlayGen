"""JSON Schema 推断引擎"""
import hashlib
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SchemaInferrer:
    """
    JSON Schema 推断器
    - 递归推断字段类型
    - 多样本合并，标记必填字段
    - 数值类型兼容 integer/number
    - 数组 item schema 推断
    - Schema 版本哈希
    """

    def infer(self, data: Any) -> dict:
        """从单个样本推断 Schema"""
        schema = self._infer_type(data)
        return schema

    def merge_schemas(self, schemas: list[dict]) -> dict:
        """
        合并多个 Schema
        - 只有稳定出现的字段标记为必填
        - 类型冲突时取兼容类型
        """
        if not schemas:
            return {}
        if len(schemas) == 1:
            result = schemas[0].copy()
            result["_required_count"] = 1
            return result

        merged = self._merge_objects(schemas)
        return merged

    def compute_schema_hash(self, schema: dict) -> str:
        """计算 Schema 哈希（排除元数据字段）"""
        clean = self._clean_schema(schema)
        schema_json = json.dumps(clean, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(schema_json.encode("utf-8")).hexdigest()[:16]

    def detect_changes(self, old_schema: dict, new_schema: dict) -> dict:
        """
        检测 Schema 变更
        返回: {
            "change_type": "compatible" | "breaking" | "none",
            "changes": [{"type": str, "path": str, "detail": str}]
        }
        """
        changes = []

        old_props = old_schema.get("properties", {})
        new_props = new_schema.get("properties", {})

        # 检测字段删除（破坏性）
        for key in old_props:
            if key not in new_props:
                changes.append({
                    "type": "field_removed",
                    "path": f"$.{key}",
                    "detail": f"字段 '{key}' 被删除",
                    "breaking": True,
                })

        # 检测字段新增（兼容）
        for key in new_props:
            if key not in old_props:
                changes.append({
                    "type": "field_added",
                    "path": f"$.{key}",
                    "detail": f"新增字段 '{key}'",
                    "breaking": False,
                })

        # 检测类型变化（可能破坏性）
        for key in old_props:
            if key in new_props:
                old_type = old_props[key].get("type")
                new_type = new_props[key].get("type")
                if old_type and new_type and old_type != new_type:
                    # integer -> number 是兼容的
                    if old_type == "integer" and new_type == "number":
                        changes.append({
                            "type": "type_widened",
                            "path": f"$.{key}",
                            "detail": f"类型从 {old_type} 扩展为 {new_type}",
                            "breaking": False,
                        })
                    else:
                        changes.append({
                            "type": "type_changed",
                            "path": f"$.{key}",
                            "detail": f"类型从 {old_type} 变为 {new_type}",
                            "breaking": True,
                        })

        has_breaking = any(c.get("breaking") for c in changes)
        change_type = "breaking" if has_breaking else ("compatible" if changes else "none")

        return {
            "change_type": change_type,
            "changes": changes,
        }

    def _infer_type(self, data: Any) -> dict:
        """推断单个值的类型"""
        if isinstance(data, dict):
            return self._infer_object(data)
        elif isinstance(data, list):
            return self._infer_array(data)
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

    def _infer_object(self, data: dict) -> dict:
        """推断对象 Schema"""
        properties = {}
        required = []

        for key, value in data.items():
            properties[key] = self._infer_type(value)
            # 非空值视为必填候选
            if value is not None and value != "" and value != []:
                required.append(key)

        schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = sorted(required)

        return schema

    def _infer_array(self, data: list) -> dict:
        """推断数组 Schema"""
        if not data:
            return {"type": "array", "items": {}}

        # 从所有元素推断 item schema
        item_schemas = [self._infer_type(item) for item in data]
        merged_items = self.merge_schemas(item_schemas)

        return {
            "type": "array",
            "items": merged_items,
        }

    def _merge_objects(self, schemas: list[dict]) -> dict:
        """合并多个对象 Schema"""
        all_keys = set()
        key_count = {}
        key_schemas = {}

        for schema in schemas:
            if schema.get("type") != "object":
                continue
            props = schema.get("properties", {})
            for key in props:
                all_keys.add(key)
                key_count[key] = key_count.get(key, 0) + 1
                if key not in key_schemas:
                    key_schemas[key] = []
                key_schemas[key].append(props[key])

        total = len(schemas)
        merged_props = {}
        merged_required = []

        for key in sorted(all_keys):
            # 合并该字段的所有 schema
            field_schemas = key_schemas.get(key, [])
            if field_schemas:
                merged_props[key] = self._merge_field_schemas(field_schemas)

            # 出现在 >80% 样本中的字段视为必填
            if key_count.get(key, 0) >= total * 0.8:
                merged_required.append(key)

        result = {
            "type": "object",
            "properties": merged_props,
            "_sample_count": total,
        }
        if merged_required:
            result["required"] = merged_required

        return result

    def _merge_field_schemas(self, schemas: list[dict]) -> dict:
        """合并同一字段的多个 Schema"""
        types = set()
        for s in schemas:
            t = s.get("type", "unknown")
            types.add(t)

        # 类型兼容处理
        if "integer" in types and "number" in types:
            types.discard("integer")
        if len(types) == 1:
            result = types.pop()
            base = {"type": result}
            # 如果是对象，递归合并
            if result == "object":
                obj_schemas = [s for s in schemas if s.get("type") == "object"]
                if obj_schemas:
                    merged = self._merge_objects(obj_schemas)
                    base["properties"] = merged.get("properties", {})
            return base

        # 多类型
        return {"type": list(types)[0] if types else "unknown"}

    def _clean_schema(self, schema: dict) -> dict:
        """清理 Schema 中的元数据字段"""
        clean = {}
        for key, value in schema.items():
            if key.startswith("_"):
                continue
            if isinstance(value, dict):
                clean[key] = self._clean_schema(value)
            elif isinstance(value, list):
                clean[key] = [
                    self._clean_schema(v) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                clean[key] = value
        return clean
