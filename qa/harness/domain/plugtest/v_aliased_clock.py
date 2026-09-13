from time import time as ticks
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "aliasedclk"
    label="x"
    def check(self, value):
        ticks()
        return VALID
