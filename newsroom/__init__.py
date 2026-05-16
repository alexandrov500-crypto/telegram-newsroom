"""Thin CLI namespace for operator commands (production-lite)."""

from newsroom._version import RELEASE_STATUS, VERSION

__version__ = VERSION
__release_status__ = RELEASE_STATUS

__all__ = ["VERSION", "RELEASE_STATUS", "__version__", "__release_status__"]
