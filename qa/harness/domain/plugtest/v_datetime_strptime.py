from datetime import datetime
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "dtfmt"
    label="x"
    screen_pattern = r"^\d{4}-\d{2}-\d{2}$"
    def check(self, value):
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return VALID
        except ValueError:
            return Judgement(valid=False, reason="bad date")
