import asyncio
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "gap_asyncio"
    label="x"
    def check(self, value):
        return VALID
