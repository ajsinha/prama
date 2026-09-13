import urllib.request
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "ban_urllib_request"
    label="x"
    def check(self, value):
        return VALID
