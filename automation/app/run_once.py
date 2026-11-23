"""Single publishing run; the container's default command."""
from .publisher import publish_once

if __name__ == "__main__":
    publish_once()
