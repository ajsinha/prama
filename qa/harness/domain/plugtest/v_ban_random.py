import random
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "ban_random"
    label="x"
    def check(self, value):
        return VALID
