class PortaError(Exception):
    """Base application error."""


class AuthenticationError(PortaError):
    """Raised when user authentication fails."""


class AuthorizationError(PortaError):
    """Raised when the actor lacks permission."""


class DependencyMissingError(PortaError):
    """Raised when required system dependency is unavailable."""


class CredentialDecryptionError(PortaError):
    """Raised when a credential cannot be decrypted."""


class ResourceConflictError(PortaError):
    """Raised when the target resource conflicts with existing state."""


class ValidationError(PortaError):
    """Raised for domain validation problems."""
