"""Investigator V1 bounded context.

Phase 0 intentionally exposes only the executable authority contract.  It has
no HTTP entry point, scoring dependency, lending command, or money capability.
"""

from .authority import AuthorityDenied, is_allowed, require_capability

__all__ = ["AuthorityDenied", "is_allowed", "require_capability"]
