-- Prama — authoritative SQLite schema.
-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
--
-- THIS FILE IS THE AUTHORITY FOR SQLITE. There are no migrations, by design.
-- `prama db init` applies this file idempotently; `prama db verify` compares the
-- live database against it and FAILS LOUDLY on drift rather than repairing it,
-- because a schema that has diverged is a fact an operator must decide about.
--
-- schema/postgres.sql is the same logical schema for PostgreSQL. A change goes
-- into both files in the same commit; tests/db/test_schema.py fails if the two
-- ever differ by anything other than this header.
--
-- Wave 1 covers platform tables only. The semantic layer (dataset, attribute,
-- concept, relationship, journey, binding, connection) arrives in Wave 2.
--
-- ---------------------------------------------------------------------------
-- PORTABLE TYPE SET
--
-- Only four column types appear anywhere in Prama's schema, because only these
-- mean the same thing in PostgreSQL and SQLite:
--
--   VARCHAR(n)  bounded strings. PostgreSQL enforces the width; SQLite records
--               it as TEXT affinity. The width is documentation that costs
--               nothing on one engine and is a real constraint on the other.
--   TEXT        unbounded strings: JSON documents, descriptions, free text.
--   INTEGER     whole numbers, and booleans as 0/1 with a CHECK constraint.
--   REAL        floating point.
--
-- Deliberately NOT used, and why:
--   BOOLEAN      PostgreSQL has a real type; SQLite does not. INTEGER 0/1 with
--                a CHECK is identical on both and never surprises a caller.
--   TIMESTAMP /  SQLite has no date type. ISO-8601 UTC text sorts
--   DATETIME     lexicographically in exactly chronological order, so ranges,
--                ordering and indexes behave the same on both engines. Storing
--                a timestamp as VARCHAR(32) is what lets the two schema files
--                be byte-identical instead of "the same except for six lines".
--   JSONB        Faster and indexable in PostgreSQL, absent in SQLite. TEXT
--                keeps one semantics; PostgreSQL indexing, where needed later,
--                is added as an expression index, never as a column type change.
--   SERIAL /     Prama mints identifiers client-side as ULIDs, so a worker can
--   AUTOINCREMENT allocate one without a round trip and an idempotent retry can
--                reuse it. A server-side sequence would make both impossible.
--   NUMERIC, BIGINT, UUID, BYTEA, BLOB
--                Accepted by SQLite only as type-affinity hints, so a declared
--                constraint would be enforced on one engine and not the other:
--                the worst kind of difference, because it is invisible in
--                development and load-bearing in production.
--
--   Every PRIMARY KEY column is declared NOT NULL explicitly. PostgreSQL
--   implies it; SQLite does NOT for a non-INTEGER primary key and would happily
--   store a NULL id.
--
-- The consequence is that schema/sqlite.sql and schema/postgres.sql are
-- byte-identical apart from this header. That is the objective: one logical
-- schema, verifiable by comparison, with no dialect-dependent behaviour for
-- anything above prama/db/dialects.py to reason about.
-- ---------------------------------------------------------------------------
--
-- Naming conventions (adopted from DishtaYantra, which proved them):
--   uq_<table>_<cols>   unique constraint      ix_<table>_<cols>   index
--   ck_<table>_<rule>   check constraint       fk implied by REFERENCES
--
-- Column width conventions:
--   VARCHAR(26)   a ULID identifier              VARCHAR(32)   an enum, a version
--   VARCHAR(32)   an ISO-8601 UTC timestamp      VARCHAR(64)   a code, a hash prefix
--   VARCHAR(128)  a name or key                  VARCHAR(255)  a display string
--   VARCHAR(320)  an email address (RFC 5321)    VARCHAR(512)  a password hash
--   TEXT          JSON, descriptions, free text

