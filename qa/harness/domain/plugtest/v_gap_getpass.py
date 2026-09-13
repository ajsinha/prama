import getpass
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "gap_getpass"
    label="x"
    def check(self, value):
        return VALID
