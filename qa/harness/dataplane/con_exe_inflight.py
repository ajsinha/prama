import sys, time, random
sys.path.insert(0, ".")
from qa_common import log
from prama.execute.inflight import Pipeline, DeadLetterFull, Outcome, Throughput, Report
from prama.execute.actions import Action
from prama.execute.transport import (
    MemoryTransport, StreamMessage, Position, StreamRunner, TransportError, run_until_idle,
    _highest_per_partition,
)
from prama.core.errors import PramaError

class FakeVerdict:
    def __init__(self, is_violation=False, unknown=False):
        self.is_violation = is_violation
        self.unknown = unknown

class FakePlan:
    def __init__(self, plan_id):
        self.plan_id = plan_id

class FakeAssertion:
    def __init__(self, plan_id, violates=False, unknown=False):
        self.plan = FakePlan(plan_id)
        self._violates = violates
        self._unknown = unknown
    def judge(self, message):
        return FakeVerdict(is_violation=self._violates, unknown=self._unknown)

class NoPlanAssertion:
    def judge(self, message):
        return FakeVerdict(is_violation=True)

def exe070():
    obs = {}
    for action in (Action.QUARANTINE, Action.BLOCK):
        try:
            Pipeline([], action=action, dead_letter=None)
            obs[action.value] = "NO ERROR"
        except PramaError as e:
            obs[action.value] = e.code
    for action in (Action.ALERT, Action.TAG):
        try:
            Pipeline([], action=action, dead_letter=None)
            obs[action.value] = "OK"
        except PramaError as e:
            obs[action.value] = f"raised {e.code}"
    ok = obs["quarantine"] == "STREAM.NO_DEAD_LETTER" and obs["block"] == "STREAM.NO_DEAD_LETTER" and obs["alert"] == "OK" and obs["tag"] == "OK"
    log("EXE-070", "PASS" if ok else "FAIL", str(obs))

def exe071():
    order = []
    def dl(payload, reason):
        order.append("dead_letter")
        return True
    p = Pipeline([FakeAssertion("p1", violates=True)], action=Action.QUARANTINE, dead_letter=dl)
    outcome = p._judge({"a": 1})
    order.append("outcome")
    ok = order == ["dead_letter", "outcome"] and outcome.disposition == "quarantined"
    log("EXE-071", "PASS" if ok else "FAIL", f"order={order} disposition={outcome.disposition}")

def exe072():
    calls = [0]
    def dl(payload, reason):
        calls[0] += 1
        return calls[0] != 4
    p = Pipeline([FakeAssertion("p1", violates=True)], action=Action.QUARANTINE, dead_letter=dl)
    messages = [{"i": i} for i in range(10)]
    report = p.run(messages)
    ok = (len(report.outcomes) == 3 and report.halted_because != "" and report.completed is False
          and report.describe().startswith("HALTED after 3 message(s)")
          and "not examined" in report.describe())
    log("EXE-072", "PASS" if ok else "FAIL", f"n_outcomes={len(report.outcomes)} halted_because={report.halted_because!r} completed={report.completed} describe={report.describe()!r}")

def exe073():
    import inspect
    is_prama_error = issubclass(DeadLetterFull, PramaError)
    def dl(payload, reason):
        return False
    p = Pipeline([FakeAssertion("p1", violates=True)], action=Action.QUARANTINE, dead_letter=dl)
    try:
        p._judge({"a": 1})
        raised = False
    except DeadLetterFull:
        raised = True
    ok = is_prama_error and raised
    log("EXE-073", "PASS" if ok else "FAIL", f"is_PramaError_subclass={is_prama_error} raised_from__judge={raised}")

def exe074():
    p = Pipeline([FakeAssertion("p1", violates=True)], action=Action.TAG, dead_letter=None)
    outcome = p._judge("not-a-dict-at-all")
    ok = outcome.disposition == "unreadable" and outcome.was_kept is True
    log("EXE-074", "PASS" if ok else "FAIL", f"disposition={outcome.disposition} was_kept={outcome.was_kept} message={outcome.message} (nothing was actually written anywhere: dead_letter=None, _to_dead_letter returned silently -- was_kept claims True with no evidence kept)")

def exe075():
    p = Pipeline([FakeAssertion("p1", violates=True)], action=Action.ALERT)
    payload = {"a": 1}
    outcome = p._judge(payload)
    ok = (outcome.disposition == "passed" and outcome.violated == ("p1",)
          and outcome.reaches_the_consumer is True and outcome.message == payload)
    log("EXE-075", "PASS" if ok else "FAIL", f"disposition={outcome.disposition} violated={outcome.violated} reaches_consumer={outcome.reaches_the_consumer} message_unmodified={outcome.message==payload}")

