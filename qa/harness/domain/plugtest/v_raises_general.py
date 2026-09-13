from prama.classify.validators import SemanticValidator, VALID
class V(SemanticValidator):
    name = 'raisesgeneral'
    label = 'x'
    def check(self, value):
        return VALID if value[9999] else VALID
