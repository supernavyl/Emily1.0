"""Emily Loop integration — adapters bridging emily-loop kernel to Emily's subsystems."""

from core.loop_integration.fleet_adapter import FleetAdapter
from core.loop_integration.tool_bridge import ToolBridgeAdapter

__all__ = ["FleetAdapter", "ToolBridgeAdapter"]
