def __getattr__(name: str):
    if name == "CAPEChatAgent":
        from .agent import CAPEChatAgent

        return CAPEChatAgent
    raise AttributeError(name)


__all__ = ["CAPEChatAgent"]
