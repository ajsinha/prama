import sqlite3
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = "gap_sqlite3"
    label="x"
    def check(self, value):
        return VALID
