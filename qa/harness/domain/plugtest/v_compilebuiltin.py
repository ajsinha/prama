from prama.classify.validators import SemanticValidator, Judgement, VALID
class CompileBuiltinValidator(SemanticValidator):
    name = "compile_builtin_scheme"
    label = "x"
    def check(self, value):
        code = compile("1+1", "<x>", "eval")
        return VALID
