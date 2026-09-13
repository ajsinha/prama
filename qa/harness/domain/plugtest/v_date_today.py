from datetime import date
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "clk7"
    label="x"
    def check(self, value):
        date.today()
        return VALID
