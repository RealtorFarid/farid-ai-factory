"""Event bus — Phase 2.

Will carry agent lifecycle events (run started/finished, tool called, approval
requested) to subscribers: the SSE transport, tracing, and the human-in-the-loop
approval gate. Not implemented yet; the API streams directly from the agent.
"""
