"""Shared AI gateway package.

The gateway is intentionally stateless. Database-backed prompt, pricing and
call-record features can be added independently without coupling every caller
to a new migration set.
"""
