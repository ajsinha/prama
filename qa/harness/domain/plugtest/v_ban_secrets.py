import secrets
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "ban_secrets"
    label="x"
    def check(self, value):
        return VALID
