import ftplib
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "gap_ftplib"
    label="x"
    def check(self, value):
        return VALID
