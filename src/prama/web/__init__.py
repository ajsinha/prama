"""The Prama user interface.

Server-rendered Jinja on FastAPI, Bootstrap 5 and jQuery, every asset vendored,
no build step — the same stack as DishtaYantra, for the reasons set out in
docs/18 §4 (the reversal of DEC-18).

The package is laid out as DishtaYantra lays its web tier out:

    web/rendering.py     the render / url_for / flash layer templates rely on
    web/routes/*.py      one class per area, registering its own routes
    web/templates/       Jinja, with base.html as the shell
    web/static/          css, js, and vendor/ — nothing fetched at run time

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.web.rendering import flash, redirect_to, render, url_for
from prama.web.webapp import mount_ui

__all__ = ["flash", "mount_ui", "redirect_to", "render", "url_for"]
