from importlib import import_module
from prama.classify.validators import SemanticValidator, Judgement, VALID
class ImportModuleBareValidator(SemanticValidator):
    name = "import_module_bare_scheme"
    label = "x"
    def check(self, value):
        import_module("socket")
        return VALID
