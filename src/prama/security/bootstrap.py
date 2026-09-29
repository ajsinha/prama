"""The bootstrap administrator: a way in on a fresh installation.

On an empty installation Prama creates an estate called ``default`` (if there is
none) and, in it, ``admin`` with the password ``prama-dev-admin`` and the
built-in ``admin`` role. That makes a new clone usable in one step, which is
what `prama serve` on a laptop needs.

A known password is a speed bump, not a door, and it is treated as one:

* **It is said out loud.** A warning in the log at every start while it is in
  use, a banner in the console for whoever signs in with it, and a gauge,
  ``prama_default_admin_password``, a dashboard can alert on.
* **It refuses to start outside development.** When ``app.environment`` is
  ``staging`` or ``production`` and the password is still the default, the
  application will not start unless ``security.allow_default_admin_password``
  is set, deliberately.
* **It is created once.** Only when the estate has no principal at all; a
  deleted or renamed admin is never recreated behind the operator's back.

``security.bootstrap_admin: false`` turns the whole thing off.

Adopted from Maya, which ships ``admin`` / ``maya-dev-admin`` on the same terms.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.core.errors import ConfigError
from prama.core.log import get_logger
from prama.telemetry.metrics import REGISTRY

_log = get_logger(__name__)

USERNAME = "admin"
DEFAULT_PASSWORD = "prama-dev-admin"
DEFAULT_TENANT = "default"
#: Environments in which the default password may be in use.
PERMISSIVE = frozenset({"development", "test"})

ACTIVE = REGISTRY.gauge(
    "prama_default_admin_password",
    "1 while the bootstrap admin still has the shipped password.",
)


async def seed(uow: Any, config: Any) -> str | None:
    """Create the default estate and the admin if the installation is empty.

    Returns the admin's principal id when one was created, else None.
    """
    if not config.get_bool("security.bootstrap_admin", True):
        return None
    tenant_id = await _tenant(uow, config)
    if tenant_id is None or await uow.principals.any_for(tenant_id):
        return None
    from prama.security.accounts import grant_roles

    principal = uow.principals.create(
        tenant_id=tenant_id, username=USERNAME, display_name="Administrator"
    )
    uow.principals.set_password(principal, DEFAULT_PASSWORD)
    await uow.flush()
    await grant_roles(uow, tenant_id, principal, ["admin"])
    _log.warning(
        "created the bootstrap admin: sign in as %s / %s and change the password",
        USERNAME,
        DEFAULT_PASSWORD,
    )
    return str(principal.id)


async def default_password_active(uow: Any, config: Any) -> bool:
    """Whether the bootstrap admin still has the shipped password."""
    tenant_id = await _tenant(uow, config, create=False)
    if tenant_id is None:
        return False
    admin = await uow.principals.by_username(tenant_id, USERNAME)
    active = admin is not None and uow.principals.has_password(admin, DEFAULT_PASSWORD)
    ACTIVE.set(1 if active else 0)
    return active


def refuse_outside_development(active: bool, config: Any) -> None:
    """Refuse to start with the default password where it must not be used."""
    environment = str(config.get("app.environment", "development") or "development")
    if not active:
        return
    if environment not in PERMISSIVE and not config.get_bool(
        "security.allow_default_admin_password", False
    ):
        raise ConfigError(
            f"the admin still has the default password, and this is {environment}",
            remedy=(
                "Sign in as admin and change the password on the My account page "
                "(/account). To start anyway, set "
                "security.allow_default_admin_password: true, knowingly."
            ),
            context={"environment": environment},
        )
    _log.warning(
        "the bootstrap admin still uses the default password %r: change it now",
        DEFAULT_PASSWORD,
    )


async def _tenant(uow: Any, config: Any, *, create: bool = True) -> str | None:
    """The estate the admin belongs to: the configured one, the only one, or a new one."""
    configured = str(config.get("tenancy.default_tenant", "") or "").strip()
    if configured:
        found = await uow.tenants.get(configured) or await uow.tenants.by_slug(configured)
        return str(found.id) if found is not None else None
    estates = await uow.tenants.list_active(limit=2)
    if len(estates) == 1:
        return str(estates[0].id)
    if estates or not create:
        return None  # several estates and none named: not ours to choose
    tenant = uow.tenants.create(slug=DEFAULT_TENANT, display_name="Default estate")
    await uow.flush()
    return str(tenant.id)
