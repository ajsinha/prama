-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE.
-- Stage booked trades from the raw feed.
INSERT INTO stg.trades (trade_id, account_id, notional, ccy, trade_date)
SELECT t.id, t.acct, t.notional_amt, t.currency, t.trade_dt
FROM raw.trades t
WHERE t.status = 'BOOKED';
