"""Bounded conversation history, independent of the radio transport."""

import copy
import time
import uuid


class MessageHistory:
    def __init__(self, data=None, changed=lambda: None):
        self.data = data or {"messages": [], "favorites": []}
        for message in self.data["messages"]:
            if message.get("status") == "sending":
                message["status"] = "unconfirmed"
        self.changed = changed

    def append(self, message):
        item = {"id": uuid.uuid4().hex, "received_at": time.time(), **message}
        # The companion may replay queued incoming messages after reconnecting.
        if item.get("direction") == "in" and item.get("sender_timestamp"):
            keys = ("conversation", "sender", "sender_timestamp", "text", "direction")
            if any(all(old.get(k) == item.get(k) for k in keys)
                   for old in self.data["messages"][-200:]):
                return None
        self.data["messages"].append(item)
        self.data["messages"] = self.data["messages"][-1000:]
        self.changed()
        return item["id"]

    def update(self, message_id, **fields):
        for message in self.data["messages"]:
            if message["id"] == message_id:
                message.update(fields)
                self.changed()
                break

    def snapshot(self):
        return copy.deepcopy(self.data)

    def favorite(self, target, enabled):
        favorites = set(self.data.get("favorites", []))
        favorites.add(target) if enabled else favorites.discard(target)
        self.data["favorites"] = sorted(favorites)
        self.changed()
