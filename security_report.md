# Security Vulnerability Report

After a thorough audit of the entire codebase, here are the vulnerabilities found, categorized by severity:

---

## CRITICAL

### 1. IP Anomaly Detection SQL Query Missing IP Filter — Complete Bypass

**File:** `app/repositories/auth_repo.py:143-152`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
async def count_emails_for_ip(self, ip_address: str, window_hours: int = 1) -> int:
    stmt = select(func.count(VerificationCode.email.distinct())).select_from(VerificationCode).where(
        and_(
            VerificationCode.created_at >= window_start,
        )
    )
```

The `ip_address` parameter is **never used** in the WHERE clause. This means the query counts **all distinct emails globally**, not for the specific IP. An attacker can send unlimited verification codes from any IP and will never trigger `IP_ANOMALY_EMAIL_THRESHOLD` (which is designed to block them). The entire IP anomaly detection is completely non-functional.

---

### 2. Sandbox Command Execution — No Real Sandboxing, Trivial Bypass

**File:** `app/tools/sandbox.py:62-94`

`execute_sandboxed()` runs commands via `asyncio.create_subprocess_exec` with **no OS-level isolation** (no container, no chroot, no seccomp, no user namespace). The "sandbox" config values `SANDBOX_CPU_LIMIT_PERCENT` and `SANDBOX_MEMORY_LIMIT_MB` are defined but **never enforced** — they're dead configuration. Only a timeout exists.

Additionally, the `shell_guard.py` whitelist is easily bypassed:

- **Command chaining:** `ls && rm -rf /home` — the regex `^ls\b` matches the start, but the rest executes freely.
- **Semicolons:** `ls; cat /etc/passwd` — same issue.
- **Subshells:** `ls$(rm -rf /)` — `^ls\b` matches, but the subshell executes.
- **Newlines:** `ls\nrm -rf /` — not stripped before matching.
- **Backticks:** `` ls`rm -rf /` `` — same subshell issue.

---

### 3. Path Traversal Check Uses Resolved Path but Checks Raw String

**File:** `app/security/path_validator.py:49-50`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
if ".." in str(path):
    return PathSecurityLevel.FORBIDDEN, "Path traversal is forbidden"
```

This checks the **raw input string** for `..`, but the actual path used is `resolved = Path(path).resolve()` (line 35). On Windows, `Path("C:\\Users\\..\\Windows")` resolves to `C:\Windows` — the `..` check catches this. However, **symlinks** can bypass this: create a symlink `~/mylink -> /etc`, then access `~/mylink/shadow` — no `..` in the string, and the symlink check on line 53 only applies if the **final resolved path itself** is a symlink, not intermediate components. More critically, **junction points on Windows** are not detected by `is_symlink()`.

---

## HIGH

### 4. IP Address Spoofing — No Proxy Header Validation

**File:** `app/routers/auth.py:25,38`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
client_ip = request.client.host if request.client else "unknown"
```

`request.client.host` returns the direct TCP connection IP. If the app is behind a reverse proxy (nginx, cloud load balancer), this is always the proxy IP, not the real client. Attackers behind the same proxy share one IP and can collectively exhaust rate limits. More importantly, there's **no X-Forwarded-For handling**, meaning rate limiting by IP is ineffective in production deployments.

---

### 5. Reserved Endpoints Exposed Without Authentication

**File:** `app/routers/reserved.py:13-61`

All reserved endpoints (`/mcp/servers`, `/mcp/tools`, `/agents/sub`, `/search/semantic`, `/files/organize`, `/tasks`) have **no `Depends(get_current_user)`**. While they currently throw `NotImplementError`, when they are implemented in future phases, there's a risk they'll be deployed without auth. The `/files/organize` endpoint is particularly dangerous — it implies file system operations with zero auth.

---

### 6. No Authorization — Any Authenticated User Can Access Any Other User's Audit Logs

**File:** `app/routers/tools.py:12-36`

The `/tools/calls` endpoint only requires authentication but **does not filter by `user_id`**. Any authenticated user can query **all** audit logs for all users, potentially leaking other users' operation details, email addresses (in details), and behavioral patterns.

---

### 7. Conversation Ownership Check Uses String Comparison on user_id

**File:** `app/services/chat_service.py:33`, `app/services/conversation_service.py:41`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
if not conv or conv.user_id != user_id:
```

