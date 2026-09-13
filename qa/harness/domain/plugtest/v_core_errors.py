import prama.core.errors
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "core_errors_ok"
    label="x"
    def check(self, value):
        return VALID
