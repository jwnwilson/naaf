import os
import sys

# Add src directories to path for pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "projects/server/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "libs/crud_router/src"))
