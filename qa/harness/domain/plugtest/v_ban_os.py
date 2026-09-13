import os
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "ban_os"
    label="x"
    def check(self, value):
        return VALID
