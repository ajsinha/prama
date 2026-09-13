import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from decimal import Decimal
from prama.packs.banking import iso20022, swift

results = []
def R(id_, ok, obs):
    results.append((id_, "PASS" if ok else "FAIL", obs))

def block(id_):
    def deco(fn):
        try:
            fn()
        except AssertionError as e:
            R(id_, False, f"AssertionError: {e}")
        except Exception as e:
            R(id_, False, f"{type(e).__name__}: {e}")
    return deco

PACS008 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
  <FIToFICstmrCdtTrf>
    <GrpHdr><MsgId>MSG-001</MsgId><CreDtTm>2026-09-09T10:15:00</CreDtTm>
      <NbOfTxs>2</NbOfTxs><CtrlSum>1500.00</CtrlSum>
      <IntrBkSttlmDt>2026-09-10</IntrBkSttlmDt>
      <SttlmInf><SttlmMtd>INDA</SttlmMtd></SttlmInf></GrpHdr>
    <CdtTrfTxInf>
      <PmtId><TxId>TX-1</TxId><EndToEndId>E2E-1</EndToEndId>
        <UETR>7f8a1c2d-3e4b-4a5c-8d9e-0f1a2b3c4d5e</UETR></PmtId>
      <IntrBkSttlmAmt Ccy="EUR">1000.00</IntrBkSttlmAmt>
      <Dbtr><Nm>Acme GmbH</Nm></Dbtr>
      <DbtrAcct><Id><IBAN>DE89370400440532013000</IBAN></Id></DbtrAcct>
      <DbtrAgt><FinInstnId><BICFI>COBADEFFXXX</BICFI></FinInstnId></DbtrAgt>
      <Cdtr><Nm>Beta SARL</Nm></Cdtr>
      <CdtrAcct><Id><IBAN>FR1420041010050500013M02606</IBAN></Id></CdtrAcct>
      <CdtrAgt><FinInstnId><BICFI>BNPAFRPPXXX</BICFI></FinInstnId></CdtrAgt>
      <RmtInf><Ustrd>Invoice 4471</Ustrd></RmtInf></CdtTrfTxInf>
    <CdtTrfTxInf>
      <PmtId><TxId>TX-2</TxId></PmtId>
      <IntrBkSttlmAmt Ccy="EUR">500.00</IntrBkSttlmAmt>
      <DbtrAgt><FinInstnId><BIC>COBADEFFXXX</BIC></FinInstnId></DbtrAgt>
      <CdtrAgt><FinInstnId><BICFI>BUKBGB22XXX</BICFI></FinInstnId></CdtrAgt></CdtTrfTxInf>
  </FIToFICstmrCdtTrf></Document>"""

@block("PCK-128")
def _():
    p = iso20022.parse_pacs008(PACS008)
    ok = p.stated_count==3 or p.stated_count==2  # header says NbOfTxs=2 but file has 2 tx -- adjust below
    R("PCK-128", None, f"PLACEHOLDER, see fixed version below")

# Build a version with NbOfTxs=3 but only 2 transactions, per catalogue precondition
PACS008_MISCOUNT = PACS008.replace("<NbOfTxs>2</NbOfTxs>", "<NbOfTxs>3</NbOfTxs>")

@block("PCK-128")
def _():
    p = iso20022.parse_pacs008(PACS008_MISCOUNT)
    ok = p.stated_count==3 and p.actual_count==2 and p.count_agrees is False
    R("PCK-128", ok, f"stated_count={p.stated_count} actual_count={p.actual_count} count_agrees={p.count_agrees}")

@block("PCK-129")
def _():
    no_ctrlsum = PACS008.replace("<CtrlSum>1500.00</CtrlSum>", "")
    p = iso20022.parse_pacs008(no_ctrlsum)
    ok = p.sum_agrees is None
    R("PCK-129", ok, f"sum_agrees={p.sum_agrees} control_sum={p.control_sum}")

@block("PCK-130")
def _():
    frac = PACS008.replace("<NbOfTxs>2</NbOfTxs>", "<NbOfTxs>2.5</NbOfTxs>")
    p = iso20022.parse_pacs008(frac)
    has_defect = any("2.5" in d or "count" in d.lower() or "malformed" in d.lower() for d in p.defects)
    R("PCK-130", has_defect, f"stated_count={p.stated_count} count_agrees={p.count_agrees} defects={p.defects}")

@block("PCK-131")
def _():
    # three unreadable amounts whose CtrlSum matches remaining sum
    bad = PACS008.replace('<IntrBkSttlmAmt Ccy="EUR">1000.00</IntrBkSttlmAmt>', '<IntrBkSttlmAmt Ccy="EUR">NOTANUMBER</IntrBkSttlmAmt>')
    bad = bad.replace("<CtrlSum>1500.00</CtrlSum>", "<CtrlSum>500.00</CtrlSum>")
    p = iso20022.parse_pacs008(bad)
    ok = p.sum_agrees is True and p.unreadable_amounts == 1
    R("PCK-131", ok, f"sum_agrees={p.sum_agrees} unreadable_amounts={p.unreadable_amounts} transaction_total={p.transaction_total} -- caveat reaches to_dict? {p.to_dict()}")

@block("PCK-132")
def _():
    p = iso20022.parse_pacs008(PACS008)
    tx2 = [t for t in p.transactions if t.reference=='TX-2'][0]
    ok = tx2.value_date == '2026-09-10'
    R("PCK-132", ok, f"tx2.value_date={tx2.value_date!r} (header IntrBkSttlmDt=2026-09-10, tx has none of its own)")

@block("PCK-133")
def _():
    p = iso20022.parse_pacs008(PACS008)
    tx1 = [t for t in p.transactions if t.reference=='TX-1'][0]  # uses BICFI
    tx2 = [t for t in p.transactions if t.reference=='TX-2'][0]  # uses BIC
    ok = tx1.debtor_agent_bic == 'COBADEFFXXX' and tx2.debtor_agent_bic == 'COBADEFFXXX'
    R("PCK-133", ok, f"tx1(BICFI)={tx1.debtor_agent_bic!r} tx2(BIC)={tx2.debtor_agent_bic!r}")

CAMT053 = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">
<BkToCstmrStmt><GrpHdr><MsgId>C-1</MsgId></GrpHdr>
<Stmt>
  <Id>STMT1</Id>
  <Acct><Id><IBAN>GB33BUKB20201555555555</IBAN></Id></Acct>
  <Bal><Tp><CdOrPrtry><Cd>ITBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">999.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-09-08</Dt></Dt></Bal>
  <Bal><Tp><CdOrPrtry><Cd>CLAV</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">888.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-09-09</Dt></Dt></Bal>
  <Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">10000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-09-08</Dt></Dt></Bal>
  <Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">11250.25</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-09-09</Dt></Dt></Bal>
  <Ntry><Amt Ccy="EUR">1500.50</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2026-09-09</Dt></BookgDt><ValDt><Dt>2026-09-09</Dt></ValDt></Ntry>
  <Ntry><Amt Ccy="EUR">250.25</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2026-09-09</Dt></BookgDt><ValDt><Dt>2026-09-09</Dt></ValDt></Ntry>
</Stmt>
</BkToCstmrStmt></Document>"""

