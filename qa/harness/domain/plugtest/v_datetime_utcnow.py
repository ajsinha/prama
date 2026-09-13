from datetime import datetime
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "clk3"
    label="x"
    def check(self, value):
        datetime.utcnow()
        return VALID
