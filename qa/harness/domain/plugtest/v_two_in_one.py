
from prama.classify.validators import SemanticValidator, VALID, Judgement
class A(SemanticValidator):
    name = 'twoinone_a'
    label = 'x'
    def check(self, value):
        return Judgement(valid=False, reason='changed')
class B(SemanticValidator):
    name = 'twoinone_b'
    label = 'x'
    def check(self, value):
        return VALID
