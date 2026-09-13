import re
from prama.classify.validators import SemanticValidator, Judgement, VALID
_PAT = re.compile(r'^[0-9]+$')
class RecompileValidator(SemanticValidator):
    name = "recompile_scheme"
    label = "recompile"
    def check(self, value):
        return VALID if _PAT.match(value) else Judgement(valid=False, reason="no")
