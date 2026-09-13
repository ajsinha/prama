import multiprocessing
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "gap_multiprocessing"
    label="x"
    def check(self, value):
        return VALID
