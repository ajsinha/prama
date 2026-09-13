import pathlib
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "ban_pathlib"
    label="x"
    def check(self, value):
        return VALID
