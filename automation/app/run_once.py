"""Make today's draft once (the `publish` service). It does not publish: use the admin screen."""
from .drafts import create_today

if __name__ == "__main__":
    create_today()
