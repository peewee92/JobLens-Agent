"""Stable application errors for resume-document input."""


class ResumeDocumentError(ValueError):
    """Base class for expected resume-document failures."""


class ResumeDocumentTooLargeError(ResumeDocumentError):
    pass


class UnsupportedResumeDocumentError(ResumeDocumentError):
    pass


class InvalidResumeDocumentError(ResumeDocumentError):
    pass


class ResumeTextNotExtractableError(ResumeDocumentError):
    pass
