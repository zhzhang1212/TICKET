# 模块C：订单生命周期与状态机 (FSM)

class OrderStateMachine:
    """
    处理订单生命周期状态流转，避免“幽灵支付”
    包含 待支付/确认 -> 已确认 -> 已取消 -> 已爽约
    """
    def __init__(self, current_state="待确认"):
        self.state = current_state

    def trigger(self, event_name: str, context: dict):
        """执行流转和延迟MQ对接"""
        pass
