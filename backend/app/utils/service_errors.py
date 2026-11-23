class ServiceFailureError(Exception):
    """A failure on the server side, answered with a 500 and this message.

    The message is shown to the user as is, so it must never carry the underlying
    exception's text; log that before raising.
    """
