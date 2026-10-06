"""Repelnt core: the stack-independent poisoning engine.

Deliberately free of FastAPI, httpx and Ollama imports so the same logic can be
ported to Kotlin (Android) and Swift (iOS) without carrying a server with it.
"""
