import prama.llm
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "model_prama_llm"
    label="x"
    def check(self, value):
        return VALID
