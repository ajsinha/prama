import os.path
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "ban_os_path"
    label="x"
    def check(self, value):
        return VALID