@block("PCK-134")
def _():
    c = iso20022.parse_camt053(CAMT053)
    ok = c.opening_balance == Decimal('10000.00') and c.closing_balance == Decimal('11250.25')
    R("PCK-134", ok, f"opening={c.opening_balance} closing={c.closing_balance} (ITBD=999,CLAV=888 must NOT be picked)")

@block("PCK-135")
def _():
    only_prcd = CAMT053.replace("<Cd>OPBD</Cd>", "<Cd>PRCD</Cd>")
    c = iso20022.parse_camt053(only_prcd)
    ok = c.opening_balance == Decimal('10000.00') and not any('opening' in d for d in c.defects)
    R("PCK-135", ok, f"opening={c.opening_balance} defects={c.defects}")

@block("PCK-136")
def _():
    no_indicator = CAMT053.replace("<Amt Ccy=\"EUR\">1500.50</Amt><CdtDbtInd>CRDT</CdtDbtInd>", "<Amt Ccy=\"EUR\">1500.50</Amt>")
    c = iso20022.parse_camt053(no_indicator)
    e = c.entries[0]
    ok = e.is_credit is not True  # expect a defect or unresolved, not silent False->debit
    has_defect = len(c.defects) > 0 and any('CdtDbtInd' in d or 'indicator' in d.lower() for d in c.defects)
    R("PCK-136", has_defect, f"entry.is_credit={e.is_credit} entry.signed={e.signed} defects={c.defects}")

@block("PCK-137")
def _():
    two_stmt = CAMT053.replace("</Stmt>\n</BkToCstmrStmt>", "</Stmt><Stmt><Id>STMT2</Id><Acct><Id><IBAN>DE89370400440532013000</IBAN></Id></Acct></Stmt>\n</BkToCstmrStmt>")
    c = iso20022.parse_camt053(two_stmt)
    ok = c.account == 'DE89370400440532013000' or any('second' in d.lower() or 'only the first' in d.lower() for d in c.defects)
    R("PCK-137", ok, f"account_read={c.account!r} defects={c.defects} (first Stmt's account is GB33...; if this shows GB33 and no mention of the 2nd, both are lost silently)")

@block("PCK-138")
def _():
    header_only = """<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
    <FIToFICstmrCdtTrf><GrpHdr><MsgId>M</MsgId><NbOfTxs>0</NbOfTxs></GrpHdr></FIToFICstmrCdtTrf></Document>"""
    p = iso20022.parse_pacs008(header_only)
    ok = any('no credit transfer' in d for d in p.defects) and p.transaction_total==Decimal(0) and p.count_agrees is True
    R("PCK-138", ok, f"defects={p.defects} transaction_total={p.transaction_total} count_agrees={p.count_agrees}")

@block("PCK-139")
def _():
    MT103 = """{1:F01COBADEFFAXXX0000000000}{2:I103BNPAFRPPXXXXN}{4:
:20:PAY-2026-0001
:23B:CRED
:32A:260910EUR1000,00
:50K:/DE89370400440532013000
ACME GMBH
BERLIN
:52A:COBADEFFXXX
:57A:BNPAFRPPXXX
:59:/FR1420041010050500013M02606
BETA SARL
:70:INVOICE 4471
:71A:SHA
-}"""
    mt_row = swift.payment(swift.parse(MT103))
    p = iso20022.parse_pacs008(PACS008)
    mx_row = p.transactions[0].to_dict()
    mt_keys = set(mt_row.keys())
    mx_keys = set(mx_row.keys())
    shared = mt_keys & mx_keys
    R("PCK-139", None, f"MT keys={sorted(mt_keys)}; MX keys={sorted(mx_keys)}; shared_key_names={sorted(shared)} -- reference,amount,currency,value_date shared; MT has sender_bic/ordering_institution/beneficiary while MX has debtor_agent_bic/debtor_name/creditor_name -- no automatic join field pairing exists in either vocabulary beyond amount/currency/value_date/reference")

print("=== PCK ISO20022 128-139 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