`user_id` comes from `user["sub"]` (JWT payload, which is a string), but `conv.user_id` is stored as whatever type the DB returns. If there's a type mismatch (e.g., `1` vs `"1"`), the check could fail open or closed unpredictably. In `conversation_service.py:26`, `user_id` is stored as a string UUID via `str(uuid.uuid4())`, but in `chat_service.py:33`, the comparison `conv.user_id != user_id` compares against the JWT `sub` which is `str(user.id)` — an integer cast to string. This is a type confusion risk.

---

### 8. CSRF Protection is Weak — Only Checks Header Existence

**File:** `app/middleware/auth.py:33-36`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
async def validate_csrf(request: Request) -> None:
    x_requested_with = request.headers.get("X-Requested-With")
    if not x_requested_with:
        raise CSRFValidationFailed(...)
```

This only checks that the header **exists**, not its **value**. An attacker can set `X-Requested-With: anything` and bypass CSRF protection. A proper CSRF implementation should use a cryptographic token that's verified against a server-side secret or cookie.

---

### 9. Refresh Token in Response Body Leaks to JS

**File:** `app/services/auth_service.py:130`, `app/routers/auth.py:41`

The login endpoint returns `refresh_token` in the JSON response body **and** sets it as an HttpOnly cookie. The `result.pop("refresh_token")` in the router removes it, but the `refresh_token` endpoint at line 74 also does `result.pop("refresh_token")` — however, the `auth_service.refresh_token()` returns the new refresh token in the dict (line 166). If any code path fails to pop it, the refresh token is exposed to JavaScript, defeating the purpose of HttpOnly cookies.

---

## MEDIUM

### 10. `datetime.utcnow()` Deprecated — Time Zone Issues

**Files:** `auth_service.py:53,108`, `rate_limiter.py:21,45,66,98,117`, `auth_repo.py:32,50,57,64,82,91,127,136,144`, `models/user_auth.py:30,45,61`, `models/base.py:25-26`

All datetime comparisons use `datetime.utcnow()` (naive datetime), but `token.py:11,16` uses `datetime.now(timezone.utc)` (aware datetime). Mixing naive and aware datetimes can cause `TypeError` in Python 3.12+ or incorrect comparisons. Also, `datetime.utcnow()` is deprecated since Python 3.12.

---

### 11. JWT Key File Read on Every Request — No Caching + Path Traversal Risk

**File:** `app/security/token.py:19-22,27-29`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
with open(private_key_path, "r") as f:
    private_key = f.read()
```

The RSA keys are read from disk on **every single token creation/verification**. If `JWT_PRIVATE_KEY_PATH` is configurable via env, an attacker who can modify env vars could point it to `/etc/passwd` or any file. There's no validation that the path points to a valid PEM key file. Also, the performance impact of file I/O on every request is significant.

---

### 12. No Rate Limiting on Login Endpoint

**File:** `app/routers/auth.py:30-51`

The `/auth/login` endpoint calls `check_account_lockout()` but **does not call `check_ip_rate_limit()`**. An attacker can brute-force verification codes at high speed from a single IP (only limited by account lockout, which is per-email). By rotating emails, an attacker can make unlimited login attempts.

---

### 13. Skill Toggle is Global, Not Per-User

**File:** `app/services/skill_service.py:101-111`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
_skills_registry[name]["enabled"] = enabled
```

The `_skills_registry` is a module-level dict shared across all requests. When any user toggles a skill, it affects **all users**. There's no per-user skill state.

---

### 14. Chat Stream Memory Leak — Locks Never Cleaned Up

**File:** `app/services/chat_service.py:16,36-37`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
_active_streams: dict[str, asyncio.Lock] = {}
```

Locks are added to `_active_streams` but **never removed**. Over time, this dict grows unboundedly, leaking memory for every conversation that ever had a stream.

---

### 15. Verification Code Not Invalidated After Successful Login

