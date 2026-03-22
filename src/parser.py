"""
API Endpoint Parser
Uses regex-based pattern matching + heuristic analysis to extract
REST API endpoints from TypeScript/JavaScript (Express.js) source files,
route definition files, test files, and OpenAPI/Swagger specs.
"""

import re
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class APIEndpoint:
    method: str          # GET, POST, PUT, DELETE, PATCH, etc.
    path: str            # e.g. /api/Users/:id
    source_file: str     # relative path inside the repo
    line_number: int = 0
    description: str = ""
    tags: list[str] = field(default_factory=list)
    auth_required: Optional[bool] = None
    request_schema: dict = field(default_factory=dict)
    response_schema: dict = field(default_factory=dict)
    path_params: list[str] = field(default_factory=list)
    query_params: list[str] = field(default_factory=list)
    middlewares: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "path": self.path,
            "source_file": self.source_file,
            "line_number": self.line_number,
            "description": self.description,
            "tags": self.tags,
            "auth_required": self.auth_required,
            "path_params": self.path_params,
            "query_params": self.query_params,
            "middlewares": self.middlewares,
            "request_schema": self.request_schema,
            "response_schema": self.response_schema,
        }


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class EndpointParser:
    """
    Multi-strategy parser that extracts API endpoints from source files.
    Supports Express.js route definitions, Frisby/Supertest test files,
    and basic OpenAPI YAML/JSON specs.
    """

    # Express route patterns: app.get('/path', ...) or router.post('/path', ...)
    EXPRESS_ROUTE_RE = re.compile(
        r"""
        (?:app|router)\s*\.\s*
        (get|post|put|patch|delete|head|options|all)\s*\(
        \s*['"`]([^'"`]+)['"`]
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # app.use('/path', ...) — often a router mount
    EXPRESS_USE_RE = re.compile(
        r"""(?:app|router)\s*\.\s*use\s*\(\s*['"`]([^'"`]+)['"`]""",
        re.VERBOSE,
    )

    # Express security middleware annotations (isAuthorized, denyAll, etc.)
    MIDDLEWARE_RE = re.compile(
        r"security\.(isAuthorized|isAccounting|denyAll|isDeluxe|is(?:[A-Z][a-z]+)+)\(\)"
    )

    # Frisby / supertest test patterns: frisby.get(URL + '/path') or frisby.get('http://host/path')
    FRISBY_RE = re.compile(
        r"""frisby\s*\.\s*(get|post|put|patch|delete)\s*\((?:[^'"]*?)['"` ](?:https?://[^/'"]+)?([/][a-zA-Z0-9/_:?&=\-\.]+)""",
        re.IGNORECASE,
    )

    # Fetch / axios calls in TypeScript (client-side hints)
    FETCH_RE = re.compile(
        r"""(?:fetch|axios(?:\.\w+)?)\s*\(\s*['"`]([^'"`]+)['"`]""",
        re.IGNORECASE,
    )

    # OpenAPI YAML path block: "  /api/Users:"
    OPENAPI_PATH_RE = re.compile(r"^\s{0,4}(/[^\s:]+):\s*$")
    OPENAPI_METHOD_RE = re.compile(r"^\s+(get|post|put|patch|delete|head|options):\s*$")

    # Common body field names → JSON Schema types (heuristic)
    FIELD_TYPE_HINTS = {
        "id": "integer",
        "email": "string",
        "password": "string",
        "name": "string",
        "username": "string",
        "token": "string",
        "role": "string",
        "status": "string",
        "message": "string",
        "url": "string",
        "rating": "integer",
        "quantity": "integer",
        "price": "number",
        "total": "number",
        "comment": "string",
        "description": "string",
        "image": "string",
        "data": "object",
        "result": "object",
        "error": "string",
        "success": "boolean",
        "createdAt": "string",
        "updatedAt": "string",
    }

    def __init__(self):
        self._seen: set[str] = set()  # dedup by (method, path)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def parse_file(self, path: str, content: str) -> list[APIEndpoint]:
        """Dispatch to the appropriate parser based on file extension/name."""
        endpoints: list[APIEndpoint] = []

        if path.endswith((".ts", ".js")) and not path.endswith(".spec.ts"):
            endpoints.extend(self._parse_express(path, content))
        if "spec" in path or "test" in path or "frisby" in path.lower():
            endpoints.extend(self._parse_test_file(path, content))
        if path.endswith((".yaml", ".yml")):
            endpoints.extend(self._parse_openapi_yaml(path, content))
        if path.endswith(".json") and "swagger" in path.lower():
            endpoints.extend(self._parse_openapi_json(path, content))

        return self._dedup(endpoints)

    # ------------------------------------------------------------------
    # Express parser
    # ------------------------------------------------------------------

    def _parse_express(self, path: str, content: str) -> list[APIEndpoint]:
        endpoints = []
        lines = content.splitlines()

        for i, line in enumerate(lines, start=1):
            m = self.EXPRESS_ROUTE_RE.search(line)
            if not m:
                continue

            method = m.group(1).upper()
            route_path = m.group(2)

            if not route_path.startswith("/"):
                continue  # skip non-path strings

            ep = APIEndpoint(
                method=method,
                path=self._normalize_path(route_path),
                source_file=path,
                line_number=i,
                tags=self._infer_tags(route_path),
                path_params=self._extract_path_params(route_path),
            )

            # Scan surrounding lines for middleware clues
            ctx = "\n".join(lines[max(0, i-3):i+5])
            middlewares = self.MIDDLEWARE_RE.findall(ctx)
            ep.middlewares = list(set(middlewares))
            ep.auth_required = any(
                m in ("isAuthorized", "isAccounting", "isDeluxe") for m in ep.middlewares
            )
            if "denyAll" in ep.middlewares:
                ep.auth_required = True

            ep.request_schema = self._build_request_schema(ep, ctx)
            ep.response_schema = self._build_response_schema(ep, ctx)
            ep.description = self._infer_description(ep)

            endpoints.append(ep)

        return endpoints

    # ------------------------------------------------------------------
    # Frisby / supertest test parser
    # ------------------------------------------------------------------

    def _parse_test_file(self, path: str, content: str) -> list[APIEndpoint]:
        endpoints = []
        lines = content.splitlines()

        for i, line in enumerate(lines, start=1):
            m = self.FRISBY_RE.search(line)
            if not m:
                continue
            method = m.group(1).upper()
            route_path = m.group(2)

            ep = APIEndpoint(
                method=method,
                path=self._normalize_path(route_path),
                source_file=path,
                line_number=i,
                tags=self._infer_tags(route_path),
                path_params=self._extract_path_params(route_path),
            )
            ep.description = f"[From test] {self._infer_description(ep)}"
            ep.request_schema = self._build_request_schema(ep, line)
            ep.response_schema = self._build_response_schema(ep, line)
            endpoints.append(ep)

        return endpoints

    # ------------------------------------------------------------------
    # OpenAPI YAML parser
    # ------------------------------------------------------------------

    def _parse_openapi_yaml(self, path: str, content: str) -> list[APIEndpoint]:
        endpoints = []
        lines = content.splitlines()
        current_path = None

        for i, line in enumerate(lines, start=1):
            pm = self.OPENAPI_PATH_RE.match(line)
            if pm:
                current_path = pm.group(1)
                continue
            if current_path:
                mm = self.OPENAPI_METHOD_RE.match(line)
                if mm:
                    method = mm.group(1).upper()
                    ep = APIEndpoint(
                        method=method,
                        path=self._normalize_path(current_path),
                        source_file=path,
                        line_number=i,
                        tags=self._infer_tags(current_path),
                        path_params=self._extract_path_params(current_path),
                    )
                    ep.description = self._infer_description(ep)
                    ep.request_schema = self._build_request_schema(ep, "")
                    ep.response_schema = self._build_response_schema(ep, "")
                    endpoints.append(ep)

        return endpoints

    # ------------------------------------------------------------------
    # OpenAPI JSON parser
    # ------------------------------------------------------------------

    def _parse_openapi_json(self, path: str, content: str) -> list[APIEndpoint]:
        endpoints = []
        try:
            spec = json.loads(content)
            for route_path, methods in spec.get("paths", {}).items():
                for method, details in methods.items():
                    if method.lower() in ("get", "post", "put", "patch", "delete", "head", "options"):
                        ep = APIEndpoint(
                            method=method.upper(),
                            path=self._normalize_path(route_path),
                            source_file=path,
                            tags=details.get("tags", self._infer_tags(route_path)),
                            path_params=self._extract_path_params(route_path),
                        )
                        ep.description = details.get("summary", self._infer_description(ep))
                        ep.request_schema = self._extract_openapi_request_schema(details)
                        ep.response_schema = self._extract_openapi_response_schema(details)
                        endpoints.append(ep)
        except json.JSONDecodeError:
            pass
        return endpoints

    def _extract_openapi_request_schema(self, op: dict) -> dict:
        body = op.get("requestBody", {})
        content = body.get("content", {})
        for ct, val in content.items():
            schema = val.get("schema", {})
            if schema:
                return {"content_type": ct, "schema": schema}
        return {}

    def _extract_openapi_response_schema(self, op: dict) -> dict:
        responses = op.get("responses", {})
        result = {}
        for code, resp in responses.items():
            content = resp.get("content", {})
            for ct, val in content.items():
                schema = val.get("schema", {})
                result[str(code)] = {"content_type": ct, "schema": schema, "description": resp.get("description", "")}
        return result

    # ------------------------------------------------------------------
    # Schema inference helpers
    # ------------------------------------------------------------------

    def _build_request_schema(self, ep: APIEndpoint, context: str) -> dict:
        """Heuristically build a JSON Schema for the request body/params."""
        schema: dict = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        if ep.path_params:
            schema["path_parameters"] = {
                p: {"type": "integer" if p in ("id", "userId", "productId") else "string"}
                for p in ep.path_params
            }

        # No body for GET/DELETE
        if ep.method in ("GET", "DELETE", "HEAD", "OPTIONS"):
            schema["query_parameters"] = self._guess_query_params(ep.path, context)
            return schema

        # Infer body fields from known route patterns
        body_fields = self._guess_body_fields(ep.path, ep.method)
        for f, t in body_fields.items():
            schema["properties"][f] = {"type": t}
            schema["required"].append(f)

        return schema

    def _build_response_schema(self, ep: APIEndpoint, context: str) -> dict:
        """Heuristically build response schema based on endpoint semantics."""
        # Base on the path segment & method
        path_lc = ep.path.lower()
        props: dict = {}

        if "login" in path_lc or "authenticate" in path_lc:
            props = {
                "authentication": {
                    "type": "object",
                    "properties": {
                        "token": {"type": "string", "description": "JWT token"},
                        "bid": {"type": "integer", "description": "Basket ID"},
                        "umail": {"type": "string", "description": "User email"},
                    },
                }
            }
        elif "/users" in path_lc or ("/user" in path_lc and "login" not in path_lc and "reset" not in path_lc):
            props = {
                "id": {"type": "integer"},
                "username": {"type": "string"},
                "email": {"type": "string"},
                "role": {"type": "string", "enum": ["customer", "admin", "deluxe"]},
                "createdAt": {"type": "string", "format": "date-time"},
                "updatedAt": {"type": "string", "format": "date-time"},
            }
        elif "/products" in path_lc:
            props = {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "price": {"type": "number"},
                "image": {"type": "string"},
                "createdAt": {"type": "string", "format": "date-time"},
            }
        elif "/basket" in path_lc or "/basketitem" in path_lc:
            props = {
                "id": {"type": "integer"},
                "quantity": {"type": "integer"},
                "ProductId": {"type": "integer"},
                "BasketId": {"type": "integer"},
            }
        elif "/orders" in path_lc:
            props = {
                "orderId": {"type": "string"},
                "email": {"type": "string"},
                "totalPrice": {"type": "number"},
                "products": {"type": "array", "items": {"type": "object"}},
                "createdAt": {"type": "string", "format": "date-time"},
            }
        elif "/feedback" in path_lc:
            props = {
                "id": {"type": "integer"},
                "comment": {"type": "string"},
                "rating": {"type": "integer", "minimum": 0, "maximum": 5},
                "UserId": {"type": "integer"},
                "createdAt": {"type": "string", "format": "date-time"},
            }
        elif "/challenges" in path_lc:
            props = {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "category": {"type": "string"},
                "description": {"type": "string"},
                "difficulty": {"type": "integer"},
                "solved": {"type": "boolean"},
            }
        elif "whoami" in path_lc:
            props = {"user": {"type": "object"}}
        elif "search" in path_lc:
            props = {"data": {"type": "array", "items": {"type": "object"}}}
        elif "captcha" in path_lc:
            props = {
                "captchaId": {"type": "integer"},
                "answer": {"type": "integer"},
                "captcha": {"type": "string"},
            }

        status_map = self._method_default_statuses(ep.method)

        return {
            "success": {
                "status": status_map["success"],
                "schema": {
                    "type": "object",
                    "properties": props if props else {"data": {"type": "object"}},
                },
            },
            "error": {
                "status": status_map["error"],
                "schema": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                        "message": {"type": "string"},
                    },
                },
            },
        }

    def _guess_body_fields(self, path: str, method: str) -> dict[str, str]:
        path_lc = path.lower()
        if "login" in path_lc or "authenticate" in path_lc:
            return {"email": "string", "password": "string"}
        if "register" in path_lc or ("/users" in path_lc and method == "POST"):
            return {"email": "string", "password": "string", "passwordRepeat": "string", "securityQuestion": "object", "securityAnswer": "string"}
        if "feedback" in path_lc:
            return {"comment": "string", "rating": "integer", "captcha": "integer", "captchaId": "integer"}
        if "basket" in path_lc and "item" in path_lc:
            return {"ProductId": "integer", "BasketId": "integer", "quantity": "integer"}
        if "orders" in path_lc:
            return {"orderLinesData": "string"}
        if "address" in path_lc:
            return {"fullName": "string", "mobileNum": "integer", "zipCode": "string", "streetAddress": "string", "city": "string", "state": "string", "country": "string"}
        if "payment" in path_lc or "card" in path_lc:
            return {"fullName": "string", "cardNum": "integer", "expMonth": "integer", "expYear": "integer"}
        if "profile" in path_lc or "whoami" in path_lc:
            return {"username": "string"}
        if "submit" in path_lc or "key" in path_lc:
            return {"privateKey": "string"}
        if "wallet" in path_lc:
            return {"balance": "number"}
        if "review" in path_lc:
            return {"message": "string"}
        if "products" in path_lc and method in ("POST", "PUT", "PATCH"):
            return {"name": "string", "description": "string", "price": "number", "image": "string"}
        return {}

    def _guess_query_params(self, path: str, context: str) -> dict:
        params = {}
        if "search" in path.lower():
            params["q"] = {"type": "string", "description": "Search query string"}
        if "sort" in context.lower():
            params["sort"] = {"type": "string"}
            params["order"] = {"type": "string", "enum": ["ASC", "DESC"]}
        if "limit" in context.lower() or "page" in context.lower():
            params["limit"] = {"type": "integer"}
            params["offset"] = {"type": "integer"}
        return params

    def _method_default_statuses(self, method: str) -> dict:
        mapping = {
            "GET": {"success": 200, "error": 404},
            "POST": {"success": 201, "error": 400},
            "PUT": {"success": 200, "error": 400},
            "PATCH": {"success": 200, "error": 400},
            "DELETE": {"success": 200, "error": 404},
        }
        return mapping.get(method, {"success": 200, "error": 400})

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _normalize_path(self, path: str) -> str:
        # Remove query strings embedded in paths (edge cases in test files)
        path = path.split("?")[0]
        # Ensure leading slash
        if not path.startswith("/"):
            path = "/" + path
        return path

    def _extract_path_params(self, path: str) -> list[str]:
        return re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", path)

    def _infer_tags(self, path: str) -> list[str]:
        parts = [p for p in path.strip("/").split("/") if p and not p.startswith(":")]
        tags = []
        for part in parts[:3]:
            part = part.split("?")[0]
            if part not in ("api", "rest", "v1", "v2", "b2b"):
                tags.append(part.capitalize())
        if not tags:
            tags = ["General"]
        return tags

    def _infer_description(self, ep: APIEndpoint) -> str:
        method_verbs = {
            "GET": "Retrieve",
            "POST": "Create",
            "PUT": "Update",
            "PATCH": "Partially update",
            "DELETE": "Delete",
        }
        verb = method_verbs.get(ep.method, ep.method.capitalize())
        # Humanize the last meaningful path segment
        parts = [p for p in ep.path.split("/") if p and not p.startswith(":")]
        resource = parts[-1].replace("-", " ").replace("_", " ") if parts else "resource"
        return f"{verb} {resource}"

    def _dedup(self, endpoints: list[APIEndpoint]) -> list[APIEndpoint]:
        result = []
        for ep in endpoints:
            key = f"{ep.method}:{ep.path}"
            if key not in self._seen:
                self._seen.add(key)
                result.append(ep)
        return result
