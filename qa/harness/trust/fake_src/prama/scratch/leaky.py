"""A scratch module that posts to an HTTP endpoint without being registered as an egress point."""
import httpx

def send(payload):
    return httpx.post("https://example.com/collect", json=payload)
