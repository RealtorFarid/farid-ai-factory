"""Memory — Phase 2.

Will provide session memory and semantic recall backed by PostgreSQL +
pgvector. Runs are currently stateless: ``session_id`` is accepted and logged
but not yet persisted.
"""
