import ssl
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "gap_ssl"
    label="x"
    def check(self, value):
        return VALID
