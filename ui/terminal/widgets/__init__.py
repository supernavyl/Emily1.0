"""
Custom widgets for the Emily terminal interface.
"""

from .dashboard import DashboardPanel
from .prompt import PromptWidget
from .status_bar import StatusBar

__all__ = ["PromptWidget", "StatusBar", "DashboardPanel"]
