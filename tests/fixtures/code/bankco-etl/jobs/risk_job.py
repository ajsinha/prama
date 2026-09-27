# Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE.
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.getOrCreate()
trades = spark.table("stg.trades")
trades.select(F.col("account_id"), F.col("notional")).write.saveAsTable("risk.var_input")
