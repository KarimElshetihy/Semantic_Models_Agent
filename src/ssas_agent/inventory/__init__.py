"""Read-only inventory of model objects, keyed by stable identity."""

from ssas_agent.inventory.builder import build_inventory
from ssas_agent.inventory.records import InventoryError, InventoryItem, ModelInventory

__all__ = ["InventoryError", "InventoryItem", "ModelInventory", "build_inventory"]
