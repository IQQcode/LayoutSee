from __future__ import annotations

from http import HTTPStatus

STATUS_BY_CODE: dict[str, HTTPStatus] = {
    "DEVICE_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "REF_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "PLUGIN_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "DEVICE_DISCONNECTED": HTTPStatus.CONFLICT,
    "DEVICE_OFFLINE": HTTPStatus.CONFLICT,
    "DEVICE_UNAUTHORIZED": HTTPStatus.CONFLICT,
    "SNAPSHOT_IN_PROGRESS": HTTPStatus.CONFLICT,
    "SNAPSHOT_STALE": HTTPStatus.CONFLICT,
    "AMBIGUOUS_ELEMENT": HTTPStatus.CONFLICT,
    "DEVICE_BUSY": HTTPStatus.CONFLICT,
    "INVALID_ARGUMENT": HTTPStatus.BAD_REQUEST,
    "INVALID_XPATH": HTTPStatus.UNPROCESSABLE_ENTITY,
    "PLUGIN_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "READ_ONLY_MODE": HTTPStatus.FORBIDDEN,
    "PERMISSION_REQUIRED": HTTPStatus.FORBIDDEN,
    "PLUGIN_PERMISSION_DENIED": HTTPStatus.FORBIDDEN,
    "PLUGIN_RATE_LIMITED": HTTPStatus.TOO_MANY_REQUESTS,
    "HOST_CAPABILITY_UNAVAILABLE": HTTPStatus.NOT_IMPLEMENTED,
    "VERSION_INCOMPATIBLE": HTTPStatus.UPGRADE_REQUIRED,
    "PLUGIN_INCOMPATIBLE": HTTPStatus.UPGRADE_REQUIRED,
    "ADB_NOT_FOUND": HTTPStatus.SERVICE_UNAVAILABLE,
    "CORE_UNAVAILABLE": HTTPStatus.SERVICE_UNAVAILABLE,
    "MEDIA_UNAVAILABLE": HTTPStatus.SERVICE_UNAVAILABLE,
    "OPERATION_TIMEOUT": HTTPStatus.GATEWAY_TIMEOUT,
}

DEFAULT_STATUS = HTTPStatus.INTERNAL_SERVER_ERROR


class CoreError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: HTTPStatus | None = None,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status or STATUS_BY_CODE.get(code, DEFAULT_STATUS)
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details:
            value["details"] = self.details
        return value


def require(value: object, name: str) -> object:
    if value is None or value == "":
        raise CoreError("INVALID_ARGUMENT", f"缺少参数：{name}")
    return value


def require_str(value: object, name: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoreError("INVALID_ARGUMENT", f"缺少参数：{name}")
    if len(value) > max_length:
        raise CoreError("INVALID_ARGUMENT", f"参数过长：{name}")
    return value


def require_int(value: object, name: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CoreError("INVALID_ARGUMENT", f"参数必须是整数：{name}")
    if minimum is not None and value < minimum:
        raise CoreError("INVALID_ARGUMENT", f"参数超出范围：{name}")
    if maximum is not None and value > maximum:
        raise CoreError("INVALID_ARGUMENT", f"参数超出范围：{name}")
    return value
