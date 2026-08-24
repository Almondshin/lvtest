class LvtestError(Exception):
    """CLI가 JSON으로 변환해 출력하는 도메인 에러."""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, **self.extra}}
