from prama.classify.validators import SemanticValidator, VALID
class V(SemanticValidator):
    name = 'raisesempty'
    label = 'x'
    def check(self, value):
        return VALID if value[9999] else VALID
