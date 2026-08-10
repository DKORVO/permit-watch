import os


def env_int(name, default, minimum=1):
    """Read a bounded integer environment variable with a clear error."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return max(minimum, default)
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, received {raw!r}") from exc
    return max(minimum, value)
