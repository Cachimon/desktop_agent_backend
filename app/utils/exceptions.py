from app.utils.trace import get_trace_id


class AppException(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str = "",
        detail: dict | None = None,
        error_code: str | None = None,
        status_code: int | None = None,
    ):
        self.message = message or self.__class__.__doc__ or ""
        self.detail = detail or {}
        if error_code is not None:
            self.error_code = error_code
        if status_code is not None:
            self.status_code = status_code
        self.trace_id = get_trace_id()
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "detail": self.detail,
            "trace_id": self.trace_id,
        }


class SecurityError(AppException):
    status_code = 403
    error_code = "SECURITY_VIOLATION"


class HITLRequiredError(AppException):
    status_code = 200
    error_code = "HITL_REQUIRED"

    def __init__(
        self,
        action: str = "",
        message: str = "",
        context: dict | None = None,
    ):
        self.action = action
        self.context = context or {}
        super().__init__(message=message, detail={"action": action, **self.context})


class ResourceNotFoundError(AppException):
    status_code = 404
    error_code = "RESOURCE_NOT_FOUND"


class ConversationNotFound(ResourceNotFoundError):
    error_code = "CONVERSATION_NOT_FOUND"


class CheckpointNotFound(ResourceNotFoundError):
    error_code = "CHECKPOINT_NOT_FOUND"


class SkillNotFound(ResourceNotFoundError):
    error_code = "SKILL_NOT_FOUND"


class ResourceConflictError(AppException):
    status_code = 409
    error_code = "RESOURCE_CONFLICT"


class ConversationAlreadyExists(ResourceConflictError):
    error_code = "CONVERSATION_ALREADY_EXISTS"


class ConversationBusy(ResourceConflictError):
    error_code = "CONVERSATION_BUSY"


class CheckpointExpired(ResourceConflictError):
    error_code = "CHECKPOINT_EXPIRED"


class WorkspaceAlreadyExists(ResourceConflictError):
    error_code = "WORKSPACE_ALREADY_EXISTS"


class ValidationError(AppException):
    status_code = 400
    error_code = "VALIDATION_ERROR"


class InvalidPagination(ValidationError):
    error_code = "INVALID_PAGINATION"


class AuthenticationError(AppException):
    status_code = 401
    error_code = "AUTHENTICATION_ERROR"


class NotAuthenticated(AuthenticationError):
    error_code = "NOT_AUTHENTICATED"


class InvalidCode(AuthenticationError):
    error_code = "INVALID_CODE"


class CodeAlreadyUsed(AuthenticationError):
    error_code = "CODE_ALREADY_USED"


class CodeMaxAttemptsExceeded(AuthenticationError):
    error_code = "CODE_MAX_ATTEMPTS_EXCEEDED"


class InvalidRefreshToken(AuthenticationError):
    error_code = "INVALID_REFRESH_TOKEN"


class TokenReuseDetected(AuthenticationError):
    error_code = "TOKEN_REUSE_DETECTED"


class RateLimitError(AppException):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"


class RateLimitExceeded(RateLimitError):
    error_code = "RATE_LIMIT_EXCEEDED"


class IPRateLimitExceeded(RateLimitError):
    error_code = "IP_RATE_LIMIT_EXCEEDED"


class AccountLocked(RateLimitError):
    error_code = "ACCOUNT_LOCKED"


class AnomalousIPDetected(RateLimitError):
    error_code = "ANOMALOUS_IP_DETECTED"


class AgentError(AppException):
    status_code = 422
    error_code = "AGENT_ERROR"


class CheckpointCorrupted(AgentError):
    error_code = "CHECKPOINT_CORRUPTED"


class CSRFError(AppException):
    status_code = 403
    error_code = "CSRF_VALIDATION_FAILED"


class CSRFValidationFailed(CSRFError):
    error_code = "CSRF_VALIDATION_FAILED"


class NotImplementError(AppException):
    status_code = 501
    error_code = "NOT_IMPLEMENTED"


class PathForbiddenError(SecurityError):
    error_code = "PATH_FORBIDDEN"


class EmailSendFailed(AppException):
    status_code = 503
    error_code = "EMAIL_SEND_FAILED"
