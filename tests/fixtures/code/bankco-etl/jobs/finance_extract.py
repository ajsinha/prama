# Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
# Proprietary; see LICENSE.
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("postgresql://warehouse")


def main() -> None:
    trades = pd.read_sql_table("trades", engine, schema="stg")
    daily = trades[["account_id", "notional", "trade_date"]]
    daily = daily.rename(columns={"trade_date": "business_date"})
    daily["notional_k"] = daily["notional"] / 1000
    daily = daily.dropna()
    daily.to_sql("daily_notional", engine, schema="fin", if_exists="replace")


if __name__ == "__main__":
    main()
