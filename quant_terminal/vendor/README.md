# vendor/

Read-only mirror of upstream code. **Do not modify files in this directory.**

## legacy_squeeze/

Verbatim copy of `Short Squeeze (Legacy Intouch)/short-squeeze-scanner-main/`.

Pillar-based short-squeeze scoring engine (Finviz screening + EDGAR 13F + yfinance
options flow + technical signals). Source: separate standalone project.

Integration: see [src/scanners/legacy_pipeline.py](../src/scanners/legacy_pipeline.py)
for the adapter that wraps this code into our DataFrame-first idiom.
