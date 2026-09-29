"""The Prama Python SDK: everything Prama does, from Python.

    import prama.sdk as prama

    client = prama.connect()                  # the server config/application.yaml names
    client = prama.connect(username="admin", password="…")
    for dataset in client.datasets.list():
        print(dataset["name"])

``connect`` finds the running server from the same configuration the server
reads, so a script, a notebook and a case study all talk to *your* Prama rather
than starting one of their own. Every endpoint of the HTTP API has a method
here, and ``tests/sdk/test_parity.py`` fails the build if one does not.

Errors are Prama's own: a refusal raises the `prama.core.errors` class the
server raised, with its message and remedy; a server that does not answer
raises `ServerUnavailable`.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PramaError,
    UnauthorisedError,
    ValidationError,
)
from prama.sdk.client import AsyncClient, Client, connect, server_url
from prama.sdk.transport import ServerUnavailable

__all__ = [
    "AsyncClient",
    "Client",
    "ConflictError",
    "ForbiddenError",
    "NotFoundError",
    "PramaError",
    "ServerUnavailable",
    "UnauthorisedError",
    "ValidationError",
    "connect",
    "server_url",
]