-- ---------------------------------------------------------------------------
-- schema_state: what this database believes it is.
-- Not a migration table. It records the digest of the schema file that was
-- applied, so drift between file and database is detectable without guessing.
-- Exactly one row.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_state (
    id               INTEGER       NOT NULL PRIMARY KEY,
    schema_version   VARCHAR(32)   NOT NULL,
    dialect          VARCHAR(16)   NOT NULL,
    file_digest      VARCHAR(64)   NOT NULL,
    applied_at       VARCHAR(32)   NOT NULL,
    applied_by       VARCHAR(255)  NOT NULL,
    product_version  VARCHAR(32)   NOT NULL,
    CONSTRAINT ck_schema_state_singleton CHECK (id = 1),
    CONSTRAINT ck_schema_state_dialect   CHECK (dialect IN ('sqlite', 'postgres'))
);

-- ---------------------------------------------------------------------------
-- tenant: the isolation boundary. Present from the first table, because
-- retrofitting multi-tenancy is the one thing that cannot be done later.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant (
    id             VARCHAR(26)   NOT NULL PRIMARY KEY,
    slug           VARCHAR(128)  NOT NULL,
    display_name   VARCHAR(255)  NOT NULL,
    status         VARCHAR(32)   NOT NULL DEFAULT 'active',
    residency      VARCHAR(64),
    settings_json  TEXT          NOT NULL DEFAULT '{}',
    created_at     VARCHAR(32)   NOT NULL,
    updated_at     VARCHAR(32)   NOT NULL,
    CONSTRAINT uq_tenant_slug  UNIQUE (slug),
    CONSTRAINT ck_tenant_status CHECK (status IN ('active', 'suspended', 'retired'))
);

-- ---------------------------------------------------------------------------
-- principal: a human or a service account.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS principal (
    id             VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id      VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    username       VARCHAR(128)  NOT NULL,
    email          VARCHAR(320),
    display_name   VARCHAR(255)  NOT NULL,
    kind           VARCHAR(32)   NOT NULL DEFAULT 'human',
    status         VARCHAR(32)   NOT NULL DEFAULT 'active',
    external_id    VARCHAR(255),
    external_idp   VARCHAR(64),
    password_hash  VARCHAR(512),
    last_login_at  VARCHAR(32),
    created_at     VARCHAR(32)   NOT NULL,
    updated_at     VARCHAR(32)   NOT NULL,
    CONSTRAINT uq_principal_tenant_username UNIQUE (tenant_id, username),
    CONSTRAINT ck_principal_kind   CHECK (kind IN ('human', 'service')),
    CONSTRAINT ck_principal_status CHECK (status IN ('active', 'disabled', 'locked'))
);
CREATE INDEX IF NOT EXISTS ix_principal_tenant_status ON principal (tenant_id, status);

-- ---------------------------------------------------------------------------
-- role and principal_role: RBAC. Permissions are a JSON array of grant strings;
-- ABAC conditions arrive with the policy service in a later wave.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS role (
    id                VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id         VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    name              VARCHAR(128)  NOT NULL,
    description       TEXT          NOT NULL DEFAULT '',
    permissions_json  TEXT          NOT NULL DEFAULT '[]',
    is_builtin        INTEGER       NOT NULL DEFAULT 0,
    created_at        VARCHAR(32)   NOT NULL,
    updated_at        VARCHAR(32)   NOT NULL,
    CONSTRAINT uq_role_tenant_name UNIQUE (tenant_id, name),
    CONSTRAINT ck_role_is_builtin  CHECK (is_builtin IN (0, 1))
);

CREATE TABLE IF NOT EXISTS principal_role (
    principal_id  VARCHAR(26)   NOT NULL REFERENCES principal (id) ON DELETE CASCADE,
    role_id       VARCHAR(26)   NOT NULL REFERENCES role (id) ON DELETE CASCADE,
    granted_at    VARCHAR(32)   NOT NULL,
    granted_by    VARCHAR(26),
    PRIMARY KEY (principal_id, role_id)
);
CREATE INDEX IF NOT EXISTS ix_principal_role_role ON principal_role (role_id);

