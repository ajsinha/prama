import importlib
from prama.classify.validators import SemanticValidator, Judgement, VALID
class ImportlibAttrValidator(SemanticValidator):
    name = "importlib_attr_scheme"
    label = "x"
    def check(self, value):
        importlib.import_module("socket")
        return VALID
