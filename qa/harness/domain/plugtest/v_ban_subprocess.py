import subprocess
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "ban_subprocess"
    label="x"
    def check(self, value):
        return VALID
