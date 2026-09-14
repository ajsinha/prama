"""Shared helpers for the round-4 language harnesses.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations


def out(cid, result, observed):
    print(f"{cid}: {result} :: {observed}")
