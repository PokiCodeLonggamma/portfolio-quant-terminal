"""Cluster 1 — SEC / EDGAR data + filings + government / capex feeds.

All modules go through `edgar_client` for SEC HTTP so the User-Agent / throttle
contract is enforced in one place. Public entry points are re-exported here
for convenience but consumers are encouraged to import the leaf module.
"""
from __future__ import annotations
