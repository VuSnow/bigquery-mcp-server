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
        r"\bload_file\b", r"\binto_dumpfile\b", r"\binto_outline\b",
        r"\bbenchmark\b", r"\bsleep\b", r"\bwaitfor\b", r"\bpg_sleep\b"
    ]
    
    @classmethod
    def _remove_comments(cls, query: str) -> str:
        """Remove SQL comments (-- line and /* block */) before validation."""
        # Remove block comments /* ... */ (non-greedy, handles multiline)
        q = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)
        # Remove line comments -- ...
        q = re.sub(r"--[^\n]*", " ", q)
        # Remove # line comments (MySQL style, rare but possible)
        q = re.sub(r"#[^\n]*", " ", q)
        return q

    @classmethod
    def _remove_string_literals(cls, query: str) -> str:
        """Remove string literals, handling escaped/doubled quotes."""
        # Handle doubled quotes: 'it''s ok' or "she said ""hi"""
        q = re.sub(r"'(?:[^']|'')*'", "''", query)
        q = re.sub(r'"(?:[^"]|"")*"', '""', q)
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
        
        stripped = cls._remove_comments(cls._remove_string_literals(query_clean)).lower()
        for kw in cls.FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{re.escape(kw)}\b", stripped):
                return {"valid": False, "error": f"Forbidden operation: '{kw}'."}
            
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE | re.DOTALL):
                return {"valid": False, "error": f"Suspicious pattern detected."}
            
        for pattern in cls.DANGEROUS_FUNCTIONS:
            if re.search(pattern, stripped, re.IGNORECASE):
                return {"valid": False, "error": "Dangerous function detected."}
        
        return {"valid": True, "sanitized_query": query_clean}
            