class ProviderError(Exception):
    """Privacy-safe provider failure base."""


class ProviderUnavailable(ProviderError):
    pass


class ProviderTimeout(ProviderError):
    pass


class ProviderOutputInvalid(ProviderError):
    pass
