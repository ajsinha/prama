"""dbt manifests into the lineage store (E2).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.lineage.ingest import dbt_lineage

#: A jaffle_shop-shaped manifest, cut to two models: one compiled, one not.
MANIFEST = {
    "nodes": {
        "model.jaffle_shop.customers": {
            "resource_type": "model",
            "relation_name": '"analytics"."main"."customers"',
            "compiled_code": (
                "select c.customer_id, c.first_name, count(o.order_id) as number_of_orders "
                'from "analytics"."main"."stg_customers" c '
                'left join "analytics"."main"."stg_orders" o on c.customer_id = o.customer_id '
                "group by c.customer_id, c.first_name"
            ),
        },
        "model.jaffle_shop.orders": {
            "resource_type": "model",
            "relation_name": '"analytics"."main"."orders"',
            "raw_code": "select * from {{ ref('stg_orders') }}",
        },
        "test.jaffle_shop.unique_customers": {"resource_type": "test"},
    }
}

GOLDEN = {
    ("analytics.main.stg_customers.customer_id", "analytics.main.customers.customer_id"),
    ("analytics.main.stg_customers.first_name", "analytics.main.customers.first_name"),
    ("analytics.main.stg_orders.order_id", "analytics.main.customers.number_of_orders"),
}


def test_a_compiled_model_yields_its_known_edges() -> None:
    edges, gaps, models = dbt_lineage(MANIFEST)
    assert models == 2
    found = {
        (e.source.qualified, e.target.qualified) for e in edges if e.transform.value != "filter"
    }
    assert found >= GOLDEN


def test_an_uncompiled_model_is_a_gap_not_a_guess() -> None:
    _, gaps, _ = dbt_lineage(MANIFEST)
    assert any(g.kind == "uncompiled" and "model.jaffle_shop.orders" in g.detail for g in gaps)
