class LlmError(RuntimeError):
    """A model call failed; the message is safe to show the user."""


class SignInRequiredError(LlmError):
    def __init__(self, message: str = "Sign in with ChatGPT again in Progress → Text generation.") -> None:
        super().__init__(message)


class PlanLimitError(LlmError):
    def __init__(self, message: str = "Your ChatGPT plan's usage limit is reached for now. Try again later.") -> None:
        super().__init__(message)


class NoModelError(LlmError):
    def __init__(self) -> None:
        super().__init__("No model is connected. Sign in with ChatGPT in Progress → Text generation.")


class DailyCapError(LlmError):
    def __init__(self, cap: int) -> None:
        super().__init__(f"Daily model-call cap reached ({cap}). Raise BHASHA_LLM_MAX_CALLS_PER_DAY to allow more.")
