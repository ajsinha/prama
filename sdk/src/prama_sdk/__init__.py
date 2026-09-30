"""The Prama Python SDK: everything Prama does, from Python.

    import prama_sdk as prama

    client = prama.connect()                  # the server config/application.yaml names
    client = prama.connect(username="admin", password="…")
    for dataset in client.datasets.list():
        print(dataset["name"])

``connect`` finds the running server from the same configuration the server
reads, so a script, a notebook and a case study all talk to *your* Prama rather
than starting one of their own. Every endpoint of the HTTP API has a method
here, and ``tests/sdk/test_parity.py`` fails the build if one does not.

Installed on its own (``pip install prama-sdk``): it depends on ``httpx`` and
``PyYAML`` and never imports the server, so a client machine needs nothing of
Prama but this.

Errors follow Prama's taxonomy (`prama_sdk.errors`): a refusal raises the class
for the server's error code, with its message, remedy and correlation id; a
server that does not answer raises `ServerUnavailable`.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama_sdk.client import AsyncClient, Client, connect
from prama_sdk.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PramaError,
    RateLimitedError,
    ServerError,
    ServerUnavailable,
    UnauthorisedError,
    ValidationError,
)
from prama_sdk.locate import server_url
from prama_sdk.version import VERSION

__version__ = VERSION

__all__ = [
    "AsyncClient",
    "Client",
    "ConflictError",
    "ForbiddenError",
    "NotFoundError",
    "PramaError",
    "RateLimitedError",
    "ServerError",
    "ServerUnavailable",
    "UnauthorisedError",
    "ValidationError",
    "__version__",
    "connect",
    "server_url",
]
