import openai
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "model_openai"
    label="x"
    def check(self, value):
        return VALID
