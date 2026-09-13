import helpers
from prama.classify.validators import SemanticValidator, VALID
class V(SemanticValidator):
    name='sib'
    label='x'
    def check(self,value):
        return VALID
