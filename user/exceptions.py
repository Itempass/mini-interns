class InsufficientBalanceError(Exception):
    """Raised when a user's balance is insufficient to perform an operation."""
    def __init__(self, message="Your balance is depleted. Please contact an administrator."):
        self.message = message
        super().__init__(self.message) 