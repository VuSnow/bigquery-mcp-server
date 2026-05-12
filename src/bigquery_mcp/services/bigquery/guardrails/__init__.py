"""Guardrails package — security pipeline for query execution."""
from .security_validator import SecurityValidator
from .query_rewriter import QueryRewriter
from .rate_limiter import RateLimiter
from .pii_masker import PIIMasker
from .audit_logger import AuditLogger

__all__ = [
    "SecurityValidator",
    "QueryRewriter",
    "RateLimiter",
    "PIIMasker",
    "AuditLogger",
    "GuardrailsPipeline",
]


class GuardrailsPipeline:
    """Orchestrates the full guardrails pipeline for query execution.

    Pipeline steps (all optional, configurable):
    1. Rate limit check
    2. Security validation (forbidden keywords, injection)
    3. Query rewrite (auto LIMIT, cap max LIMIT)
    4. [Execute happens outside pipeline]
    5. PII masking on results
    6. Audit logging
    """

    def __init__(self, guardrails_config: dict, pii_rules: list) -> None:
        """Initialize pipeline from YAML config.

        Args:
            guardrails_config: The guardrails section from config.yaml.
            pii_rules: The pii section from config.yaml.
        """
        self._config = guardrails_config

        # Rate limiter
        rate_config = guardrails_config.get("rate_limit", {})
        self._rate_limiter = RateLimiter(
            max_calls=rate_config.get("max_calls", 100),
            window_seconds=rate_config.get("window_seconds", 3600),
        )

        # PII masker
        self._pii_masker = PIIMasker(pii_rules)

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter

    def pre_execute(self, query: str, connection: str) -> dict:
        """Run pre-execution guardrails (rate limit → security → rewrite).

        Returns:
            {"allowed": True, "query": rewritten_query, "modifications": [...]}
            OR {"allowed": False, "error": "...", "stage": "..."}
        """
        # 1. Rate limit
        rate_check = self._rate_limiter.check()
        if not rate_check["allowed"]:
            AuditLogger.log_blocked(
                query=query, connection=connection,
                reason="Rate limit exceeded", stage="rate_limit",
            )
            return {
                "allowed": False,
                "error": f"Rate limit exceeded. Try again in {rate_check['reset_in_seconds']}s.",
                "stage": "rate_limit",
            }

        # 2. Security validation
        max_length = self._config.get("max_query_length", 10_000)
        sec_result = SecurityValidator.validate(query, max_length=max_length)
        if not sec_result["valid"]:
            AuditLogger.log_blocked(
                query=query, connection=connection,
                reason=sec_result["error"], stage="security_validator",
            )
            return {
                "allowed": False,
                "error": sec_result["error"],
                "stage": "security_validator",
            }

        # 3. Query rewrite
        default_limit = self._config.get("default_limit", 100)
        max_limit = self._config.get("max_limit", 1000)
        rewrite_result = QueryRewriter.rewrite(
            query, default_limit=default_limit, max_limit=max_limit,
        )

        # Record the call after passing all checks
        self._rate_limiter.record()

        return {
            "allowed": True,
            "query": rewrite_result["rewritten_query"],
            "modifications": rewrite_result["modifications"],
        }

    def post_execute(self, rows: list, connection: str, query: str, modifications: list) -> dict:
        """Run post-execution guardrails (PII masking → audit log).

        Returns:
            {"rows": masked_rows, "masked_fields": [...], "audit": record}
        """
        # 5. PII masking
        pii_result = self._pii_masker.mask_rows(rows)
        masked_fields = pii_result["masked_fields"]
        if pii_result["modifications"] > 0:
            modifications.append(f"PII masked: {', '.join(masked_fields)}")

        # 6. Audit log
        audit_record = AuditLogger.log_query(
            query=query,
            connection=connection,
            status="ok",
            rows_returned=len(rows),
            modifications=modifications,
            masked_fields=masked_fields,
        )

        return {
            "rows": pii_result["rows"],
            "masked_fields": masked_fields,
            "audit": audit_record,
        }
