from __future__ import annotations


def called_positionally(method):
    """
    Marks *method*, returning it unchanged.
    """
    return method


def on_message(message: str) -> None:
    print(message)
