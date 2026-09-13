import platform
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "gap_platform"
    label="x"
    def check(self, value):
        return VALID
