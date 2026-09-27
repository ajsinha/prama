# Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
# Proprietary; see LICENSE.
from airflow import DAG
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

with DAG("finrep_daily", schedule="@daily") as dag:
    SQLExecuteQueryOperator(task_id="load", sql="EXEC rpt.load_finrep")
    SQLExecuteQueryOperator(
        task_id="archive",
        sql="INSERT INTO rpt.finrep_archive (account_id, amount) "
        "SELECT account_id, amount FROM rpt.finrep_line_23",
    )
