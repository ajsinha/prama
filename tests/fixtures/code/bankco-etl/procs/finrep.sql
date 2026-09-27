-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE.
CREATE PROCEDURE rpt.load_finrep
AS
BEGIN
    INSERT INTO rpt.finrep_line_23 (account_id, amount)
    SELECT p.account_id, p.exposure_usd
    FROM mart.positions p;

    DECLARE @t NVARCHAR(128) = 'rpt.finrep_line_23';
    EXEC('INSERT INTO rpt.audit_log SELECT * FROM ' + @t);
END
