"""A Language Server for PQL, over stdio.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.lsp.server import PqlLanguageServer, serve_stdio

__all__ = ["PqlLanguageServer", "serve_stdio"]
