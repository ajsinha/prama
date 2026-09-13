import socket
from prama.classify.validators import SemanticValidator, VALID
class V(SemanticValidator):
    name='badimp'
    label='x'
    def check(self,v): return VALID
