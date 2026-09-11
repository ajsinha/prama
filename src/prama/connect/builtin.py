"""Registering the first-party connectors, with their presentation overlays.

The overlay is the *only* hand-written part of a connector's form, and it may
add nothing but presentation: which fields are secret, what input to render,
what to call them, and a line of help. Every field itself is derived from the
connector's own code, so a connector that gains an option gains it in the form
the moment the code is written.

``audit()`` reports any overlay key the code does not read, and the test suite
fails the build on it — which is what stops the two halves quietly disagreeing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.connect.capability import CapabilityMatrix
from prama.connect.config_schema import FieldPresentation, InputKind
from prama.connect.registry import ConnectorRegistry, default_registry
from prama.connect.sources.filesystem import CAPABILITIES as FILESYSTEM_CAPABILITIES
from prama.connect.sources.filesystem import FilesystemConnector
from prama.connect.sources.mongo import CAPABILITIES as MONGO_CAPABILITIES
from prama.connect.sources.mongo import MongoConnector
from prama.connect.sources.objectstore import CAPABILITIES as OBJECTSTORE_CAPABILITIES
from prama.connect.sources.objectstore import ObjectStoreConnector
from prama.connect.sources.rest import CAPABILITIES as REST_CAPABILITIES
from prama.connect.sources.rest import RestConnector
from prama.connect.sources.sql.clickhouse import CAPABILITIES as CLICKHOUSE_CAPABILITIES
from prama.connect.sources.sql.clickhouse import ClickHouseConnector
from prama.connect.sources.sql.jdbc import CAPABILITIES as JDBC_CAPABILITIES
from prama.connect.sources.sql.jdbc import DIALECTS, JdbcConnector
from prama.connect.sources.sql.postgres import CAPABILITIES as POSTGRES_CAPABILITIES
from prama.connect.sources.sql.postgres import PostgresConnector
from prama.connect.sources.sql.snowflake import CAPABILITIES as SNOWFLAKE_CAPABILITIES
from prama.connect.sources.sql.snowflake import SnowflakeConnector
from prama.connect.sources.sqlite import CAPABILITIES as SQLITE_CAPABILITIES
from prama.connect.sources.sqlite import SqliteConnector

FILESYSTEM_OVERLAY: dict[str, FieldPresentation] = {
    "root_path": FieldPresentation(
        label="Folder",
        help=(
            "The directory Prama reads from. For a feed, this is the landing zone — "
            "the folder the file arrives in, not the file itself."
        ),
        input_kind=InputKind.PATH,
        required=True,
        order=10,
    ),
    "file_pattern": FieldPresentation(
        label="File pattern",
        help=(
            "Which files to consider, e.g. positions_*.csv. Date tokens are matched "
            "as wildcards; the arrival window is declared on the dataset, not here."
        ),
        order=20,
    ),
    "max_file_bytes": FieldPresentation(
        label="Digest ceiling",
        help=(
            "How much of a file to hash when recording a snapshot. An exact "
            "identifier for a 40 GB extract is not worth 40 GB of reading; the size "
            "and modification time recorded alongside make a collision implausible."
        ),
        input_kind=InputKind.BYTES,
        group="advanced",
        order=110,
    ),
    "schema_sample_rows": FieldPresentation(
        label="Rows sampled for schema inference",
        help="How many rows to read when inferring CSV column types.",
        input_kind=InputKind.NUMBER,
        group="advanced",
        order=120,
    ),
}

SQLITE_OVERLAY: dict[str, FieldPresentation] = {
    "database_path": FieldPresentation(
        label="Database file",
        help="Path to the .db or .sqlite file. It is opened read-only.",
        input_kind=InputKind.PATH,
        required=True,
        order=10,
    ),
    "busy_timeout_seconds": FieldPresentation(
        label="Busy timeout",
        help="How long to wait when another writer holds the database.",
        input_kind=InputKind.DURATION,
        group="advanced",
        order=110,
    ),
    "include_views": FieldPresentation(
        label="Include views",
        help="Whether discovery offers views as well as tables.",
        input_kind=InputKind.BOOLEAN,
        order=20,
    ),
}

POSTGRES_OVERLAY: dict[str, FieldPresentation] = {
    "host": FieldPresentation(label="Host", required=True, order=10),
    "port": FieldPresentation(label="Port", input_kind=InputKind.NUMBER, order=20),
    "database": FieldPresentation(label="Database", required=True, order=30),
    "user": FieldPresentation(
        label="User",
        help=(
            "A role with SELECT on what Prama should read, and nothing more. "
            "The session is opened read-only at the server regardless, but a "
            "read-only role is the guarantee that survives a misconfiguration."
        ),
        order=40,
    ),
    "password": FieldPresentation(
        label="Password",
        help="Stored as a vault reference, never in the connection record.",
        input_kind=InputKind.PASSWORD,
        secret=True,
        order=50,
    ),
    "dsn": FieldPresentation(
        label="Connection string",
        help=(
            "postgresql://... — an alternative to the fields above, for estates "
            "that already manage connection strings centrally."
        ),
        input_kind=InputKind.PASSWORD,
        secret=True,
        group="advanced",
        order=60,
    ),
    "ssl_mode": FieldPresentation(
        label="TLS mode",
        help="disable, prefer, require, verify-ca or verify-full.",
        order=70,
    ),
    "schemas": FieldPresentation(
        label="Schemas",
        help=(
            "Restrict discovery to these schemas. Leave empty to offer everything "
            "the connecting role can already read."
        ),
        order=80,
    ),
    "include_views": FieldPresentation(
        label="Include views",
        help="Whether discovery offers views and materialised views as well as tables.",
        input_kind=InputKind.BOOLEAN,
        order=90,
    ),
    "statement_timeout_ms": FieldPresentation(
        label="Statement timeout",
        help=(
            "The ceiling on any single query. Prama reading a table must never be "
            "able to pin the database the business is using."
        ),
        input_kind=InputKind.DURATION,
        group="advanced",
        order=110,
    ),
    "connect_timeout_seconds": FieldPresentation(
        label="Connection timeout",
        input_kind=InputKind.DURATION,
        group="advanced",
        order=120,
    ),
    "application_name": FieldPresentation(
        label="Application name",
        help=(
            "How this connection identifies itself in pg_stat_activity, so a DBA "
            "who finds an unfamiliar query can see whose it is."
        ),
        group="advanced",
        order=130,
    ),
}

OBJECTSTORE_OVERLAY: dict[str, FieldPresentation] = {
    "uri": FieldPresentation(
        label="Location",
        help=(
            "The bucket and prefix, e.g. s3://risk-lake/positions. Point it at the "
            "prefix a dataset lives under, not at a single file: a partitioned table "
            "is one dataset, not one per day."
        ),
        required=True,
        order=10,
    ),
    "access_key_id": FieldPresentation(
        label="Access key",
        help="Leave empty to use the machine's own role, which is the safer arrangement.",
        order=20,
    ),
    "secret_access_key": FieldPresentation(
        label="Secret key",
        help="Stored as a vault reference, never in the connection record.",
        input_kind=InputKind.PASSWORD,
        secret=True,
        order=30,
    ),
    "session_token": FieldPresentation(
        label="Session token",
        help="For temporary credentials issued by an identity provider.",
        input_kind=InputKind.PASSWORD,
        secret=True,
        group="advanced",
        order=40,
    ),
    "region": FieldPresentation(label="Region", order=50),
    "endpoint": FieldPresentation(
        label="Endpoint",
        help="For an S3-compatible store that is not AWS. Leave empty for AWS itself.",
        group="advanced",
        order=60,
    ),
    "use_ssl": FieldPresentation(
        label="Use TLS",
        input_kind=InputKind.BOOLEAN,
        group="advanced",
        order=70,
    ),
    "url_style": FieldPresentation(
        label="URL style",
        help="vhost for AWS; path for MinIO and most on-premise stores.",
        choices=("vhost", "path"),
        input_kind=InputKind.SELECT,
        group="advanced",
        order=80,
    ),
    "file_pattern": FieldPresentation(
        label="File pattern",
        help="Which objects to consider, e.g. *.parquet. Everything by default.",
        order=90,
    ),
    "max_objects": FieldPresentation(
        label="Object ceiling",
        help=(
            "Refuse rather than truncate above this many objects. A partial listing "
            "would profile part of the data as though it were all of it."
        ),
        input_kind=InputKind.NUMBER,
        group="advanced",
        order=110,
    ),
}

REST_OVERLAY: dict[str, FieldPresentation] = {
    "base_url": FieldPresentation(
        label="Base URL",
        help="The API's root, e.g. https://api.example.com/v2. Endpoints hang off it.",
        input_kind=InputKind.TEXT,
        required=True,
        order=10,
    ),
    "endpoints": FieldPresentation(
        label="Endpoints",
        help=(
            "Which paths are datasets. An API does not enumerate itself, so Prama "
            "reads what you name here and guesses nothing."
        ),
        required=True,
        order=20,
    ),
    "records_path": FieldPresentation(
        label="Records field",
        help=(
            "Where the rows sit inside the response, e.g. data.items. Leave blank "
            "if the endpoint returns a bare array."
        ),
        order=30,
    ),
    "next_path": FieldPresentation(
        label="Next-page field",
        help=(
            "Where the link to the next page sits, e.g. links.next. Without this or "
            "a page parameter, Prama reads one page and one page is not a "
            "population."
        ),
        order=40,
    ),
    "page_param": FieldPresentation(
        label="Page parameter",
        help="For APIs that page by number rather than by link, e.g. page.",
        order=50,
    ),
    "page_limit": FieldPresentation(
        label="Page ceiling",
        help=(
            "How many pages one read will follow before stopping. A bound, not a "
            "preference: an endpoint whose next link cycles would otherwise read "
            "forever. A read stopped by it says so."
        ),
        order=60,
    ),
    "token": FieldPresentation(
        label="Credential",
        help=(
            "A secret reference, never the token itself — env://ACME_API_TOKEN. It "
            "is sent as a header, because a token in a URL is a token in every "
            "access log between here and the server."
        ),
        input_kind=InputKind.PASSWORD,
        order=70,
    ),
}


JDBC_OVERLAY: dict[str, FieldPresentation] = {
    "jdbc_url": FieldPresentation(
        label="JDBC URL",
        help="e.g. jdbc:oracle:thin:@host:1521/SERVICE. The driver's own form.",
        input_kind=InputKind.TEXT,
        required=True,
        order=10,
    ),
    "driver_class": FieldPresentation(
        label="Driver class",
        help="e.g. oracle.jdbc.OracleDriver. Named in the driver's documentation.",
        required=True,
        order=20,
    ),
    "driver_path": FieldPresentation(
        label="Driver jar",
        help=(
            "Path to the jar on this host. Prama does not redistribute drivers and "
            "will not fetch one — the jar is somebody else's code running in our "
            "process, so the deployment chooses it."
        ),
        input_kind=InputKind.PATH,
        required=True,
        order=30,
    ),
    "dialect": FieldPresentation(
        label="Dialect",
        help=(
            "Which database is on the other end. JDBC is a transport, not a "
            "dialect: guessing would send one database's SQL to another and "
            f"produce a control that compiles and then fails. One of: {', '.join(DIALECTS)}."
        ),
        input_kind=InputKind.SELECT,
        required=True,
        order=40,
    ),
    "user": FieldPresentation(label="User", order=50),
    "password": FieldPresentation(
        label="Password",
        help="A secret reference, never the password itself — env://ORACLE_PASSWORD.",
        input_kind=InputKind.PASSWORD,
        order=60,
    ),
    "fetch_size": FieldPresentation(
        label="Fetch size",
        help=(
            "Rows per round trip. Without it the driver materialises the whole "
            "result in the JVM heap and a large read fails on memory."
        ),
        order=70,
    ),
}


SNOWFLAKE_OVERLAY: dict[str, FieldPresentation] = {
    "account": FieldPresentation(
        label="Account",
        help="The account identifier, e.g. xy12345.eu-west-1. Not the URL.",
        input_kind=InputKind.TEXT,
        required=True,
        order=10,
    ),
    "user": FieldPresentation(label="User", required=True, order=20),
    "password": FieldPresentation(
        label="Password",
        help="A secret reference, never the password itself — env://SNOWFLAKE_PASSWORD.",
        input_kind=InputKind.PASSWORD,
        order=30,
    ),
    "role": FieldPresentation(
        label="Role",
        help=(
            "Connect as a role with SELECT and nothing more. Snowflake has no "
            "session read-only switch, so this is what actually stops Prama "
            "writing — not the product's good manners."
        ),
        order=40,
    ),
    "warehouse": FieldPresentation(
        label="Warehouse",
        help=(
            "Which warehouse runs the queries, and therefore whose credits they "
            "spend. A query with no warehouse has nothing to run on."
        ),
        required=True,
        order=50,
    ),
    "database": FieldPresentation(label="Database", required=True, order=60),
    "schema": FieldPresentation(
        label="Schema",
        help="The default for unqualified names. Discovery still sees the others.",
        order=70,
    ),
}


CLICKHOUSE_OVERLAY: dict[str, FieldPresentation] = {
    "host": FieldPresentation(label="Host", required=True, order=10),
    "port": FieldPresentation(label="Port", help="8123 for HTTP, 8443 for HTTPS.", order=20),
    "database": FieldPresentation(label="Database", required=True, order=30),
    "user": FieldPresentation(label="User", order=40),
    "password": FieldPresentation(
        label="Password",
        help="A secret reference, never the password itself — env://CLICKHOUSE_PASSWORD.",
        input_kind=InputKind.PASSWORD,
        order=50,
    ),
    "secure": FieldPresentation(
        label="TLS", help="Use HTTPS. On for anything not on a private network.", order=60
    ),
}


MONGO_OVERLAY: dict[str, FieldPresentation] = {
    "host": FieldPresentation(label="Host", order=10),
    "port": FieldPresentation(label="Port", order=20),
    "database": FieldPresentation(
        label="Database",
        help=(
            "Which database. A deployment holds several and Prama will not pick "
            "one — an estate declared against the wrong database is worse than "
            "one that failed to connect."
        ),
        required=True,
        order=30,
    ),
    "user": FieldPresentation(label="User", order=40),
    "password": FieldPresentation(
        label="Password",
        help="A secret reference, never the password itself — env://MONGO_PASSWORD.",
        input_kind=InputKind.PASSWORD,
        order=50,
    ),
    "auth_source": FieldPresentation(
        label="Auth database",
        help="Where the user is defined, usually `admin` rather than the data database.",
        order=60,
    ),
    "schema_sample_documents": FieldPresentation(
        label="Schema sample",
        help=(
            "How many documents the inferred schema is taken from. The count is "
            "reported with it: 'no document has this field' and 'none of the two "
            "hundred I looked at' are different claims."
        ),
        order=70,
    ),
}


BUILTIN: tuple[tuple[type, CapabilityMatrix, dict[str, FieldPresentation]], ...] = (
    (FilesystemConnector, FILESYSTEM_CAPABILITIES, FILESYSTEM_OVERLAY),
    (SqliteConnector, SQLITE_CAPABILITIES, SQLITE_OVERLAY),
    (PostgresConnector, POSTGRES_CAPABILITIES, POSTGRES_OVERLAY),
    (ObjectStoreConnector, OBJECTSTORE_CAPABILITIES, OBJECTSTORE_OVERLAY),
    (RestConnector, REST_CAPABILITIES, REST_OVERLAY),
    (JdbcConnector, JDBC_CAPABILITIES, JDBC_OVERLAY),
    (SnowflakeConnector, SNOWFLAKE_CAPABILITIES, SNOWFLAKE_OVERLAY),
    (ClickHouseConnector, CLICKHOUSE_CAPABILITIES, CLICKHOUSE_OVERLAY),
    (MongoConnector, MONGO_CAPABILITIES, MONGO_OVERLAY),
)


def register_builtin(registry: ConnectorRegistry | None = None) -> ConnectorRegistry:
    """Register every first-party connector. Idempotent."""
    target = registry or default_registry()
    for connector_class, capabilities, overlay in BUILTIN:
        target.register(
            connector_class,
            capabilities=capabilities,
            overlay=overlay,
            replace=True,
        )
    return target
