import requests
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "ban_requests"
    label="x"
    def check(self, value):
        return VALID