def exe076():
    p = Pipeline([FakeAssertion("p1", violates=True), FakeAssertion("p2", violates=True), FakeAssertion("p3", unknown=True)],
                 action=Action.TAG, tag_field="_prama")
    payload = {"a": 1}
    outcome = p._judge(payload)
    ok = (outcome.disposition == "tagged"
          and outcome.message["_prama"]["violated"] == ["p1", "p2"]
          and outcome.message["_prama"]["unknown"] == ["p3"]
          and "_prama" not in payload
          and outcome.reaches_the_consumer is True)
    log("EXE-076", "PASS" if ok else "FAIL", f"disposition={outcome.disposition} tag={outcome.message.get('_prama')} original_mutated={'_prama' in payload}")

def exe077():
    p = Pipeline([FakeAssertion("p1", violates=True)], action=Action.TAG, tag_field="_prama")
    payload = {"a": 1, "_prama": "old-value"}
    outcome = p._judge(payload)
    ok = outcome.message["_prama"] != "old-value" and isinstance(outcome.message["_prama"], dict)
    log("EXE-077", "PASS" if ok else "FAIL", f"tag_field_overwritten={outcome.message['_prama']}")

def exe078():
    assertions = [FakeAssertion(f"p{i}", violates=(i == 17)) for i in range(40)]
    p = Pipeline(assertions, action=Action.ALERT)
    outcome = p._judge({"a": 1})
    ok = outcome.violated == ("p17",)
    log("EXE-078", "PASS" if ok else "FAIL", f"violated={outcome.violated}")

def exe079():
    p = Pipeline([NoPlanAssertion()], action=Action.ALERT)
    outcome = p._judge({"a": 1})
    ok = outcome.violated == ("",)
    log("EXE-079", "PASS" if ok else "FAIL", f"violated={outcome.violated}")

def exe080():
    assertions = [FakeAssertion(f"p{i}") for i in range(5)]
    p = Pipeline(assertions, action=Action.ALERT)
    messages = [{"i": i} for i in range(100_000)]
    report = p.run(messages)
    ok = report.throughput.p99_ms is not None and report.throughput.within(5.0) in (True, False)
    log("EXE-080", "PASS" if ok else "FAIL", f"p99_ms={report.throughput.p99_ms:.4f} within(5.0)={report.throughput.within(5.0)}")

def exe081():
    p = Pipeline([], action=Action.ALERT)
    report = p.run([])
    t = report.throughput
    ok = t.p99_ms is None and t.within(5.0) is None and t.per_second is None and t.describe() == "no messages passed through, so nothing was measured"
    log("EXE-081", "PASS" if ok else "FAIL", f"p99_ms={t.p99_ms} within={t.within(5.0)} per_second={t.per_second} describe={t.describe()!r}")

def exe082():
    obs = {}
    for n in (1, 2, 100):
        t = Throughput(messages=n, elapsed_seconds=1.0, latencies_ms=tuple(float(i) for i in range(n)))
        try:
            r0 = t.percentile(0.0)
            r99 = t.percentile(0.99)
            r100 = t.percentile(1.0)
            obs[n] = (r0, r99, r100, r100 == float(n - 1))
        except IndexError as e:
            obs[n] = f"IndexError: {e}"
    ok = all(isinstance(v, tuple) and v[3] for v in obs.values())
    log("EXE-082", "PASS" if ok else "FAIL", str(obs))

def exe083():
    order = []
    class Tracking(MemoryTransport):
        def poll(self, max_messages):
            order.append("poll")
            return super().poll(max_messages)
        def commit(self, positions):
            order.append("commit")
            return super().commit(positions)
    msgs = [StreamMessage(position=Position("t", 0, i), payload={"i": i}) for i in range(3)]
    t = Tracking(msgs)
    p = Pipeline([FakeAssertion("p1")], action=Action.ALERT)
    order.append("about_to_poll")
    runner = StreamRunner(t, p)
    orig_run = p.run
    def tracking_run(messages):
        order.append("pipeline")
        return orig_run(messages)
    p.run = tracking_run
    runner.poll_once()
    ok = order == ["about_to_poll", "poll", "pipeline", "commit"]
    log("EXE-083", "PASS" if ok else "FAIL", f"order={order}")

def exe084():
    calls = [0]
    def dl(payload, reason):
        calls[0] += 1
        return calls[0] != 4  # 4th call fails -> halt after 4 enforced (wait: 4th enforced msg dead-letters and fails)
    msgs = [StreamMessage(position=Position("t", 0, i), payload={"i": i}) for i in range(10)]
    t = MemoryTransport(msgs)
    p = Pipeline([FakeAssertion("p1", violates=True)], action=Action.QUARANTINE, dead_letter=dl)
    runner = StreamRunner(t, p)
    result = runner.poll_once()
    ok = (result.halted is True and len(result.committed) == 1
          and result.committed[0].offset == 2  # through the 3rd enforced message (0-indexed offset 2)
          and len(result.uncommitted) == 7
          and "redeliver" in result.describe())
    log("EXE-084", "PASS" if ok else "FAIL", f"halted={result.halted} committed={[p.render() for p in result.committed]} uncommitted_count={len(result.uncommitted)} describe={result.describe()!r}")

