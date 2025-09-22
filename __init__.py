import os
import sys
import threading
import time

# sys.path.append(os.path.join(os.path.dirname(__file__)))

from . import custom_routes
from .connect_host import init_tunnel
from .comfy_services import start_comfy_services

def delayed_start_services():
    """Start services after a delay to ensure ComfyUI is ready"""
    time.sleep(5)  # Wait 5 seconds for ComfyUI to fully initialize
    start_comfy_services()

init_tunnel()
custom_routes.register()

# Start comfy services in background after delay
service_thread = threading.Thread(target=delayed_start_services, daemon=True)
service_thread.start()

# __all__= []