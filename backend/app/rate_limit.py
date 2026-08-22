from slowapi import Limiter
from slowapi.util import get_remote_address

# In-memory, per-process limiter — sufficient for this app's single-instance
# deployment (no shared Redis-backed store needed). A generous global
# default guards every endpoint against automated abuse without affecting
# normal usage; auth.py applies a tighter override on register/login
# specifically, the highest-value targets for brute-force/spam.
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
