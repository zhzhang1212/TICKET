# 模块C：动态规则引擎 (责任链模式的基础骨架)

class InternalRuleHandler:
    """抽象规则处理类"""
    def __init__(self):
        self._next_handler = None

    def set_next(self, handler):
        self._next_handler = handler
        return handler

    def handle(self, context: dict):
        if self._next_handler:
            return self._next_handler.handle(context)
        return True, "通关"
