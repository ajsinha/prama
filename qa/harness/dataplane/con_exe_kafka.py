import sys
sys.path.insert(0, ".")
from qa_common import log
from prama.execute.kafka import KafkaTransport, _text
from prama.execute.transport import TransportError
from prama.core.errors import PramaError

BASE = dict(bootstrap_servers="127.0.0.1:1", group_id="g", topics=["t"])

def exe093():
    obs = {}
    for val in (True, "true", "1", "false", None):
        cfg = {} if val is None else {"enable.auto.commit": val}
        try:
            t = KafkaTransport(**BASE, config=cfg)
            obs[str(val)] = ("OK", t._consumer.poll is not None)
            t.close()
        except PramaError as e:
            obs[str(val)] = (e.code, None)
    ok = (obs["True"][0] == "STREAM.AUTO_COMMIT" and obs["true"][0] == "STREAM.AUTO_COMMIT"
          and obs["1"][0] == "STREAM.AUTO_COMMIT" and obs["false"][0] == "OK" and obs["None"][0] == "OK")
    log("EXE-093", "PASS" if ok else "FAIL", str(obs))

class FakeRecord:
    def __init__(self, value, key=None, headers=None, topic="t", partition=0, offset=0, error=None):
        self._value = value
        self._key = key
        self._headers = headers or []
        self._topic = topic
        self._partition = partition
        self._offset = offset
        self._error = error
    def value(self): return self._value
    def key(self): return self._key
    def headers(self): return self._headers
    def topic(self): return self._topic
    def partition(self): return self._partition
    def offset(self): return self._offset
    def error(self): return self._error

def exe096():
    t = KafkaTransport(**BASE)
    record = FakeRecord(value=b"not json {{{")
    msg = t._message(record)
    ok_wrapped_as_unreadable = msg.payload.get("_unreadable") is True
    from prama.execute.inflight import Pipeline
    from prama.execute.actions import Action
    class FakeAssertion:
        def judge(self, message):
            class V:
                is_violation = False
                unknown = False
            return V()
    p = Pipeline([FakeAssertion()], action=Action.ALERT)
    outcome = p._judge(msg.payload)
    log("EXE-096", "FAIL" if outcome.disposition == "passed" else "PASS",
        f"_message() wraps as {msg.payload}; isinstance(payload, dict)={isinstance(msg.payload, dict)}; "
        f"Pipeline._judge() on this wrapped payload -> disposition={outcome.disposition} (confirmed: "
        f"the unreadable-body note passes the isinstance(payload, dict) check in _judge, so it is "
        f"evaluated as an ordinary message against every assertion rather than being dead-lettered "
        f"as unreadable -- here it 'passed' because the fake assertion never fires, but a real "
        f"assertion checking some expected field would find it absent from {{'_unreadable':True,...}} "
        f"and could flag it as a content violation instead of what it actually is: an undeserialisable "
        f"message)")
    t.close()

def exe097():
    t = KafkaTransport(**BASE)
    obs = {}
    for label, body in (
        ("array", b"[1,2,3]"),
        ("text", b'"text"'),
        ("number", b"42"),
        ("null", b"null"),
        ("empty", b""),
    ):
        record = FakeRecord(value=body)
        msg = t._message(record)
        obs[label] = msg.payload
    ok = (obs["array"] == {"_raw": [1, 2, 3]} and obs["text"] == {"_raw": "text"}
          and obs["number"] == {"_raw": 42} and obs["null"] == {"_raw": None} and obs["empty"] == {})
    log("EXE-097", "PASS" if ok else "FAIL", str(obs))
    t.close()

def exe098():
    t = KafkaTransport(**BASE)
    bad_utf8 = b"\xff\xfe\x80invalid"
    record = FakeRecord(value=b"{}", key=bad_utf8, headers=[("h1", bad_utf8)])
    msg = t._message(record)
    ok_key = "�" in msg.key or msg.key != ""
    record_none_key = FakeRecord(value=b"{}", key=None)
    msg2 = t._message(record_none_key)
    ok = ok_key and msg2.key == ""
    log("EXE-098", "PASS" if ok else "FAIL", f"bad_utf8_key={msg.key!r} header={msg.headers.get('h1')!r} none_key={msg2.key!r}")
    t.close()

def exe099():
    t = KafkaTransport(**BASE)
    calls = []
    class FakeConsumer:
        def close(self):
            calls.append(1)
    t._consumer = FakeConsumer()  # swap in a plain Python double; cimpl.Consumer's methods are read-only
    t.close()
    t.close()
    ok = len(calls) == 1
    log("EXE-099", "PASS" if ok else "FAIL", f"underlying consumer.close() called {len(calls)} time(s) across two KafkaTransport.close() calls")

def exe094_095():
    log("EXE-094", "BLOCKED", "needs a live Kafka broker (offset+1 commit semantics can only be "
        "verified against a real broker's actual redelivery behaviour on reconnect with the same "
        "group id -- a fake consumer would only test our own mock, not confluent_kafka/the broker's "
        "real semantics). Per the hard constraint, a real Kafka broker is explicitly blocked unless "
        "the repo ships a fake; none does (tests/execute/test_kafka.py is itself a live-broker test, "
        "skipped without PRAMA_TEST_KAFKA_BOOTSTRAP).")
    log("EXE-095", "BLOCKED", "needs a live Kafka broker to produce a record genuinely carrying a "
        "broker-level error through confluent_kafka's real poll() path; the pure error-handling logic "
        "in KafkaTransport.poll() is trivial to reach with a stubbed consumer.poll(), but doing so "
        "would only prove the stub behaves as configured, not exercise a real broker error -- and a "
        "real Kafka broker is explicitly blocked per the hard constraint.")

exe093()
exe096()
exe097()
exe098()
exe099()
exe094_095()
