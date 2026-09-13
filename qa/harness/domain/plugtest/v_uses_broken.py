import v_syntax_error_helper
from prama.classify.validators import SemanticValidator, VALID
class V(SemanticValidator):
    name='brk'
    label='x'
    def check(self,value):
        return VALID
