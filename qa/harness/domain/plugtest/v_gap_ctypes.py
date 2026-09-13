import ctypes
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "gap_ctypes"
    label="x"
    def check(self, value):
        return VALID