def exe085():
    msgs = ([StreamMessage(position=Position("t0", 0, i), payload={"i": i}) for i in range(1, 6)]
            + [StreamMessage(position=Position("t1", 0, i), payload={"i": i}) for i in range(10, 13)])
    t = MemoryTransport(msgs)
    p = Pipeline([FakeAssertion("p1")], action=Action.ALERT)
    runner = StreamRunner(t, p)
    result = runner.poll_once()
    rendered = [pos.render() for pos in result.committed]
    ok = len(result.committed) == 2 and "t0[0]@5" in rendered and "t1[0]@12" in rendered and rendered == sorted(rendered)
    log("EXE-085", "PASS" if ok else "FAIL", f"committed={rendered}")

def exe086():
    class FailingPoll(MemoryTransport):
        def poll(self, max_messages):
            raise RuntimeError("broker down")
    t = FailingPoll()
    p = Pipeline([], action=Action.ALERT)
    runner = StreamRunner(t, p)
    try:
        runner.poll_once()
        log("EXE-086", "FAIL", "no exception")
    except TransportError as e:
        ok = e.code == "STREAM.TRANSPORT" and "no message was lost" in (e.remedy or "") and t.commits == []
        log("EXE-086", "PASS" if ok else "FAIL", f"code={e.code} remedy={e.remedy} commits={t.commits}")

def exe087():
    class FailingCommit(MemoryTransport):
        def commit(self, positions):
            raise RuntimeError("commit rejected")
    msgs = [StreamMessage(position=Position("t", 0, i), payload={"i": i}) for i in range(3)]
    t = FailingCommit(msgs)
    p = Pipeline([FakeAssertion("p1")], action=Action.ALERT)
    runner = StreamRunner(t, p)
    try:
        runner.poll_once()
        log("EXE-087", "FAIL", "no exception")
    except TransportError as e:
        ok = "redelivered" in (e.remedy or "") and "dead-lettered" in (e.remedy or "") and "3" in str(e.context.get("messages", ""))
        log("EXE-087", "PASS" if ok else "FAIL", f"remedy={e.remedy} context={e.context}")

def exe088():
    t = MemoryTransport([])
    called = []
    p = Pipeline([], action=Action.ALERT)
    orig_run = p.run
    def tracking(messages):
        messages = list(messages)
        called.append(len(messages))
        return orig_run(messages)
    p.run = tracking
    runner = StreamRunner(t, p)
    result = runner.poll_once()
    ok = result.polled == 0 and result.committed == () and result.describe() == "nothing to read" and called == [0]
    log("EXE-088", "PASS" if ok else "FAIL", f"polled={result.polled} committed={result.committed} describe={result.describe()!r} pipeline_called_with={called}")

def exe089():
    def dl(payload, reason):
        return False  # always full
    msgs = [StreamMessage(position=Position("t", 0, i), payload={"i": i}) for i in range(1000)]
    t = MemoryTransport(msgs)
    p = Pipeline([FakeAssertion("p1", violates=True)], action=Action.QUARANTINE, dead_letter=dl)
    reports = run_until_idle(t, p)
    ok = len(reports) == 1 and reports[0].halted is True
    log("EXE-089", "PASS" if ok else "FAIL", f"n_reports={len(reports)} halted={reports[0].halted if reports else None}")

def exe090():
    class InfiniteTransport(MemoryTransport):
        def poll(self, max_messages):
            return [StreamMessage(position=Position("t", 0, i), payload={"i": i}) for i in range(max_messages)]
    t = InfiniteTransport()
    p = Pipeline([FakeAssertion("p1")], action=Action.ALERT)
    runner = StreamRunner(t, p)
    reports = runner.run_until_idle(max_batches=5)
    ok = len(reports) == 5
    log("EXE-090", "PASS" if ok else "FAIL", f"n_reports={len(reports)}")

def exe091():
    t = MemoryTransport([])
    p = Pipeline([], action=Action.ALERT)
    obs = {}
    for bs in (0, -1):
        try:
            StreamRunner(t, p, batch_size=bs)
            obs[bs] = "NO ERROR"
        except PramaError as e:
            obs[bs] = e.code
    ok = obs[0] == "STREAM.BATCH_SIZE" and obs[-1] == "STREAM.BATCH_SIZE"
    log("EXE-091", "PASS" if ok else "FAIL", str(obs))

def exe092():
    t = MemoryTransport()
    t.commit([Position("t", 0, 10)])
    t.commit([Position("t", 0, 5)])
    ok = t.committed[("t", 0)] == 10
    log("EXE-092", "PASS" if ok else "FAIL", f"committed={t.committed}")

for fn in (exe070, exe071, exe072, exe073, exe074, exe075, exe076, exe077, exe078, exe079,
           exe080, exe081, exe082, exe083, exe084, exe085, exe086, exe087, exe088, exe089,
           exe090, exe091, exe092):
    fn()
