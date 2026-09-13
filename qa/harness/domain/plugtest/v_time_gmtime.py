import time
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "clk1"
    label="x"
    def check(self, value):
        time.gmtime()
        return VALID
