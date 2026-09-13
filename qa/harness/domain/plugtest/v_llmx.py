import prama.llmx
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "llmx_prefix"
    label="x"
    def check(self, value):
        return VALID
