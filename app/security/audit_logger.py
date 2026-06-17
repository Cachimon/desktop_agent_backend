from app.utils.trace import get_trace_id


async def record_audit(
    session,
    operation: str,
    details: dict | None = None,
    ip_address: str | None = None,
    user_id: str | None = None,
    risk_level: str | None = None,
    status: str | None = None,
) -> None:
    from app.repositories.audit_repo import AuditRepo
    repo = AuditRepo(session)
    await repo.record(
        operation=operation,
        details=details,
        ip_address=ip_address,
        user_id=user_id,
        trace_id=get_trace_id(),
        risk_level=risk_level,
        status=status,
    )
