import importlib
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "gap_importlib"
    label="x"
    def check(self, value):
        return VALID
