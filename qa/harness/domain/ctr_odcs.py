import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.contract import odcs
from prama.derive.declaration import DatasetDeclaration, AttributeDeclaration
from prama.semantic.values import Criticality, Optionality

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

def contract1():
    return {
        "schema": [{"name":"orders", "description":"orders table",
                    "properties":[
                        {"name":"id","logicalType":"string","required":True},
                        {"name":"amount","logicalType":"number","required":False},
                        {"name":"created","logicalType":"date","required":True},
                        {"name":"status","logicalType":"string","required":False},
                        {"name":"note","logicalType":"string","required":False},
                    ]}],
        "description": {"purpose":"track orders","usage":"used by finance"},
    }

@block("CTR-001")
def _():
    c = contract1()
    imp = odcs.load(c)
    d = imp.declaration
    ok = d is not None and len(d.attributes)==5 and d.name=='orders' and d.purpose=='track orders' and d.description=='used by finance'
    ok2 = all(f in ' '.join(imp.defaulted) for f in ('criticality','grain','rhythm'))
    R("CTR-001", ok and ok2, f"name={d.name if d else None} attrs={len(d.attributes) if d else None} purpose={d.purpose if d else None} description={d.description if d else None} defaulted={imp.defaulted}")

@block("CTR-002")
def _():
    c = contract1()
    c['slaProperties']=[{'x':1}]; c['team']=[{'x':1}]; c['roles']=[{'x':1}]; c['support']=[{'x':1}]; c['price']={'x':1}
    imp = odcs.load(c)
    desc = imp.describe()
    ok = all(k in desc for k in ('slaProperties','team','roles','support','price')) and all('no field for it' in desc for _ in [1])
    R("CTR-002", ok, f"ignored={imp.ignored}")

@block("CTR-003")
def _():
    c = contract1()
    c['slaProperties']=[{'x':1}]
    imp = odcs.load(c)
    desc = imp.describe()
    ok = desc.index('field(s) the contract does not carry') < desc.index('not imported')
    R("CTR-003", ok, f"describe={desc}")

@block("CTR-004")
def _():
    imp = odcs.load({})
    ok = imp.declaration is None and len(imp.ignored)==1
    R("CTR-004", ok, f"declaration={imp.declaration} ignored={imp.ignored}")

@block("CTR-005")
def _():
    c = contract1()
    c['schema'] = c['schema']*4
    imp = odcs.load(c)
    ok = imp.declaration is not None and any('3 further schema' in i for i in imp.ignored)
    R("CTR-005", ok, f"ignored={imp.ignored}")

@block("CTR-006")
def _():
    from prama.contract.quality import controls_from
    c = contract1()
    c['schema'] = [dict(c['schema'][0], quality=[{"rule":"nullCheck","column":"id"}]),
                    {"name":"payments","properties":[{"name":"pid"}], "quality":[{"rule":"nullCheck","column":"pid"}]}]
    result = controls_from(c)
    text = repr(result.to_dict()) if hasattr(result,'to_dict') else repr(result)
    mentions_second_schema = 'payments' in text or 'pid' in text
    R("CTR-006", mentions_second_schema, f"mentions_second_schema_or_named_omission={mentions_second_schema}; result_summary={text[:300]}")

@block("CTR-007")
def _():
    results_ = {}
    for lvl, tier in (('critical',Criticality.TIER_1),('high',Criticality.TIER_2),('medium',Criticality.TIER_3),('low',Criticality.TIER_4)):
        c = contract1(); c['criticality']=lvl
        imp = odcs.load(c)
        results_[lvl] = (imp.declaration.criticality, 'criticality' in ' '.join(imp.defaulted))
    ok = all(results_[l][0]==t and not results_[l][1] for l,t in zip(('critical','high','medium','low'),(Criticality.TIER_1,Criticality.TIER_2,Criticality.TIER_3,Criticality.TIER_4)))
    R("CTR-007", ok, f"{results_}")

@block("CTR-008")
def _():
    c = contract1(); c['criticality']='very high'
    imp = odcs.load(c)
    ok = imp.declaration.criticality==Criticality.TIER_4 and any('criticality' in d for d in imp.defaulted)
    R("CTR-008", ok, f"criticality={imp.declaration.criticality} defaulted={imp.defaulted}")

@block("CTR-009")
def _():
    c = contract1()
    c['schema'][0]['properties'].append({"name":"price","logicalType":"money"})
    imp = odcs.load(c)
    attr = next(a for a in imp.declaration.attributes if a.name=='price')
    ok = attr.semantic_type=='' and any('price' in i and 'money' in i for i in imp.ignored)
    R("CTR-009", ok, f"semantic_type={attr.semantic_type!r} ignored={imp.ignored}")

