import a
from prama.classify.validators import SemanticValidator, VALID
class V(SemanticValidator):
    name='cyc'
    label='x'
    def check(self,value):
        return VALID
