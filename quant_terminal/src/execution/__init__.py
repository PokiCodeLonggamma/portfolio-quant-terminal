"""Execution / OMS layer.

Paper-mode by default. Live mode requires `EXECUTION_ALLOW_LIVE=1` AND
`APCA_API_BASE_URL=https://api.alpaca.markets` (i.e. the live endpoint),
otherwise the broker wrapper forces paper.
"""
