"""Common contract for cloud certificate targets.

Design decisions this file encodes (see docs/design-review-multicloud-2026-08-14.md):

- D5: failure policy is per target, not global. `policy: required` (the default)
  fails the run; `policy: advisory` is logged and reported but non-fatal. The
  previous global OTC_ELB_BEST_EFFORT flag downgraded every target at once.
- D6: deploy() imports and binds, and never deletes. Removing a superseded
  certificate is a separate, explicitly-gated operation so that a failure
  always leaves the previous working certificate bound.
- D2/D3: no provider implementation here carries a delete permission.
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

REQUIRED = "required"
ADVISORY = "advisory"
VALID_POLICIES = (REQUIRED, ADVISORY)


@dataclass
class DeployResult:
    """Outcome of one certificate deployment to one cloud target."""

    server: str
    success: bool
    message: str = ""
    policy: str = REQUIRED
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def advisory(self) -> bool:
        """True when a failure here must not fail the run."""
        return self.policy == ADVISORY

    @property
    def fatal(self) -> bool:
        """True when this result should fail the domain."""
        return not self.success and not self.advisory

    def to_dict(self) -> Dict[str, Any]:
        # Mirrors the shape main.py already consumes for SSH and OTC results.
        return {
            "server": self.server,
            "success": self.success,
            "message": self.message,
            "advisory": self.advisory,
            **({"details": self.details} if self.details else {}),
        }


class CertificateTarget(abc.ABC):
    """A cloud endpoint that can be given a certificate and bound to it.

    Implementations must not expose deletion. Credentials are resolved by each
    provider's own credential chain (D1) so that CI can federate short-lived
    credentials instead of storing a long-lived secret.
    """

    #: short provider key used in config, e.g. "aws"
    provider: str = ""

    def __init__(self, name: str, policy: str = REQUIRED, **_: Any) -> None:
        if policy not in VALID_POLICIES:
            raise ValueError(
                f"{name}: policy must be one of {VALID_POLICIES}, got {policy!r}"
            )
        self.name = name
        self.policy = policy

    @abc.abstractmethod
    def deploy(self, cert_name: str, cert_pem: str, key_pem: str, chain_pem: Optional[str] = None) -> DeployResult:
        """Import the certificate and bind it to this target.

        Must not raise for an expected provider failure — return a DeployResult
        with success=False so the per-target policy decides whether the run fails.
        """

    def _ok(self, message: str, **details: Any) -> DeployResult:
        log.info("%s: %s", self.name, message)
        return DeployResult(self.name, True, message, self.policy, details)

    def _fail(self, message: str, **details: Any) -> DeployResult:
        suffix = " [advisory, non-fatal]" if self.policy == ADVISORY else ""
        log.error("%s: %s%s", self.name, message, suffix)
        return DeployResult(self.name, False, message, self.policy, details)
