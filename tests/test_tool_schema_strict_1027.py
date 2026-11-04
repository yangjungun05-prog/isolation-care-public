"""strict 도구 스키마가 API 검사를 넘는 꼴인지(10-27 village_6 실측).

API의 strict 도구 검사는 `{"type": ["string", "null"], "enum": [..., null]}` 꼴을
400('Enum value … does not match declared type')으로 거절한다. 계획기(query.plan_schema)가 이 꼴이라
10-27 API 길 첫 실응답 시험에서 계산 길이 한 번도 돌지 못했다(CLI 길의 --json-schema 는 이 검사를
하지 않아 10-24 ~ 10-27 아침까지 숨어 있었다). nullable enum 은 anyOf 꼴로 쓴다.
"""

from src.assistant import query
from src.assistant.doc import SCHEMA as DOC_SCHEMA
from src.assistant.slots import desk_tool_schema


def _walk(node, path="$"):
    if isinstance(node, dict):
        t = node.get("type")
        if "enum" in node and isinstance(t, list):
            yield path, node
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def test_no_type_list_with_enum_in_any_tool_schema():
    for name, schema in (
        ("planner", query.plan_schema()),
        ("desk", desk_tool_schema()),
        ("doc", DOC_SCHEMA),
    ):
        bad = [p for p, _ in _walk(schema)]
        assert not bad, f"{name}: enum 과 type 목록을 같이 쓴 칸 {bad} — _nullable_enum(anyOf)로"


def test_planner_nullable_enums_are_anyof():
    s = query.plan_schema()
    for key in ("region", "kind"):
        node = s["properties"][key]
        assert "anyOf" in node and {"type": "null"} in node["anyOf"], key
        assert node["anyOf"][0]["type"] == "string" and node["anyOf"][0]["enum"]
    per = s["properties"]["conds"]["items"]["properties"]["per"]
    assert per["anyOf"][0]["enum"] == list(query.PER)
