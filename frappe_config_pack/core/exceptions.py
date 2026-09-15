"""Domain exceptions. Callers can show these messages without a traceback."""


class ConfigPackError(Exception):
    """Base exception for all package-engine failures."""


class ManifestValidationError(ConfigPackError):
    """Raised when a manifest does not satisfy the package schema."""


class InvalidPackageError(ConfigPackError):
    """Raised when an archive or packaged resource is unsafe or malformed."""


class UnsupportedFormatError(InvalidPackageError):
    """Raised when an archive uses a package format we do not support."""


class ChecksumMismatchError(InvalidPackageError):
    """Raised when an archive's asserted checksums do not match its content."""


class ResourceValidationError(ConfigPackError):
    """Raised when a handler cannot validate a resource payload."""


class UnknownResourceTypeError(ResourceValidationError):
    """Raised when a package mentions a resource without a registered handler."""


class DeploymentBlockedError(ConfigPackError):
    """Raised when a package plan has unresolved safety blockers."""


class StalePreviewError(ConfigPackError):
    """Raised when target configuration changed after a user reviewed the diff."""


class SnapshotError(ConfigPackError):
    """Raised when a deployment restore point cannot be safely created or read."""


class RollbackError(ConfigPackError):
    """Raised when a saved restore point cannot be safely applied."""


class DuplicateResourceError(InvalidPackageError):
    """Raised when a package contains the same resource identity twice."""
