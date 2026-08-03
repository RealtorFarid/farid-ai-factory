"""LLM routing — Phase 2.

Will wrap LiteLLM to provide model fallback, cost accounting and rate limiting.
Today the model is resolved from ``Settings.default_model`` in
:mod:`backend.runtime.agent`.
"""
