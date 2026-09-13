import time
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "clk6"
    label="x"
    def check(self, value):
        time.time_ns()
        return VALID
