import io
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "gap_io"
    label="x"
    def check(self, value):
        return VALID
