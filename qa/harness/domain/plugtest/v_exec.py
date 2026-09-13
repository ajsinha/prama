from prama.classify.validators import SemanticValidator, Judgement, VALID
class ExecValidator(SemanticValidator):
    name = "exec_scheme"
    label = "x"
    def check(self, value):
        exec("x=1")
        return VALID
