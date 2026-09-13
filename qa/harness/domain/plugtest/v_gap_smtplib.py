import smtplib
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "gap_smtplib"
    label="x"
    def check(self, value):
        return VALID
