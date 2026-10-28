class MatchingCoreError(Exception):
    """Base for this package's own errors — never a framework exception
    (no HTTPException here; the backend adapter translates these)."""


class CallerNotFoundError(MatchingCoreError):
    def __init__(self, caller_id: object) -> None:
        self.caller_id = caller_id
        super().__init__(f"Caller not found: {caller_id!r}")


class LocationRequiredError(MatchingCoreError):
    def __init__(self, caller_id: object) -> None:
        self.caller_id = caller_id
        super().__init__(f"Caller has no location set: {caller_id!r}")
