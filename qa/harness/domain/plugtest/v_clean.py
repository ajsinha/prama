import re
from prama.classify.validators import SemanticValidator, Judgement, VALID
class CleanValidator(SemanticValidator):
    name = "clean_scheme"
    label = "clean"
    def check(self, value):
        return VALID if re.match(r'^[0-9]+$', value) else Judgement(valid=False, reason="not numeric")
