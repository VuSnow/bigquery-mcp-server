"""Security validator — forbidden keywords, injection patterns, query length."""
from __future__ import annotations

import re
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class SecurityValidator:
    """Validates queries against basic security rules (stateless, no config needed)"""
    
    FORBIDDEN_KEYWORDS = [
        "insert", "update", "delete", "merge", "truncate",
        "create", "drop", "alter", "rename", "grant", "revoke", "set", "use", 
        "call", "execute", "exec", "commit", "rollback", "begin", "start", "export", 
        "cancel", "kill"
    ]
    
    SUSPICIOUS_PATTERNS = [
        r";\s*\w+",
        r"\bload\s+data\b",
        r"\binto\s+outfile\b",
        r"\bscript\b",
        r"\bxp_\w+",
        r"\bsp_\w+",
    ]
    
    DANGEROUS_FUNCTIONS = [
        "load_file", "into_dumpfile", "into_outline",
        "benchmark", "sleep", "waitfor", "pg_sleep"
    ]
    
    @classmethod
    def _remove_string_literals(cls, query: str) -> str:
        q = re.sub(r"'[^']*'", "''", query)
        q = re.sub(r'"[^"]*"', '""', q)
        q = re.sub(r"`[^`]*`", "``", q)
        return q

    @classmethod
    def validate(cls, query: str, max_length: int = 10_000) -> Dict[str, Any]:
        if not query or not query.strip():
            return {"valid": False, "error": "Empty query not allowed."}
        
        query_clean = query.strip()
        if len(query_clean) > max_length:
            return {"valid": False, "error": f"Query too long. Max {max_length} chars."}
        
        query_lower = query_clean.lower()
        allowed_starts = ("select", "with", "show", "describe", "explain")
        if not any(query_lower.startswith(s) for s in allowed_starts):
            return {"valid": False, "error": "Only SELECT/WITH/SHOW/DESCRIBE/EXPLAIN allowed."}
        
        stripped = cls._remove_string_literals(query_clean).lower()
        for kw in cls.FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{re.escape(kw)}\b", stripped):
                return {"valid": False, "error": f"Forbidden operation: '{kw}'."}
            
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE | re.DOTALL):
                return {"valid": False, "error": f"Suspicious pattern detected '{pattern}'."}
            
        if any(f in query_lower for f in cls.DANGEROUS_FUNCTIONS):
            return {"valid": False, "error": f"Dangerous function detected."}
        
        return {"valid": True, "santizied_query": query_clean}
            