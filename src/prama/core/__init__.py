"""Prama core primitives: configuration, identity, time, errors, logging,
plugin registry and structured concurrency.

Nothing in this package performs I/O against a customer data source and nothing
imports SQLAlchemy; that confinement is what makes the layering testable.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
