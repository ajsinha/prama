import time
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "clk5"
    label="x"
    def check(self, value):
        time.perf_counter()
        return VALID
