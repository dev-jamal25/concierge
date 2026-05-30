from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass(slots=True)
class APIResult:
    ok: bool
    status_code: int | None = None
    data: Any = None
    text: str = ""
    error: str = ""

    @property
    def route_missing(self) -> bool:
        return self.status_code in {404, 405, 501}


class AdminAPI:
    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    @property
    def headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"authorization": f"Bearer {self.token}"}

    def get(self, path: str, **params: Any) -> APIResult:
        return self._request("GET", path, params={k: v for k, v in params.items() if v})

    def post(self, path: str, payload: dict[str, Any] | None = None) -> APIResult:
        return self._request("POST", path, json=payload)

    def put(self, path: str, payload: dict[str, Any]) -> APIResult:
        return self._request("PUT", path, json=payload)

    def delete(self, path: str) -> APIResult:
        return self._request("DELETE", path)

    def _request(self, method: str, path: str, **kwargs: Any) -> APIResult:
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                headers=self.headers,
                timeout=10,
                **kwargs,
            )
        except requests.RequestException as exc:
            return APIResult(ok=False, error=str(exc))

        data: Any = None
        if response.content:
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    data = response.json()
                except ValueError:
                    data = None
            else:
                data = response.text

        return APIResult(
            ok=response.ok,
            status_code=response.status_code,
            data=data,
            text=response.text,
        )


def require_token(token: str | None) -> bool:
    return bool((token or "").strip())


def error_message(result: APIResult, *, route_name: str) -> str:
    if result.route_missing:
        return f"{route_name} backend route is not available yet."
    if result.status_code == 401:
        return "Authentication failed. Add a valid tenant admin bearer token."
    if result.status_code == 403:
        return "Forbidden for this tenant or role."
    if result.error:
        return result.error
    if result.status_code is not None:
        detail = result.data.get("detail") if isinstance(result.data, dict) else result.text
        return f"{route_name} request failed with HTTP {result.status_code}: {detail}"
    return f"{route_name} request failed."
