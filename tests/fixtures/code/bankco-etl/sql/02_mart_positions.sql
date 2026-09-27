-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE.
-- Positions in USD, by account.
CREATE VIEW mart.positions AS
WITH fx AS (SELECT r.ccy, r.rate FROM ref.fx_rates r)
SELECT s.account_id AS account_id,
       SUM(s.notional * fx.rate) AS exposure_usd
FROM stg.trades s
JOIN fx ON s.ccy = fx.ccy
GROUP BY s.account_id;