@block("CTR-010")
def _():
    c = contract1()
    c['schema'][0]['properties'] = [
        {"name":"a","required":True},{"name":"b","required":False},{"name":"c"}]
    imp = odcs.load(c)
    opts = {a.name: a.optionality for a in imp.declaration.attributes}
    ok = opts['a']==Optionality.MANDATORY and opts['b']==Optionality.OPTIONAL and opts['c']==Optionality.OPTIONAL
    R("CTR-010", ok, f"{opts}")

@block("CTR-011")
def _():
    c = contract1()
    c['schema'][0]['properties'] = [{"name":"amt","precision":18,"scale":2}]
    imp = odcs.load(c)
    d = imp.declaration
    dumped = odcs.dump(d)
    imp2 = odcs.load(dumped)
    a2 = imp2.declaration.attributes[0]
    ok = a2.numeric_precision==18 and a2.numeric_scale==2 and dumped['schema'][0]['properties'][0]['logicalType']=='number'
    R("CTR-011", ok, f"reimport_precision={a2.numeric_precision} scale={a2.numeric_scale} exported_type={dumped['schema'][0]['properties'][0]['logicalType']}")

@block("CTR-012")
def _():
    d = DatasetDeclaration(name='orders', purpose='p', description='d', criticality=Criticality.TIER_2,
                            tags=('a','b'), attributes=(
                                AttributeDeclaration(name='id', definition='the id', optionality=Optionality.MANDATORY),
                                AttributeDeclaration(name='amt', definition='amount', optionality=Optionality.OPTIONAL, numeric_precision=10, numeric_scale=2),
                            ))
    dumped = odcs.dump(d)
    imp = odcs.load(dumped)
    d2 = imp.declaration
    ok = (d2.name==d.name and d2.purpose==d.purpose and d2.description==d.description and
          d2.criticality==d.criticality and d2.tags==d.tags and
          [a.name for a in d2.attributes]==[a.name for a in d.attributes] and
          [a.optionality for a in d2.attributes]==[a.optionality for a in d.attributes])
    R("CTR-012", ok, f"round_trip_equal_fields={ok}; d2={d2}")

@block("CTR-013")
def _():
    d = DatasetDeclaration(name='orders', purpose='the purpose', description='the description', criticality=Criticality.TIER_2)
    dumped1 = odcs.dump(d)
    d1 = odcs.load(dumped1).declaration
    dumped2 = odcs.dump(d1)
    d2 = odcs.load(dumped2).declaration
    ok = d1.purpose==d.purpose and d1.description==d.description and d2.purpose==d.purpose and d2.description==d.description
    R("CTR-013", ok, f"orig(purpose={d.purpose!r},desc={d.description!r}); after1(purpose={d1.purpose!r},desc={d1.description!r}); after2(purpose={d2.purpose!r},desc={d2.description!r})")

@block("CTR-014")
def _():
    d = DatasetDeclaration(name='parties', attributes=(
        AttributeDeclaration(name='lei_code', semantic_type='lei'),
    ))
    dumped = odcs.dump(d)
    imp = odcs.load(dumped)
    a2 = imp.declaration.attributes[0]
    preserved = a2.semantic_type=='lei'
    reported = any('lei' in i.lower() or 'semantic' in i.lower() for i in imp.ignored)
    ok = preserved or reported
    R("CTR-014", ok, f"exported_logicalType={dumped['schema'][0]['properties'][0]['logicalType']!r}; reimported_semantic_type={a2.semantic_type!r} preserved={preserved} reported_as_lost={reported} ignored={imp.ignored}")

@block("CTR-015")
def _():
    cases = [{"schema": {"name": "x"}}, {"schema": ["orders"]}, {"schema": [None]}]
    from prama.core.errors import ValidationError
    detail = []
    ok = True
    for c in cases:
        try:
            odcs.load(c)
            detail.append(f"{c}: no exception (may be fine if it degrades gracefully)")
        except ValidationError as e:
            detail.append(f"{c}: ValidationError({e})")
        except Exception as e:
            ok = False
            detail.append(f"{c}: BARE {type(e).__name__}: {e}")
    R("CTR-015", ok, "; ".join(detail))

@block("CTR-016")
def _():
    c = contract1()
    imp = odcs.load(c)
    R("CTR-016", not imp.is_complete, f"is_complete={imp.is_complete} defaulted={imp.defaulted} (grain/rhythm always defaulted for any real contract)")

print("=== CTR odcs 001-016 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
