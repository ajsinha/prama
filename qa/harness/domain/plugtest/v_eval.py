from prama.classify.validators import SemanticValidator, Judgement, VALID
class EvalValidator(SemanticValidator):
    name = "eval_scheme"
    label = "x"
    def check(self, value):
        eval("1+1")
        return VALID
