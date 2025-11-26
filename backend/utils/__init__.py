"""
Utility module for common functionality.

Handles AWS credential management and configuration.
"""

from .aws_credentials import get_credentials_for_opensearch, get_stage

__all__ = [
    "get_credentials_for_opensearch",
    "get_stage",
]
