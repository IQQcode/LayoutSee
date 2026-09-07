from __future__ import annotations

from .generated_contracts import CoreInfo


def info_envelope(info: CoreInfo, request_id: str) -> dict[str, object]:
    return {"ok": True, "data": info.model_dump(), "requestId": request_id}
