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
    tombstone_json   TEXT,
    previous_hash    VARCHAR(64)   NOT NULL,
    content_hash     VARCHAR(64)   NOT NULL,
    record_hash      VARCHAR(64)   NOT NULL,
    evidence_version VARCHAR(16)   NOT NULL DEFAULT '1.0',
    CONSTRAINT ck_ev_record_verdict CHECK (verdict IN (
        'pass', 'fail', 'warn', 'error', 'skipped', 'unknown')),
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
