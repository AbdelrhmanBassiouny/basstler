from helpers import old_name


def caller() -> int:
    """
    Return what :func:`old_name` returns.
    """
    # old_name never fails.
    return old_name()
