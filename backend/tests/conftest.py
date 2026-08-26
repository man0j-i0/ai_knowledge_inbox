"""app.config builds Settings at import time and requires an API key, so give
it a dummy one before any test module imports the app. Nothing under tests/
makes a network call: the chunker and similarity are pure functions."""
import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-never-used")
