import httpx
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "ban_httpx"
    label="x"
    def check(self, value):
        return VALID
