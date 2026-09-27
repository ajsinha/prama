-- Prama — authoritative PostgreSQL schema.
-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
--
-- THIS FILE IS THE AUTHORITY FOR POSTGRESQL. There are no migrations, by design.
-- `prama db init` applies this file idempotently; `prama db verify` compares the
-- live database against it and FAILS LOUDLY on drift rather than repairing it,
-- because a schema that has diverged is a fact an operator must decide about.
--
-- schema/sqlite.sql is the same logical schema for SQLite. A change goes
-- into both files in the same commit; tests/db/test_schema.py fails if the two
-- ever differ by anything other than this header.
--
-- Wave 1 covers platform tables. Wave 2 adds the complete semantic layer:
-- domain, dataset, attribute, concept, concept property, relationship,
-- journey, connection and binding — every one of them bitemporal.
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

-- ===========================================================================
-- SEMANTIC LAYER (Wave 2)
--
-- Every declaration is BITEMPORAL, held as an identity row plus a chain of
-- version rows:
--
--   valid_from / valid_to      business time: when the declaration was true
--   recorded_at / superseded_at  system time: when we believed it
--
-- Nothing is ever updated in place. Correcting a mistake supersedes a version;
-- changing a fact closes one validity period and opens another. The two axes
-- are separable because the questions differ: "what was the grain on 31 March?"
-- and "what did we believe the grain was, on 31 March?" have different answers
-- after a correction, and an evidence record from March must resolve against
-- the second.
--
-- The current declaration is  valid_to IS NULL AND superseded_at IS NULL.
-- A partial unique index enforces exactly one current version per entity; the
-- syntax is identical on both engines.
--
-- Foreign keys point at the IDENTITY table, never at a version, so a reference
-- does not have to be rewritten every time a declaration changes.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- sem_domain: a business grouping with an accountable owner.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sem_domain (
    id          VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id   VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    created_at  VARCHAR(32)   NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sem_domain_tenant ON sem_domain (tenant_id);

CREATE TABLE IF NOT EXISTS sem_domain_version (
    id                VARCHAR(26)   NOT NULL PRIMARY KEY,
    domain_id         VARCHAR(26)   NOT NULL REFERENCES sem_domain (id) ON DELETE CASCADE,
    version           INTEGER       NOT NULL,
    valid_from        VARCHAR(32)   NOT NULL,
    valid_to          VARCHAR(32),
    recorded_at       VARCHAR(32)   NOT NULL,
    superseded_at     VARCHAR(32),
    authored_by       VARCHAR(26),
    approved_by       VARCHAR(26),
    approved_at       VARCHAR(32),
    change_reason     TEXT          NOT NULL DEFAULT '',
    name              VARCHAR(255)  NOT NULL,
    description       TEXT          NOT NULL DEFAULT '',
    owner_id          VARCHAR(26),
    parent_domain_id  VARCHAR(26)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sem_domain_current
    ON sem_domain_version (domain_id) WHERE superseded_at IS NULL AND valid_to IS NULL;
CREATE INDEX IF NOT EXISTS ix_sem_domain_version_entity
    ON sem_domain_version (domain_id, recorded_at);

-- ---------------------------------------------------------------------------
-- sem_dataset: whatever the business calls "a set of data" — a table, a set of
-- tables, a database, a feed, a set of feeds, a stream, an API, a return, a
-- query, or nothing yet. A dataset may be declared before it is bound to any
-- physical object; an unbound dataset still participates in relationships and
-- is reported as a connectivity gap (FR-MET-003).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sem_dataset (
    id          VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id   VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    created_at  VARCHAR(32)   NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sem_dataset_tenant ON sem_dataset (tenant_id);

CREATE TABLE IF NOT EXISTS sem_dataset_version (
    id                    VARCHAR(26)   NOT NULL PRIMARY KEY,
    dataset_id            VARCHAR(26)   NOT NULL REFERENCES sem_dataset (id) ON DELETE CASCADE,
    version               INTEGER       NOT NULL,
    valid_from            VARCHAR(32)   NOT NULL,
    valid_to              VARCHAR(32),
    recorded_at           VARCHAR(32)   NOT NULL,
    superseded_at         VARCHAR(32),
    authored_by           VARCHAR(26),
    approved_by           VARCHAR(26),
    approved_at           VARCHAR(32),
    change_reason         TEXT          NOT NULL DEFAULT '',
    name                  VARCHAR(255)  NOT NULL,
    slug                  VARCHAR(128)  NOT NULL,
    description           TEXT          NOT NULL DEFAULT '',
    purpose               TEXT          NOT NULL DEFAULT '',
    domain_id             VARCHAR(26),
    shape                 VARCHAR(32)   NOT NULL DEFAULT 'unbound',
    owner_id              VARCHAR(26),
    steward_id            VARCHAR(26),
    custodian_id          VARCHAR(26),
    criticality           INTEGER       NOT NULL DEFAULT 4,
    grain_json            TEXT,
    business_key_json     TEXT,
    temporality           VARCHAR(32)   NOT NULL DEFAULT 'snapshot',
    rhythm_json           TEXT,
    authoritativeness     VARCHAR(32)   NOT NULL DEFAULT 'unknown',
    source_of_truth_id    VARCHAR(26),
    retention_days        INTEGER,
    jurisdiction          VARCHAR(64),
    sensitivity           VARCHAR(32)   NOT NULL DEFAULT 'internal',
    lifecycle_state       VARCHAR(32)   NOT NULL DEFAULT 'proposed',
    tags_json             TEXT          NOT NULL DEFAULT '[]',
    CONSTRAINT ck_sem_dataset_criticality CHECK (criticality BETWEEN 1 AND 4),
    CONSTRAINT ck_sem_dataset_shape CHECK (shape IN (
        'unbound', 'table', 'table_set', 'schema', 'feed', 'feed_set',
        'stream', 'api', 'report', 'query')),
    CONSTRAINT ck_sem_dataset_lifecycle CHECK (lifecycle_state IN (
        'proposed', 'active', 'deprecated', 'retired'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sem_dataset_current
    ON sem_dataset_version (dataset_id) WHERE superseded_at IS NULL AND valid_to IS NULL;
CREATE INDEX IF NOT EXISTS ix_sem_dataset_version_entity
    ON sem_dataset_version (dataset_id, recorded_at);
CREATE INDEX IF NOT EXISTS ix_sem_dataset_version_domain
    ON sem_dataset_version (domain_id, criticality);
CREATE INDEX IF NOT EXISTS ix_sem_dataset_version_slug
    ON sem_dataset_version (slug);

-- ---------------------------------------------------------------------------
-- sem_attribute: a business field of a dataset, with its interpretation.
-- Distinct from a physical column: the binding to one lives separately, so an
-- attribute survives a schema change that renames the column beneath it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sem_attribute (
    id          VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id   VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    dataset_id  VARCHAR(26)   NOT NULL REFERENCES sem_dataset (id) ON DELETE CASCADE,
    created_at  VARCHAR(32)   NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sem_attribute_dataset ON sem_attribute (dataset_id);

CREATE TABLE IF NOT EXISTS sem_attribute_version (
    id                     VARCHAR(26)   NOT NULL PRIMARY KEY,
    attribute_id           VARCHAR(26)   NOT NULL REFERENCES sem_attribute (id) ON DELETE CASCADE,
    version                INTEGER       NOT NULL,
    valid_from             VARCHAR(32)   NOT NULL,
    valid_to               VARCHAR(32),
    recorded_at            VARCHAR(32)   NOT NULL,
    superseded_at          VARCHAR(32),
    authored_by            VARCHAR(26),
    approved_by            VARCHAR(26),
    approved_at            VARCHAR(32),
    change_reason          TEXT          NOT NULL DEFAULT '',
    name                   VARCHAR(128)  NOT NULL,
    ordinal                INTEGER       NOT NULL DEFAULT 0,
    definition             TEXT          NOT NULL DEFAULT '',
    interpretation         TEXT          NOT NULL DEFAULT '',
    semantic_type          VARCHAR(64),
    unit                   VARCHAR(32),
    currency_attribute     VARCHAR(128),
    numeric_scale          INTEGER,
    numeric_precision      INTEGER,
    value_domain_json      TEXT,
    optionality            VARCHAR(32)   NOT NULL DEFAULT 'optional',
    optionality_condition  TEXT,
    is_cde                 INTEGER       NOT NULL DEFAULT 0,
    obligations_json       TEXT          NOT NULL DEFAULT '[]',
    sensitivity            VARCHAR(32)   NOT NULL DEFAULT 'internal',
    masking_policy         VARCHAR(64),
    expected_behaviour     VARCHAR(32),
    concept_property_id    VARCHAR(26),
    glossary_term          VARCHAR(255),
    owner_id               VARCHAR(26),
    CONSTRAINT ck_sem_attribute_is_cde CHECK (is_cde IN (0, 1)),
    CONSTRAINT ck_sem_attribute_optionality CHECK (optionality IN (
        'mandatory', 'conditional', 'optional'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sem_attribute_current
    ON sem_attribute_version (attribute_id) WHERE superseded_at IS NULL AND valid_to IS NULL;
CREATE INDEX IF NOT EXISTS ix_sem_attribute_version_entity
    ON sem_attribute_version (attribute_id, recorded_at);
CREATE INDEX IF NOT EXISTS ix_sem_attribute_version_cde
    ON sem_attribute_version (is_cde, semantic_type);

-- ---------------------------------------------------------------------------
-- sem_concept / sem_concept_property: the canonical vocabulary.
-- A Concept is a thing the business talks about — Party, Instrument, Position.
-- Attributes across the estate map to a Concept's Properties, which is what
-- turns "author a control once, enforce it everywhere" from a slogan into a
-- join, and what lets two incompatible definitions of the same property be
-- detected rather than silently coexist (FR-MET-040..043).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sem_concept (
    id          VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id   VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    created_at  VARCHAR(32)   NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sem_concept_tenant ON sem_concept (tenant_id);

CREATE TABLE IF NOT EXISTS sem_concept_version (
    id             VARCHAR(26)   NOT NULL PRIMARY KEY,
    concept_id     VARCHAR(26)   NOT NULL REFERENCES sem_concept (id) ON DELETE CASCADE,
    version        INTEGER       NOT NULL,
    valid_from     VARCHAR(32)   NOT NULL,
    valid_to       VARCHAR(32),
    recorded_at    VARCHAR(32)   NOT NULL,
    superseded_at  VARCHAR(32),
    authored_by    VARCHAR(26),
    approved_by    VARCHAR(26),
    approved_at    VARCHAR(32),
    change_reason  TEXT          NOT NULL DEFAULT '',
    name           VARCHAR(128)  NOT NULL,
    description    TEXT          NOT NULL DEFAULT '',
    domain_id      VARCHAR(26),
    pack_ref       VARCHAR(128)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sem_concept_current
    ON sem_concept_version (concept_id) WHERE superseded_at IS NULL AND valid_to IS NULL;
CREATE INDEX IF NOT EXISTS ix_sem_concept_version_entity
    ON sem_concept_version (concept_id, recorded_at);

CREATE TABLE IF NOT EXISTS sem_concept_property (
    id          VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id   VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    concept_id  VARCHAR(26)   NOT NULL REFERENCES sem_concept (id) ON DELETE CASCADE,
    created_at  VARCHAR(32)   NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sem_concept_property_concept
    ON sem_concept_property (concept_id);

CREATE TABLE IF NOT EXISTS sem_concept_property_version (
    id                 VARCHAR(26)   NOT NULL PRIMARY KEY,
    property_id        VARCHAR(26)   NOT NULL
                                     REFERENCES sem_concept_property (id) ON DELETE CASCADE,
    version            INTEGER       NOT NULL,
    valid_from         VARCHAR(32)   NOT NULL,
    valid_to           VARCHAR(32),
    recorded_at        VARCHAR(32)   NOT NULL,
    superseded_at      VARCHAR(32),
    authored_by        VARCHAR(26),
    approved_by        VARCHAR(26),
    approved_at        VARCHAR(32),
    change_reason      TEXT          NOT NULL DEFAULT '',
    name               VARCHAR(128)  NOT NULL,
    definition         TEXT          NOT NULL DEFAULT '',
    semantic_type      VARCHAR(64),
    unit               VARCHAR(32),
    value_domain_json  TEXT,
    is_identifier      INTEGER       NOT NULL DEFAULT 0,
    CONSTRAINT ck_sem_concept_property_identifier CHECK (is_identifier IN (0, 1))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sem_concept_property_current
    ON sem_concept_property_version (property_id)
    WHERE superseded_at IS NULL AND valid_to IS NULL;
CREATE INDEX IF NOT EXISTS ix_sem_concept_property_version_entity
    ON sem_concept_property_version (property_id, recorded_at);

-- ---------------------------------------------------------------------------
-- sem_relationship: the declaration that turns an estate into a map.
--
-- The most valuable object in the semantic layer, because each kind generates a
-- different family of controls: RECONCILES_WITH generates a reconciliation with
-- break workflow, TEMPORAL_SUCCESSOR generates a roll-forward, TOGETHER_COMPLETE
-- generates a population-completeness check against a declared universe.
--
-- Join keys are held in BUSINESS ATTRIBUTE terms and resolved to physical
-- columns at compile time, so a relationship survives a schema change beneath
-- it and can be declared before either side is bound (FR-MET-060..068).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sem_relationship (
    id          VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id   VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    created_at  VARCHAR(32)   NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sem_relationship_tenant ON sem_relationship (tenant_id);

CREATE TABLE IF NOT EXISTS sem_relationship_version (
    id                  VARCHAR(26)   NOT NULL PRIMARY KEY,
    relationship_id     VARCHAR(26)   NOT NULL
                                      REFERENCES sem_relationship (id) ON DELETE CASCADE,
    version             INTEGER       NOT NULL,
    valid_from          VARCHAR(32)   NOT NULL,
    valid_to            VARCHAR(32),
    recorded_at         VARCHAR(32)   NOT NULL,
    superseded_at       VARCHAR(32),
    authored_by         VARCHAR(26),
    approved_by         VARCHAR(26),
    approved_at         VARCHAR(32),
    change_reason       TEXT          NOT NULL DEFAULT '',
    kind                VARCHAR(32)   NOT NULL,
    from_dataset_id     VARCHAR(26)   NOT NULL,
    to_dataset_id       VARCHAR(26)   NOT NULL,
    name                VARCHAR(255)  NOT NULL DEFAULT '',
    description         TEXT          NOT NULL DEFAULT '',
    match_keys_json     TEXT          NOT NULL DEFAULT '[]',
    compare_json        TEXT          NOT NULL DEFAULT '[]',
    cardinality         VARCHAR(32)   NOT NULL DEFAULT 'many_to_many',
    tolerance_json      TEXT,
    offset_json         TEXT,
    filter_expression   TEXT,
    owner_id            VARCHAR(26),
    criticality         INTEGER       NOT NULL DEFAULT 4,
    status              VARCHAR(32)   NOT NULL DEFAULT 'proposed',
    confidence          REAL,
    discovered_by       VARCHAR(64),
    evidence_json       TEXT,
    CONSTRAINT ck_sem_relationship_kind CHECK (kind IN (
        'references', 'reconciles_with', 'derives_from', 'feeds', 'mirrors',
        'aggregates', 'enriches', 'supersedes', 'same_entity_as',
        'temporal_successor', 'parent_of', 'mutually_exclusive',
        'together_complete')),
    CONSTRAINT ck_sem_relationship_cardinality CHECK (cardinality IN (
        'one_to_one', 'one_to_many', 'many_to_one', 'many_to_many')),
    CONSTRAINT ck_sem_relationship_status CHECK (status IN (
        'proposed', 'confirmed', 'rejected', 'retired')),
    CONSTRAINT ck_sem_relationship_criticality CHECK (criticality BETWEEN 1 AND 4)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sem_relationship_current
    ON sem_relationship_version (relationship_id)
    WHERE superseded_at IS NULL AND valid_to IS NULL;
CREATE INDEX IF NOT EXISTS ix_sem_relationship_version_from
    ON sem_relationship_version (from_dataset_id, kind);
CREATE INDEX IF NOT EXISTS ix_sem_relationship_version_to
    ON sem_relationship_version (to_dataset_id, kind);
CREATE INDEX IF NOT EXISTS ix_sem_relationship_version_entity
    ON sem_relationship_version (relationship_id, recorded_at);

-- ---------------------------------------------------------------------------
-- sem_journey / sem_journey_step: a business process as a chain of datasets.
-- Gives business lineage where technical lineage cannot reach — a mainframe
-- job, a vendor package, a manual upload — because a human described it in one
-- sentence rather than a scanner reverse-engineering it (FR-MET-080..084).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sem_journey (
    id          VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id   VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    created_at  VARCHAR(32)   NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sem_journey_tenant ON sem_journey (tenant_id);

CREATE TABLE IF NOT EXISTS sem_journey_version (
    id             VARCHAR(26)   NOT NULL PRIMARY KEY,
    journey_id     VARCHAR(26)   NOT NULL REFERENCES sem_journey (id) ON DELETE CASCADE,
    version        INTEGER       NOT NULL,
    valid_from     VARCHAR(32)   NOT NULL,
    valid_to       VARCHAR(32),
    recorded_at    VARCHAR(32)   NOT NULL,
    superseded_at  VARCHAR(32),
    authored_by    VARCHAR(26),
    approved_by    VARCHAR(26),
    approved_at    VARCHAR(32),
    change_reason  TEXT          NOT NULL DEFAULT '',
    name           VARCHAR(255)  NOT NULL,
    slug           VARCHAR(128)  NOT NULL,
    description    TEXT          NOT NULL DEFAULT '',
    domain_id      VARCHAR(26),
    owner_id       VARCHAR(26),
    criticality    INTEGER       NOT NULL DEFAULT 4,
    sla_json       TEXT,
    steps_json     TEXT          NOT NULL DEFAULT '[]',
    CONSTRAINT ck_sem_journey_criticality CHECK (criticality BETWEEN 1 AND 4)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sem_journey_current
    ON sem_journey_version (journey_id) WHERE superseded_at IS NULL AND valid_to IS NULL;
CREATE INDEX IF NOT EXISTS ix_sem_journey_version_entity
    ON sem_journey_version (journey_id, recorded_at);

-- ---------------------------------------------------------------------------
-- sem_connection: how Prama reaches a source. Configured by a data architect
-- through typed forms, never a raw connection string, and never holding a
-- secret: credential_ref names a vault entry the business user cannot read
-- (FR-CON-026..029).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sem_connection (
    id          VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id   VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    created_at  VARCHAR(32)   NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sem_connection_tenant ON sem_connection (tenant_id);

CREATE TABLE IF NOT EXISTS sem_connection_version (
    id                 VARCHAR(26)   NOT NULL PRIMARY KEY,
    connection_id      VARCHAR(26)   NOT NULL
                                     REFERENCES sem_connection (id) ON DELETE CASCADE,
    version            INTEGER       NOT NULL,
    valid_from         VARCHAR(32)   NOT NULL,
    valid_to           VARCHAR(32),
    recorded_at        VARCHAR(32)   NOT NULL,
    superseded_at      VARCHAR(32),
    authored_by        VARCHAR(26),
    approved_by        VARCHAR(26),
    approved_at        VARCHAR(32),
    change_reason      TEXT          NOT NULL DEFAULT '',
    name               VARCHAR(255)  NOT NULL,
    slug               VARCHAR(128)  NOT NULL,
    source_type        VARCHAR(64)   NOT NULL,
    description        TEXT          NOT NULL DEFAULT '',
    config_json        TEXT          NOT NULL DEFAULT '{}',
    credential_ref     VARCHAR(255),
    read_policy_json   TEXT          NOT NULL DEFAULT '{}',
    budget_json        TEXT          NOT NULL DEFAULT '{}',
    owner_id           VARCHAR(26),
    health_state       VARCHAR(32)   NOT NULL DEFAULT 'unknown',
    health_checked_at  VARCHAR(32),
    health_detail      TEXT,
    CONSTRAINT ck_sem_connection_health CHECK (health_state IN (
        'unknown', 'healthy', 'degraded', 'unreachable', 'unauthorised'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sem_connection_current
    ON sem_connection_version (connection_id) WHERE superseded_at IS NULL AND valid_to IS NULL;
CREATE INDEX IF NOT EXISTS ix_sem_connection_version_entity
    ON sem_connection_version (connection_id, recorded_at);

-- ---------------------------------------------------------------------------
-- sem_binding: the link from a business object to its physical realisation.
-- Held separately from the declaration so that a dataset survives a column
-- rename beneath it, and so that a dataset can exist unbound (FR-MET-002/003).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sem_binding (
    id          VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id   VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    created_at  VARCHAR(32)   NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sem_binding_tenant ON sem_binding (tenant_id);

CREATE TABLE IF NOT EXISTS sem_binding_version (
    id                VARCHAR(26)   NOT NULL PRIMARY KEY,
    binding_id        VARCHAR(26)   NOT NULL REFERENCES sem_binding (id) ON DELETE CASCADE,
    version           INTEGER       NOT NULL,
    valid_from        VARCHAR(32)   NOT NULL,
    valid_to          VARCHAR(32),
    recorded_at       VARCHAR(32)   NOT NULL,
    superseded_at     VARCHAR(32),
    authored_by       VARCHAR(26),
    approved_by       VARCHAR(26),
    approved_at       VARCHAR(32),
    change_reason     TEXT          NOT NULL DEFAULT '',
    target_kind       VARCHAR(32)   NOT NULL,
    dataset_id        VARCHAR(26)   NOT NULL,
    attribute_id      VARCHAR(26),
    connection_id     VARCHAR(26)   NOT NULL,
    physical_ref_json TEXT          NOT NULL DEFAULT '{}',
    transform         TEXT,
    status            VARCHAR(32)   NOT NULL DEFAULT 'proposed',
    confidence        REAL,
    last_verified_at  VARCHAR(32),
    drift_state       VARCHAR(32)   NOT NULL DEFAULT 'unknown',
    CONSTRAINT ck_sem_binding_target CHECK (target_kind IN ('dataset', 'attribute')),
    CONSTRAINT ck_sem_binding_status CHECK (status IN (
        'proposed', 'confirmed', 'rejected', 'broken')),
    CONSTRAINT ck_sem_binding_drift CHECK (drift_state IN (
        'unknown', 'intact', 'missing', 'retyped', 'renamed'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sem_binding_current
    ON sem_binding_version (binding_id) WHERE superseded_at IS NULL AND valid_to IS NULL;
CREATE INDEX IF NOT EXISTS ix_sem_binding_version_dataset
    ON sem_binding_version (dataset_id, target_kind);
CREATE INDEX IF NOT EXISTS ix_sem_binding_version_connection
    ON sem_binding_version (connection_id);
CREATE INDEX IF NOT EXISTS ix_sem_binding_version_entity
    ON sem_binding_version (binding_id, recorded_at);

-- ---------------------------------------------------------------------------
-- EVIDENCE LEDGER  (Wave 9)
--
-- Append-only and hash-linked. These tables are owned by EvidenceBase rather
-- than Base, so no platform operation can create, truncate or cascade into
-- them: the ledger outlives the semantic layer it describes, is retained for
-- years after it, and is the one thing in Prama that is never rewritten.
--
-- There is no UPDATE path in the DAO and no ON DELETE CASCADE here — both
-- deliberate. A foreign key from ev_record to a semantic table would let a
-- tenant deletion silently take the evidence of what was checked with it,
-- which is precisely the record somebody would later need. The identifiers are
-- carried as plain values.
--
-- The one exception to immutability is erasure, and it is not a delete:
-- content columns are blanked, the original content hash is preserved in
-- ev_record.tombstone_json, and the chain still verifies across the gap. See
-- prama/evidence/record.py::Tombstone.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ev_run (
    id             VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id      VARCHAR(26)   NOT NULL,
    -- What caused it: schedule, api, backfill, manual, replay.
    triggered_by   VARCHAR(32)   NOT NULL DEFAULT 'schedule',
    actor_id       VARCHAR(26),
    engine         VARCHAR(64)   NOT NULL DEFAULT '',
    started_at     VARCHAR(32)   NOT NULL,
    finished_at    VARCHAR(32),
    -- running | complete | failed | abandoned. A run that never finished is a
    -- fact about the estate, not a row to tidy away: its controls have no
    -- verdict, and a scorecard that silently omitted them would report the
    -- controls that did run as though they were all of them.
    status         VARCHAR(32)   NOT NULL DEFAULT 'running',
    record_count   INTEGER       NOT NULL DEFAULT 0,
    detail         TEXT          NOT NULL DEFAULT '',
    CONSTRAINT ck_ev_run_status CHECK (status IN (
        'running', 'complete', 'failed', 'abandoned'))
);
CREATE INDEX IF NOT EXISTS ix_ev_run_tenant ON ev_run (tenant_id, started_at);

CREATE TABLE IF NOT EXISTS ev_record (
    id               VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id        VARCHAR(26)   NOT NULL,
    -- Position in the chain, per tenant. Contiguous from zero, so a missing
    -- record shows as a gap rather than only as a broken hash.
    sequence         INTEGER       NOT NULL,
    run_id           VARCHAR(26),
    plan_id          VARCHAR(128)  NOT NULL DEFAULT '',
    control_id       VARCHAR(26)   NOT NULL DEFAULT '',
    control_version  INTEGER       NOT NULL DEFAULT 1,
    dataset          VARCHAR(128)  NOT NULL DEFAULT '',
    binding          VARCHAR(128)  NOT NULL DEFAULT '',
    snapshot_json    TEXT          NOT NULL DEFAULT '{}',
    parameters_json  TEXT          NOT NULL DEFAULT '{}',
    engine           VARCHAR(64)   NOT NULL DEFAULT '',
    -- full | incremental | forward_only. Carried because a verdict means
    -- different things at different widths: "passed" after a full scan says
    -- the dataset is sound, and after an incremental run says only that the
    -- rows examined were.
    coverage         VARCHAR(32)   NOT NULL DEFAULT 'full',
    verdict          VARCHAR(32)   NOT NULL DEFAULT 'error',
    metrics_json     TEXT          NOT NULL DEFAULT '{}',
    samples_digest   VARCHAR(64)   NOT NULL DEFAULT '',
    sample_count     INTEGER       NOT NULL DEFAULT 0,
    started_at       VARCHAR(32)   NOT NULL DEFAULT '',
    finished_at      VARCHAR(32)   NOT NULL DEFAULT '',
    duration_ms      INTEGER       NOT NULL DEFAULT 0,
    triggered_by     VARCHAR(32)   NOT NULL DEFAULT 'schedule',
    detail           TEXT          NOT NULL DEFAULT '',
    -- Added with evidence format 1.1. Nullable and defaulted, so a row written
    -- under 1.0 reads back as 1.0 and still hashes to the value stored beside
    -- it: EvidenceRecord.content() emits these only for records whose own
    -- evidence_version has them.
    dimensions_json  TEXT          NOT NULL DEFAULT '[]',
    criticality      INTEGER       NOT NULL DEFAULT 4,
    tombstone_json   TEXT,
    previous_hash    VARCHAR(64)   NOT NULL,
    content_hash     VARCHAR(64)   NOT NULL,
    record_hash      VARCHAR(64)   NOT NULL,
    evidence_version VARCHAR(16)   NOT NULL DEFAULT '1.0',
    -- These are prama.ir.Verdict and prama.execute.Coverage, and a test
    -- asserts the constraints match the enums. A constraint that omits a
    -- verdict the engine can produce rejects a perfectly ordinary result at
    -- the worst moment: the run is over, the finding is real, and there is
    -- nowhere to put it.
    CONSTRAINT ck_ev_record_verdict CHECK (verdict IN (
        'pass', 'fail', 'error', 'skipped', 'indeterminate')),
    CONSTRAINT ck_ev_record_coverage CHECK (coverage IN (
        'full', 'incremental', 'forward_only'))
);
-- One record per position per tenant. This is the constraint that makes a
-- concurrent second writer fail loudly instead of forking the chain.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ev_record_sequence
    ON ev_record (tenant_id, sequence);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ev_record_hash ON ev_record (record_hash);
CREATE INDEX IF NOT EXISTS ix_ev_record_dataset ON ev_record (tenant_id, dataset, finished_at);
CREATE INDEX IF NOT EXISTS ix_ev_record_control ON ev_record (control_id, finished_at);
CREATE INDEX IF NOT EXISTS ix_ev_record_run ON ev_record (run_id);
CREATE INDEX IF NOT EXISTS ix_ev_record_verdict ON ev_record (tenant_id, verdict, finished_at);

CREATE TABLE IF NOT EXISTS ev_sample (
    -- The digest is the identity: the same failing rows recorded twice are one
    -- sample set, and a record refers to it by hash rather than owning it.
    digest       VARCHAR(64)   NOT NULL PRIMARY KEY,
    tenant_id    VARCHAR(26)   NOT NULL,
    rows_json    TEXT          NOT NULL DEFAULT '[]',
    -- Which columns were removed before storage, so a reader knows what they
    -- are not seeing rather than assuming the row is complete.
    masked_json  TEXT          NOT NULL DEFAULT '[]',
    row_count    INTEGER       NOT NULL DEFAULT 0,
    created_at   VARCHAR(32)   NOT NULL,
    -- Samples expire on their own schedule, years before the records that name
    -- them: the rows are the personal data, the record is the audit trail, and
    -- keeping the two on one clock means either discarding evidence early or
    -- holding personal data for seven years.
    expires_at   VARCHAR(32)
);
CREATE INDEX IF NOT EXISTS ix_ev_sample_expiry ON ev_sample (expires_at);
CREATE INDEX IF NOT EXISTS ix_ev_sample_tenant ON ev_sample (tenant_id);

-- ---------------------------------------------------------------------------
-- CONTROLS  (Wave 9)
--
-- The estate of controls, bitemporal like every other declaration. Editing a
-- threshold is an AMEND — the old threshold really was the rule until Tuesday —
-- and discovering the control was wrong all along is a CORRECT. Conflating the
-- two loses the ability to replay an evidence record against the control that
-- was actually in force when it ran, which is the whole point of keeping both
-- axes.
--
-- The PQL text is the authority. plan_id, severity and dimensions_json are
-- DERIVED from it when a version is written, never supplied by a caller, and a
-- test re-lowers the stored text and compares. They exist as columns so the
-- estate can be queried without parsing every control, not as a second source
-- of truth.
--
-- ctl_control.identity is what makes regeneration idempotent: it is derived
-- from what a control is *about* — the declaration, the rule, the subject —
-- and not from its text, so re-running the generator after an edit amends the
-- existing control instead of orphaning one and creating another.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ctl_control (
    id          VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id   VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    -- Stable across regeneration. See prama/core/provenance.py::identity.
    identity    VARCHAR(64)   NOT NULL,
    created_at  VARCHAR(32)   NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ctl_control_identity ON ctl_control (tenant_id, identity);
CREATE INDEX IF NOT EXISTS ix_ctl_control_tenant ON ctl_control (tenant_id);

CREATE TABLE IF NOT EXISTS ctl_control_version (
    id              VARCHAR(26)   NOT NULL PRIMARY KEY,
    control_id      VARCHAR(26)   NOT NULL REFERENCES ctl_control (id) ON DELETE CASCADE,
    version         INTEGER       NOT NULL,
    valid_from      VARCHAR(32)   NOT NULL,
    valid_to        VARCHAR(32),
    recorded_at     VARCHAR(32)   NOT NULL,
    superseded_at   VARCHAR(32),
    authored_by     VARCHAR(26),
    approved_by     VARCHAR(26),
    approved_at     VARCHAR(32),
    change_reason   TEXT          NOT NULL DEFAULT '',

    -- The authority. Everything below it is derived from this text.
    pql             TEXT          NOT NULL,
    name            VARCHAR(255)  NOT NULL DEFAULT '',
    dataset         VARCHAR(128)  NOT NULL DEFAULT '',
    -- Content-addressed plan the text lowers to. An evidence record names this,
    -- so a verdict can be traced to exactly what was executed rather than to a
    -- row that happened to point at it.
    plan_id         VARCHAR(128)  NOT NULL DEFAULT '',
    content_hash    VARCHAR(64)   NOT NULL DEFAULT '',
    severity        VARCHAR(32)   NOT NULL DEFAULT 'major',
    dimensions_json TEXT          NOT NULL DEFAULT '[]',
    criticality     INTEGER       NOT NULL DEFAULT 4,

    -- How it came to exist, and what that is worth. A mined rule says the data
    -- behaves this way; a declared one says the business means it to.
    origin          VARCHAR(32)   NOT NULL DEFAULT 'declaration',
    rule            VARCHAR(128)  NOT NULL DEFAULT '',
    source_ref      VARCHAR(128)  NOT NULL DEFAULT '',
    provenance_json TEXT          NOT NULL DEFAULT '{}',

    -- proposed | active | suppressed | retired. A control is never deleted:
    -- retiring it keeps the evidence it produced attributable to something.
    status          VARCHAR(32)   NOT NULL DEFAULT 'proposed',
    -- Set when status is 'suppressed'. Both are required together, because a
    -- control silenced with no expiry and no reason is a control nobody will
    -- ever turn back on.
    suppressed_until   VARCHAR(32),
    suppressed_because TEXT,
    schedule        VARCHAR(64)   NOT NULL DEFAULT '',
    owner_id        VARCHAR(26),
    CONSTRAINT ck_ctl_control_status CHECK (status IN (
        'proposed', 'active', 'suppressed', 'retired')),
    CONSTRAINT ck_ctl_control_severity CHECK (severity IN (
        'info', 'warning', 'minor', 'major', 'critical')),
    CONSTRAINT ck_ctl_control_origin CHECK (origin IN (
        'declaration', 'import', 'document', 'mining', 'example', 'induction')),
    CONSTRAINT ck_ctl_control_criticality CHECK (criticality BETWEEN 1 AND 4),
    CONSTRAINT ck_ctl_control_suppression CHECK (
        status <> 'suppressed' OR (suppressed_until IS NOT NULL AND suppressed_because IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ctl_control_current
    ON ctl_control_version (control_id) WHERE superseded_at IS NULL AND valid_to IS NULL;
CREATE INDEX IF NOT EXISTS ix_ctl_control_version_entity
    ON ctl_control_version (control_id, recorded_at);
CREATE INDEX IF NOT EXISTS ix_ctl_control_version_dataset
    ON ctl_control_version (dataset, status);
CREATE INDEX IF NOT EXISTS ix_ctl_control_version_plan ON ctl_control_version (plan_id);

-- A proposal a person turned down, kept so the same one is not offered again.
-- Recorded rather than deleted: a rejection is a training signal, and
-- re-proposing something a steward has already refused is the fastest way to
-- lose their attention.
CREATE TABLE IF NOT EXISTS ctl_rejection (
    id            VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id     VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    identity      VARCHAR(64)   NOT NULL,
    content_hash  VARCHAR(64)   NOT NULL DEFAULT '',
    reason        VARCHAR(32)   NOT NULL DEFAULT 'incorrect',
    note          TEXT          NOT NULL DEFAULT '',
    rejected_by   VARCHAR(26),
    rejected_at   VARCHAR(32)   NOT NULL,
    -- These are prama.propose.proposal.RejectionReason, and a test asserts the
    -- two agree. A constraint listing reasons the enum does not have accepts
    -- rows nothing can read; one missing a reason the enum has rejects a
    -- perfectly ordinary rejection at the worst moment.
    CONSTRAINT ck_ctl_rejection_reason CHECK (reason IN (
        'incorrect', 'not_material', 'coincidental', 'duplicate', 'too_noisy',
        'pending_remediation'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ctl_rejection_identity
    ON ctl_rejection (tenant_id, identity, content_hash);

-- ---------------------------------------------------------------------------
-- ATTESTATIONS  (Wave 9)
--
-- A named person's statement that they reviewed a scope for a period. Never
-- edited: a signed attestation is immutable, and a correction is a *new* row
-- naming the one it supersedes, because the fact that somebody signed the
-- first one is itself part of the record.
--
-- The seal is an HMAC over content_hash. It says the content was sealed by a
-- holder of the key and nothing to anybody else; the column is named `seal`
-- rather than `signature` so the word cannot imply more than it delivers.
--
-- evidence_root ties the statement to the facts. Without it an attestation
-- floats free of the records, and evidence written afterwards is
-- indistinguishable from evidence written before.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS att_attestation (
    id                 VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id          VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    attester_id        VARCHAR(26)   NOT NULL,
    -- The name as it was at signing. Denormalised on purpose: an attestation
    -- reprinted years later must say who signed it, not who happens to hold
    -- that principal id now.
    attester_name      VARCHAR(255)  NOT NULL,
    statement          TEXT          NOT NULL,
    scope              VARCHAR(255)  NOT NULL,
    period_start       VARCHAR(32)   NOT NULL,
    period_end         VARCHAR(32)   NOT NULL,
    coverage_json      TEXT          NOT NULL DEFAULT '{}',
    -- Every failure and every unestablished control in the period, in full.
    -- Summarising them into a count would be asking somebody to sign for
    -- things they were not shown.
    exceptions_json    TEXT          NOT NULL DEFAULT '[]',
    evidence_root      VARCHAR(64)   NOT NULL,
    evidence_records   INTEGER       NOT NULL DEFAULT 0,
    content_hash       VARCHAR(64)   NOT NULL,
    seal               VARCHAR(64)   NOT NULL,
    signed_at          VARCHAR(32)   NOT NULL,
    -- Set on the *superseded* row when a correction arrives, so a reader
    -- looking at an old attestation learns it was replaced rather than
    -- having to search for a newer one.
    superseded_by      VARCHAR(26),
    supersedes         VARCHAR(26),
    supersedes_because TEXT          NOT NULL DEFAULT '',
    version            VARCHAR(16)   NOT NULL DEFAULT '1.0',
    CONSTRAINT ck_att_period CHECK (period_end >= period_start)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_att_content ON att_attestation (content_hash);
CREATE INDEX IF NOT EXISTS ix_att_tenant ON att_attestation (tenant_id, period_end);
CREATE INDEX IF NOT EXISTS ix_att_scope ON att_attestation (tenant_id, scope, period_end);
CREATE INDEX IF NOT EXISTS ix_att_attester ON att_attestation (attester_id);

-- ---------------------------------------------------------------------------
-- RECONCILIATION BREAKS  (Wave 9)
--
-- The break queue, persisted. Working state rather than evidence: the ledger
-- records what a reconciliation concluded, and this records what people are
-- doing about it. So this table is *mutable* where the ledger is not, and the
-- three things that must not move are protected by the shape rather than by
-- discipline.
--
-- first_seen never moves. A break re-detected for forty days is forty days
-- old; a queue that stamps each detection with today reports it as new every
-- morning and nothing ever ages.
--
-- Clearing is inferred, never announced. No reconciliation tells you a break
-- has gone — it stops reporting it. A break open in the last run and absent
-- from this one is cleared here, and a queue that waits to be told never
-- closes anything.
--
-- A cleared break is not deleted. "We had four hundred breaks and they
-- cleared" and "we had four hundred breaks" are the same sentence in a system
-- that forgets, and only one of them is reassuring.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rec_break (
    id                VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id         VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    -- Which reconciliation produced it. A break key is only unique within its
    -- own definition; two reconciliations over the same accounts would
    -- otherwise collide and each would clear the other's breaks.
    definition        VARCHAR(255)  NOT NULL,
    break_key         VARCHAR(255)  NOT NULL,
    -- prama.recon.classify.BreakKind. A test asserts the constraint and the
    -- enum agree in both directions: a constraint listing a kind the enum does
    -- not have accepts rows nothing can read, and one missing a kind the enum
    -- has rejects an ordinary break at the worst moment.
    kind              VARCHAR(32)   NOT NULL,
    -- The two sides, as text rather than REAL: these are money, and summing
    -- or storing them in binary floating point manufactures exactly the small
    -- discrepancies a reconciliation exists to find. A queue that renders a
    -- break as 0.30000000000000004 is not one anybody works.
    left_value        VARCHAR(64)   NOT NULL DEFAULT '',
    right_value       VARCHAR(64)   NOT NULL DEFAULT '',
    difference        VARCHAR(64)   NOT NULL DEFAULT '0',
    -- Why it was classified this way, in a sentence somebody can argue with.
    because           TEXT          NOT NULL DEFAULT '',
    -- What normalisation did to get here. The first question about any break
    -- is whether it is real or a translation error, and this answers it.
    normalisation_json TEXT         NOT NULL DEFAULT '[]',
    aggregated        INTEGER       NOT NULL DEFAULT 0,
    first_seen        VARCHAR(32)   NOT NULL,
    last_seen         VARCHAR(32)   NOT NULL,
    -- prama.recon.workflow.State, enforced the same way as kind.
    state             VARCHAR(32)   NOT NULL DEFAULT 'open',
    owner             VARCHAR(255)  NOT NULL DEFAULT '',
    accepted_reason   TEXT          NOT NULL DEFAULT '',
    -- Appended to, never rewritten. The disposition history is the reason a
    -- carried break is defensible years later.
    comments_json     TEXT          NOT NULL DEFAULT '[]',
    cleared_at        VARCHAR(32),
    CONSTRAINT ck_rec_break_kind CHECK (kind IN (
        'timing', 'fx', 'rounding', 'missing', 'extra', 'duplicate', 'sign',
        'genuine')),
    CONSTRAINT ck_rec_break_state CHECK (state IN (
        'open', 'assigned', 'explained', 'cleared', 'accepted')),
    CONSTRAINT ck_rec_break_aggregated CHECK (aggregated IN (0, 1)),
    CONSTRAINT ck_rec_break_seen CHECK (last_seen >= first_seen)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_rec_break_key
    ON rec_break (tenant_id, definition, break_key);
CREATE INDEX IF NOT EXISTS ix_rec_break_open
    ON rec_break (tenant_id, definition, state, first_seen);
CREATE INDEX IF NOT EXISTS ix_rec_break_owner ON rec_break (tenant_id, owner);


-- ===========================================================================
-- LLM GATEWAY  (Wave 12)
-- ===========================================================================
-- Providers and profiles are data, not configuration: one authority, managed
-- on the Models page or with `prama llm`. A provider stores a reference the
-- secrets layer resolves, never a secret. Hosting has no default, because the
-- default used to be the one class exempt from residency checks.
--
-- Every column the later gateway phases need (budgets, cache, templates) is
-- declared now. Prama has no migrations, so a column added later would be
-- drift on every deployed database. Foreign keys to tables that do not exist
-- yet (llm_template, llm_model) are left out and added with those tables.
CREATE TABLE IF NOT EXISTS llm_provider (
    id             VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id      VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    name           VARCHAR(64)   NOT NULL,
    kind           VARCHAR(64)   NOT NULL,
    dialect        VARCHAR(32)   NOT NULL DEFAULT '',
    hosting        VARCHAR(16)   NOT NULL,
    endpoint       VARCHAR(512)  NOT NULL DEFAULT '',
    region         VARCHAR(32)   NOT NULL DEFAULT '',
    credential_ref VARCHAR(512),
    settings_json  TEXT          NOT NULL DEFAULT '{}',
    enabled        INTEGER       NOT NULL DEFAULT 1,
    created_at     VARCHAR(32)   NOT NULL,
    created_by     VARCHAR(26),
    updated_at     VARCHAR(32)   NOT NULL,
    updated_by     VARCHAR(26),
    CONSTRAINT uq_llm_provider_name UNIQUE (tenant_id, name),
    CONSTRAINT ck_llm_provider_hosting CHECK (hosting IN ('hosted', 'tenant', 'self_hosted')),
    CONSTRAINT ck_llm_provider_enabled CHECK (enabled IN (0, 1))
);

-- A purpose ("author", "explain") mapped to an ordered route of provider and
-- model. Versioned and append-only: which model wrote a proposal must stay
-- answerable after the profile changes.
CREATE TABLE IF NOT EXISTS llm_profile (
    id              VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id       VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    purpose         VARCHAR(64)   NOT NULL,
    current_version INTEGER,
    created_at      VARCHAR(32)   NOT NULL,
    CONSTRAINT uq_llm_profile_purpose UNIQUE (tenant_id, purpose)
);

CREATE TABLE IF NOT EXISTS llm_profile_version (
    id                 VARCHAR(26)   NOT NULL PRIMARY KEY,
    profile_id         VARCHAR(26)   NOT NULL REFERENCES llm_profile (id) ON DELETE CASCADE,
    version            INTEGER       NOT NULL,
    purpose_class      VARCHAR(16)   NOT NULL DEFAULT 'author',
    params_json        TEXT          NOT NULL DEFAULT '{}',
    overridable_json   TEXT          NOT NULL DEFAULT '[]',
    max_sensitivity    VARCHAR(16)   NOT NULL DEFAULT 'internal',
    redactors_json     TEXT          NOT NULL DEFAULT '[]',
    template_id        VARCHAR(26),
    template_version   INTEGER,
    timeout_ms         INTEGER       NOT NULL DEFAULT 60000,
    max_attempts       INTEGER       NOT NULL DEFAULT 3,
    schema_repairs     INTEGER       NOT NULL DEFAULT 1,
    cache_ttl_s        INTEGER       NOT NULL DEFAULT 86400,
    fallback_across_hosting INTEGER  NOT NULL DEFAULT 0,
    eval_run_id        VARCHAR(26),
    note               TEXT          NOT NULL DEFAULT '',
    recorded_at        VARCHAR(32)   NOT NULL,
    recorded_by        VARCHAR(26),
    CONSTRAINT uq_llm_profile_version UNIQUE (profile_id, version),
    CONSTRAINT ck_llm_profile_class CHECK (purpose_class IN ('author', 'explain', 'summarise', 'embed')),
    CONSTRAINT ck_llm_profile_fallback CHECK (fallback_across_hosting IN (0, 1))
);

CREATE TABLE IF NOT EXISTS llm_profile_route (
    profile_version_id VARCHAR(26)  NOT NULL REFERENCES llm_profile_version (id) ON DELETE CASCADE,
    position           INTEGER      NOT NULL,
    provider_id        VARCHAR(26)  NOT NULL REFERENCES llm_provider (id),
    model              VARCHAR(128) NOT NULL,
    params_json        TEXT         NOT NULL DEFAULT '{}',
    PRIMARY KEY (profile_version_id, position)
);

-- Every model call, hash-chained per tenant like the evidence ledger. Hashes of
-- the prompt and answer, never their text.
CREATE TABLE IF NOT EXISTS llm_call (
    id                  VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id           VARCHAR(26)   NOT NULL,
    sequence            INTEGER       NOT NULL,
    started_at          VARCHAR(32)   NOT NULL,
    finished_at         VARCHAR(32)   NOT NULL,
    principal_id        VARCHAR(26),
    api_key_id          VARCHAR(26),
    surface             VARCHAR(32)   NOT NULL,
    purpose             VARCHAR(64)   NOT NULL DEFAULT '',
    profile_id          VARCHAR(26),
    profile_version     INTEGER,
    template_id         VARCHAR(26),
    template_version    INTEGER,
    provider_id         VARCHAR(26),
    provider_kind       VARCHAR(64)   NOT NULL DEFAULT '',
    hosting             VARCHAR(16)   NOT NULL DEFAULT '',
    destination_region  VARCHAR(32)   NOT NULL DEFAULT '',
    jurisdiction        VARCHAR(32)   NOT NULL DEFAULT '',
    sensitivity         VARCHAR(16)   NOT NULL,
    model_requested     VARCHAR(128)  NOT NULL DEFAULT '',
    model_reported      VARCHAR(128)  NOT NULL DEFAULT '',
    model_version       VARCHAR(128)  NOT NULL DEFAULT '',
    price_model_id      VARCHAR(26),
    request_fingerprint VARCHAR(64)   NOT NULL,
    prompt_hash         VARCHAR(64)   NOT NULL,
    response_hash       VARCHAR(64)   NOT NULL DEFAULT '',
    payload_digest      VARCHAR(64),
    redactions_json     TEXT          NOT NULL DEFAULT '{}',
    temperature         REAL          NOT NULL DEFAULT 0,
    seed                INTEGER,
    input_tokens        INTEGER       NOT NULL DEFAULT 0,
    cached_tokens       INTEGER       NOT NULL DEFAULT 0,
    output_tokens       INTEGER       NOT NULL DEFAULT 0,
    tokens_estimated    INTEGER       NOT NULL DEFAULT 0,
    cost_micros         INTEGER       NOT NULL DEFAULT 0,
    latency_ms          INTEGER       NOT NULL DEFAULT 0,
    attempts            INTEGER       NOT NULL DEFAULT 1,
    fallback_from       VARCHAR(26),
    served_from         VARCHAR(16)   NOT NULL DEFAULT 'provider',
    schema_valid        INTEGER,
    grammar_enforced    INTEGER       NOT NULL DEFAULT 0,
    outcome             VARCHAR(24)   NOT NULL,
    outcome_detail      TEXT          NOT NULL DEFAULT '',
    correlation_id      VARCHAR(64),
    previous_hash       VARCHAR(64)   NOT NULL,
    record_hash         VARCHAR(64)   NOT NULL,
    CONSTRAINT uq_llm_call_sequence UNIQUE (tenant_id, sequence),
    CONSTRAINT ck_llm_call_served CHECK (served_from IN ('provider', 'cache', 'replay')),
    CONSTRAINT ck_llm_call_outcome CHECK (outcome IN ('ok', 'incomplete', 'refused_policy',
        'refused_budget', 'refused_rate', 'error', 'cancelled')),
    CONSTRAINT ck_llm_call_flags CHECK (tokens_estimated IN (0, 1) AND grammar_enforced IN (0, 1)
        AND (schema_valid IS NULL OR schema_valid IN (0, 1)))
);
CREATE INDEX IF NOT EXISTS ix_llm_call_started ON llm_call (tenant_id, started_at);

-- ===========================================================================
-- LINEAGE STORE  (Wave 12)
-- ===========================================================================
-- Lineage as data: where it came from, each scan of it, every column edge
-- with its provenance and history, and what could not be read. One store for
-- every origin: parsed SQL, code, OpenLineage, dbt, warehouse history, a
-- declared journey, an import from another tool.
CREATE TABLE IF NOT EXISTS lin_source (
    id            VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id     VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    name          VARCHAR(128)  NOT NULL,
    kind          VARCHAR(32)   NOT NULL,
    location      VARCHAR(512)  NOT NULL DEFAULT '',
    dialect       VARCHAR(32)   NOT NULL DEFAULT 'ansi',
    settings_json TEXT          NOT NULL DEFAULT '{}',
    created_at    VARCHAR(32)   NOT NULL,
    created_by    VARCHAR(26),
    last_run_id   VARCHAR(26),
    CONSTRAINT uq_lin_source_name UNIQUE (tenant_id, name),
    CONSTRAINT ck_lin_source_kind CHECK (kind IN ('sql', 'code', 'openlineage', 'dbt',
        'warehouse', 'declared', 'import'))
);

CREATE TABLE IF NOT EXISTS lin_run (
    id          VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id   VARCHAR(26)   NOT NULL,
    source_id   VARCHAR(26)   NOT NULL REFERENCES lin_source (id) ON DELETE CASCADE,
    started_at  VARCHAR(32)   NOT NULL,
    finished_at VARCHAR(32),
    statements  INTEGER       NOT NULL DEFAULT 0,
    edges       INTEGER       NOT NULL DEFAULT 0,
    gaps        INTEGER       NOT NULL DEFAULT 0,
    understood  REAL          NOT NULL DEFAULT 0,
    outcome     VARCHAR(16)   NOT NULL DEFAULT 'running',
    detail      TEXT          NOT NULL DEFAULT '',
    started_by  VARCHAR(26),
    CONSTRAINT ck_lin_run_outcome CHECK (outcome IN ('running', 'ok', 'partial', 'failed')),
    CONSTRAINT ck_lin_run_understood CHECK (understood >= 0 AND understood <= 1)
);
CREATE INDEX IF NOT EXISTS ix_lin_run_source ON lin_run (source_id, started_at);

-- An edge is identified by its source, its two columns and its transform, so a
-- re-scan finds it again. Bitemporal: valid_to is set when a scan of the same
-- source stops finding it, and the row is kept. `parsed` edges come from a
-- deterministic parser; `inferred` ones (heuristic or model) wait for a person.
CREATE TABLE IF NOT EXISTS lin_edge (
    id              VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id       VARCHAR(26)   NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
    source_id       VARCHAR(26)   NOT NULL REFERENCES lin_source (id) ON DELETE CASCADE,
    identity        VARCHAR(64)   NOT NULL,
    source_dataset  VARCHAR(255)  NOT NULL,
    source_column   VARCHAR(255)  NOT NULL,
    target_dataset  VARCHAR(255)  NOT NULL,
    target_column   VARCHAR(255)  NOT NULL,
    transform       VARCHAR(16)   NOT NULL,
    produced_by     VARCHAR(512)  NOT NULL DEFAULT '',
    expression      TEXT          NOT NULL DEFAULT '',
    status          VARCHAR(16)   NOT NULL DEFAULT 'parsed',
    method          VARCHAR(128)  NOT NULL,
    confidence      REAL          NOT NULL DEFAULT 1,
    unit_id         VARCHAR(26),
    line_start      INTEGER,
    line_end        INTEGER,
    excerpt         TEXT          NOT NULL DEFAULT '',
    llm_fingerprint VARCHAR(64),
    decided_by      VARCHAR(26),
    decided_at      VARCHAR(32),
    decision_note   TEXT,
    valid_from      VARCHAR(32)   NOT NULL,
    valid_to        VARCHAR(32),
    first_seen_run  VARCHAR(26)   NOT NULL,
    last_seen_run   VARCHAR(26)   NOT NULL,
    CONSTRAINT uq_lin_edge_identity UNIQUE (tenant_id, identity),
    CONSTRAINT ck_lin_edge_status CHECK (status IN ('parsed', 'inferred', 'confirmed',
        'rejected', 'retired')),
    CONSTRAINT ck_lin_edge_transform CHECK (transform IN ('identity', 'rename', 'derived',
        'aggregated', 'filter', 'join_key')),
    CONSTRAINT ck_lin_edge_confidence CHECK (confidence >= 0 AND confidence <= 1)
);
CREATE INDEX IF NOT EXISTS ix_lin_edge_source_col ON lin_edge (tenant_id, source_dataset, source_column);
CREATE INDEX IF NOT EXISTS ix_lin_edge_target_col ON lin_edge (tenant_id, target_dataset, target_column);

-- What a run could not read. Kept per run, because "37% of this package was not
-- parsed" is a claim about a moment, and the next scan may say something else.
CREATE TABLE IF NOT EXISTS lin_gap (
    id        VARCHAR(26)   NOT NULL PRIMARY KEY,
    tenant_id VARCHAR(26)   NOT NULL,
    run_id    VARCHAR(26)   NOT NULL REFERENCES lin_run (id) ON DELETE CASCADE,
    kind      VARCHAR(32)   NOT NULL,
    detail    TEXT          NOT NULL,
    statement TEXT          NOT NULL DEFAULT '',
    unit_ref  VARCHAR(512)  NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_lin_gap_run ON lin_gap (run_id);
