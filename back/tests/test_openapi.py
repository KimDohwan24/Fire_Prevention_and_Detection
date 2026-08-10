"""OpenAPI 스펙이 실제 라우트와 어긋나지 않게 지키는 테스트.

스펙(openapi.yaml)은 손으로 쓰는 파일이라, 라우트를 고치고 스펙을 안 고치면
프론트에게 거짓말하는 문서가 나간다. 그걸 여기서 빨간불로 잡는다.

라우트를 추가·삭제·변경했다면 openapi.yaml 도 같이 고쳐야 이 파일이 통과한다.
"""
import re
from pathlib import Path

import pytest
import yaml
from openapi_spec_validator import validate

SPEC_PATH = Path(__file__).resolve().parents[1] / "openapi.yaml"

# 문서화 대상에서 빼는 것 — Flask 기본 static 과 문서 서빙 자신
EXCLUDED_ENDPOINT_PREFIXES = ("static", "docs.", "docs_ui.")

# <int:cctv_no> → {cctv_no} · <path:filename> → {filename}
_FLASK_PARAM = re.compile(r"<(?:[^:<>]+:)?([^:<>]+)>")

# auth.py 데코레이터가 다는 표식 → 스펙 securitySchemes 이름
AUTH_TO_SCHEME = {"bearer": "bearerAuth", "internal": "internalKey"}


def _flask_to_openapi(rule: str) -> str:
    return _FLASK_PARAM.sub(r"{\1}", rule)


@pytest.fixture(scope="module")
def spec():
    assert SPEC_PATH.exists(), f"스펙 파일이 없다: {SPEC_PATH}"
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def _documented_rules(app):
    """실제 등록된 라우트 → {OpenAPI 경로: 메서드 소문자 집합}."""
    found: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith(EXCLUDED_ENDPOINT_PREFIXES):
            continue
        methods = {m.lower() for m in rule.methods} - {"head", "options"}
        found.setdefault(_flask_to_openapi(rule.rule), set()).update(methods)
    return found


# ---------- 1. 스펙 자체가 유효한가 ----------

def test_spec_is_valid_openapi(spec):
    """문법이 깨지면 TS 타입 생성이 통째로 실패하므로 제일 먼저 막는다."""
    validate(spec)


def test_spec_declares_both_security_schemes(spec):
    schemes = spec["components"]["securitySchemes"]
    assert schemes["bearerAuth"]["scheme"] == "bearer"
    assert schemes["internalKey"]["name"] == "X-Internal-Key"


def _resolve(spec: dict, node: dict) -> dict:
    """$ref 를 따라가 실제 노드를 돌려준다 (내부 참조만 쓴다)."""
    while "$ref" in node:
        target = spec
        for part in node["$ref"].lstrip("#/").split("/"):
            target = target[part]
        node = target
    return node


def test_error_responses_declare_example(spec):
    """4xx 응답은 저마다 실제로 나가는 code/message 예시를 들고 있어야 한다.

    예시가 없으면 Swagger UI 가 공통 Error 스키마로 본문을 만들어 내서
    400·401·403 이 전부 똑같이 보인다. 프론트는 그 화면을 보고 분기할 code 를
    정하므로, 예시가 없는 게 아니라 '틀린 예시가 있는' 상태가 된다.
    """
    missing = []
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            for status, res in op["responses"].items():
                if not status.startswith(("4", "5")):
                    continue
                body = _resolve(spec, res).get("content", {}).get("application/json", {})
                if not ({"example", "examples"} & set(body)):
                    missing.append(f"{method.upper()} {path} → {status}")
    assert not missing, "에러 응답 예시 누락:\n" + "\n".join(missing)


# ---------- 2·3. 라우트와 스펙이 일치하는가 ----------

def test_every_route_is_documented(app, spec):
    missing = sorted(set(_documented_rules(app)) - set(spec["paths"]))
    assert not missing, f"스펙에 빠진 경로: {missing}"


def test_spec_has_no_phantom_paths(app, spec):
    phantom = sorted(set(spec["paths"]) - set(_documented_rules(app)))
    assert not phantom, f"실제로 없는데 스펙에만 있는 경로: {phantom}"


def test_methods_match_per_path(app, spec):
    actual = _documented_rules(app)
    mismatches = []
    for path, methods in actual.items():
        documented = {
            m for m in spec["paths"].get(path, {})
            if m in {"get", "post", "put", "patch", "delete"}
        }
        if documented != methods:
            mismatches.append(f"{path}: 실제={sorted(methods)} 스펙={sorted(documented)}")
    assert not mismatches, "메서드 불일치:\n" + "\n".join(mismatches)


# ---------- 4. 문서가 실제로 서빙되는가 ----------

def test_swagger_ui_is_served(client):
    res = client.get("/api/docs/")
    assert res.status_code == 200
    assert b"swagger" in res.data.lower()


def test_raw_spec_is_served_and_parseable(client):
    res = client.get("/api/openapi.yaml")
    assert res.status_code == 200
    loaded = yaml.safe_load(res.data.decode("utf-8"))
    assert loaded["openapi"].startswith("3.")


# ---------- 5. 인증이 정확히 문서화됐는가 ----------

def test_protected_routes_declare_security(app, spec):
    """데코레이터가 걸린 엔드포인트는 스펙에도 security 가 있어야 한다.

    공개로 잘못 적어두면 프론트가 토큰 없이 호출하다 401 에 막혀 시간을 버린다.
    """
    problems = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith(EXCLUDED_ENDPOINT_PREFIXES):
            continue
        view = app.view_functions[rule.endpoint]
        required = getattr(view, "_auth", None)
        if required is None:
            continue

        path = _flask_to_openapi(rule.rule)
        expected = AUTH_TO_SCHEME[required]
        for method in {m.lower() for m in rule.methods} - {"head", "options"}:
            op = spec["paths"].get(path, {}).get(method, {})
            declared = {name for entry in op.get("security", []) for name in entry}
            if expected not in declared:
                problems.append(f"{method.upper()} {path}: {expected} 선언 없음")
    assert not problems, "인증 문서화 누락:\n" + "\n".join(problems)


def test_public_routes_declare_no_security(app, spec):
    """반대 방향 — 데코레이터가 없는데 스펙엔 인증이 걸려 있으면 그것도 거짓말이다."""
    problems = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith(EXCLUDED_ENDPOINT_PREFIXES):
            continue
        if getattr(app.view_functions[rule.endpoint], "_auth", None) is not None:
            continue

        path = _flask_to_openapi(rule.rule)
        for method in {m.lower() for m in rule.methods} - {"head", "options"}:
            op = spec["paths"].get(path, {}).get(method, {})
            if op.get("security"):
                problems.append(f"{method.upper()} {path}: 공개인데 security 선언됨")
    assert not problems, "인증 문서화 과잉:\n" + "\n".join(problems)
