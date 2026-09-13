from datetime import datetime
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "clk2"
    label="x"
    def check(self, value):
        datetime.now()
        return VALID
