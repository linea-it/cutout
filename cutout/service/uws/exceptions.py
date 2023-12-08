from rest_framework.exceptions import APIException, PermissionDenied


class UWSError(APIException):
    """An error with an associated error code.

    SODA requires errors be in ``text/plain`` and start with an error code.
    Adopt that as a general representation of errors produced by the UWS
    layer to simplify generating error responses.
    """

    status_code = 400


class PermissionDeniedError(PermissionDenied):
    """User does not have access to this resource."""

    status_code = 403


class UsageError(APIException):
    """Invalid parameters were passed to a UWS API."""

    status_code = 422


class InvalidPhaseError(UsageError):
    """The job is in an invalid phase for the desired operation."""


class MultiValuedParameterError(UWSError):
    """Multiple values not allowed for this parameter."""

    status_code = 422


class ParameterError(UsageError):
    """Unsupported value passed to a parameter."""
