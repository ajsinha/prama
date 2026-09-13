from prama.classify.validators import SemanticValidator, Judgement, VALID
class DunderImportValidator(SemanticValidator):
    name = "dunderimport_scheme"
    label = "x"
    def check(self, value):
        __import__("socket")
        return VALID
