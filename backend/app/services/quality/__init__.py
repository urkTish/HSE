"""Phase 8 Quality services (spec 8-quality). Q0 owns the shared services in this package; each
wave-2 part owns `q<n>/` and plugs into `registry` from its `register()` (§3.2)."""

_registered = False


def ensure_registered() -> None:
    """Register Q0's providers and call every part's `register()` once (idempotent)."""
    global _registered  # noqa: PLW0603
    if _registered:
        return
    _registered = True
    from app.services.quality import q0_register, q1, q2, q3, q4  # noqa: PLC0415

    q0_register.register()
    for part in (q1, q2, q3, q4):
        part.register()
