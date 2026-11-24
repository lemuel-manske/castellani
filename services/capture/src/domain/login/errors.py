class DuplicateSessionRequest(ValueError):
    pass


class SessionNotFound(KeyError):
    pass


class SessionConflict(ValueError):
    pass


class LoginUnavailable(RuntimeError):
    pass