-- ---------------------------------------------------------------------------
-- api_key: only the hash is stored. The plaintext is shown once, at creation.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_key (
    id            VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id     VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    principal_id  VARCHAR(26)   NOT NULL REFERENCES principal (id) ON DELETE CASCADE,
    name          VARCHAR(128)  NOT NULL,
    key_prefix    VARCHAR(32)   NOT NULL,
    key_hash      VARCHAR(128)  NOT NULL,
    scopes_json   TEXT          NOT NULL DEFAULT '[]',
    expires_at    VARCHAR(32),
    last_used_at  VARCHAR(32),
    revoked_at    VARCHAR(32),
    created_at    VARCHAR(32)   NOT NULL,
    created_by    VARCHAR(26),
    CONSTRAINT uq_api_key_prefix UNIQUE (key_prefix)
);
CREATE INDEX IF NOT EXISTS ix_api_key_principal ON api_key (principal_id);

-- ---------------------------------------------------------------------------
-- audit_event: append-only. Nothing in the platform issues UPDATE or DELETE
-- against this table; retention is enforced by archival, never by mutation.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_event (
    id              VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id       VARCHAR(26)   NOT NULL,
    occurred_at     VARCHAR(32)   NOT NULL,
    actor_id        VARCHAR(26),
    actor_kind      VARCHAR(32)   NOT NULL DEFAULT 'human',
    action          VARCHAR(64)   NOT NULL,
    object_kind     VARCHAR(64)   NOT NULL,
    object_id       VARCHAR(64),
    outcome         VARCHAR(32)   NOT NULL DEFAULT 'success',
    correlation_id  VARCHAR(64),
    source_ip       VARCHAR(64),
    detail_json     TEXT          NOT NULL DEFAULT '{}',
    CONSTRAINT ck_audit_actor_kind CHECK (actor_kind IN ('human', 'service', 'system', 'agent')),
    CONSTRAINT ck_audit_outcome    CHECK (outcome IN ('success', 'failure', 'denied'))
);
CREATE INDEX IF NOT EXISTS ix_audit_tenant_time ON audit_event (tenant_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_audit_object      ON audit_event (object_kind, object_id);
CREATE INDEX IF NOT EXISTS ix_audit_actor       ON audit_event (actor_id, occurred_at);

-- ---------------------------------------------------------------------------
-- lease: single-writer coordination across the fleet.
-- fencing_token increases strictly per resource, so a superseded holder's
-- writes can be rejected downstream rather than merely discouraged. Releasing
-- a lease expires the row; it never deletes it, because deleting would reset
-- the token and a fencing token that can go backwards protects nothing.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lease (
    resource       VARCHAR(255)  NOT NULL PRIMARY KEY,
    holder         VARCHAR(255)  NOT NULL,
    token          VARCHAR(26)   NOT NULL,
    fencing_token  INTEGER       NOT NULL DEFAULT 1,
    acquired_at    VARCHAR(32)   NOT NULL,
    expires_at     VARCHAR(32)   NOT NULL,
    metadata_json  TEXT          NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_lease_expires ON lease (expires_at);

-- ---------------------------------------------------------------------------
-- setting: runtime configuration that outlives a process and belongs to a
-- tenant. Never a substitute for config/application.yaml, which holds the
-- deployment's own settings; this is for values a user changes in the product.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS setting (
    tenant_id   VARCHAR(26)   NOT NULL,
    scope       VARCHAR(128)  NOT NULL DEFAULT 'global',
    key         VARCHAR(128)  NOT NULL,
    value_json  TEXT          NOT NULL,
    updated_at  VARCHAR(32)   NOT NULL,
    updated_by  VARCHAR(26),
    PRIMARY KEY (tenant_id, scope, key)
);
