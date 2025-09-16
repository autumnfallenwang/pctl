"""
Core exceptions for pctl
"""

class PctlError(Exception):
    """Base exception for pctl"""
    pass

class ConfigError(PctlError):
    """Configuration related errors"""
    pass

class ServiceError(PctlError):
    """Service layer errors"""
    pass


class JourneyError(ServiceError):
    """Journey service errors"""
    pass

class ELKError(ServiceError):
    """ELK service errors"""
    pass


class PAICError(ServiceError):
    """PAIC service errors"""
    pass


class ConnectionError(PAICError):
    """PAIC connection profile errors"""
    pass


class AuthenticationError(PAICError):
    """PAIC authentication errors"""
    pass