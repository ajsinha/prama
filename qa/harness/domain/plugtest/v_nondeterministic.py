
_counter = [0]
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = 'nondet'
    label = 'x'
    def check(self, value):
        _counter[0] += 1
        return VALID if _counter[0] % 2 == 0 else Judgement(valid=False, reason='odd')