**File:** `app/services/auth_service.py:96`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
await repo.mark_code_used(vc.id)
```

While the code is marked as "used" (`used_at` set), the `get_latest_valid_code` query filters by `used_at.is_(None)`, so it won't be reused. However, there's a **race condition**: if two concurrent login requests arrive with the same code, both could pass the `used_at is None` check before either marks it used. The `mark_code_used` and `increment_code_attempts` operations are not atomic with the verification check.

---

### 16. Error Messages Leak Internal State

**File:** `app/security/shell_guard.py:45-47`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
raise SecurityError(message=f"Command is forbidden for security reasons: {stripped[:50]}")
```

Error messages include the first 50 characters of the rejected command. In `path_validator.py:41`, forbidden path reasons include the actual path. This leaks server directory structure and file paths to attackers.

---

## LOW

### 17. CORS Allows Wildcard Subdomains

**File:** `app/config.py:84`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
CORS_ORIGINS: list[str] = ["http://localhost:*", "electron://*"]
```

`http://localhost:*` allows any port on localhost. If any service on localhost has a XSS vulnerability, it can make authenticated requests to this API.

---

### 18. Swagger/OpenAPI Docs Enabled in Production

**File:** `app/main.py:33-35`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json"
```

API documentation is always available regardless of `DEBUG` mode. This exposes the full API surface to attackers.

---

### 19. No Input Length Limit on Chat Message

**File:** `app/schemas/chat.py:7-10`

![](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/comon/.vscode/extensions/huaweicloud.vscode-codebot-26.5.2-win32-x64/dist/file-icons/default.svg)

python

 

```python
class ChatStreamRequest(BaseModel):
    message: str
```

The `message` field has no `max_length` constraint. An attacker can send extremely large messages, potentially causing memory issues or overwhelming the LLM API.

---

### 20. Generic Exception Handler Swallows Trace Details

**File:** `app/main.py:75-87`

The generic exception handler returns a generic message but logs `str(exc)`. If the exception contains sensitive info (file paths, SQL queries, stack traces), it's logged but not returned to the client — this is actually correct. However, the `str(e)` in streaming error responses (`streaming.py:46`) **does** send exception details to the client via SSE.

---

### Summary Table

|#|Severity|Category|File|Issue|
|---|---|---|---|---|
|1|CRITICAL|Logic|auth_repo.py:143|IP anomaly query missing IP filter — completely bypassed|
|2|CRITICAL|Security|sandbox.py, shell_guard.py|No real sandboxing; command whitelist trivially bypassed|
|3|CRITICAL|Security|path_validator.py:49|Path traversal via symlinks/junctions bypasses `..` check|
|4|HIGH|Request|auth.py:25|IP spoofing — no proxy header validation|
|5|HIGH|Auth|reserved.py|Reserved endpoints have no authentication|
|6|HIGH|Auth|tools.py:12|Audit logs accessible by any authenticated user|
|7|HIGH|Logic|chat_service.py:33|user_id type confusion in ownership check|
|8|HIGH|Security|auth.py:33|CSRF only checks header existence, not value|
|9|HIGH|Security|auth_service.py:130|Refresh token potentially leaked in response body|
|10|MEDIUM|Logic|Multiple files|Mixed naive/aware datetime comparisons|
|11|MEDIUM|Security|token.py:19|JWT key file read every request, no path validation|
|12|MEDIUM|Security|auth.py:30|No IP rate limiting on login endpoint|
|13|MEDIUM|Logic|skill_service.py:101|Skill toggle is global, not per-user|
|14|MEDIUM|Memory|chat_service.py:16|Stream locks never cleaned up — memory leak|
|15|MEDIUM|Race Cond|auth_service.py:96|Concurrent login race condition on verification code|
|16|MEDIUM|Info Leak|shell_guard.py:45|Error messages leak command/path details|
|17|LOW|Config|config.py:84|CORS allows wildcard localhost ports|
|18|LOW|Config|main.py:33|API docs always enabled|
|19|LOW|Validation|chat.py:7|No max_length on chat message|
|20|LOW|Info Leak|streaming.py:46|SSE error responses leak exception details|