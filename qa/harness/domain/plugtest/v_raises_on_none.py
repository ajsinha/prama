from prama.classify.validators import SemanticValidator, VALID
class V(SemanticValidator):
    name = 'raisesnone'
    label = 'x'
    def check(self, value):
        return VALID
    def judge(self, value):
        return VALID if len(value) >= 0 else VALID
