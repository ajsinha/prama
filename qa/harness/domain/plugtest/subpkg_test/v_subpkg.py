from .helpers.impure import check as _c
from prama.classify.validators import SemanticValidator, VALID
class V(SemanticValidator):
    name='subpkg'
    label='x'
    def check(self,value):
        return VALID
