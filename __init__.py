import os
import sys

# sys.path.append(os.path.join(os.path.dirname(__file__)))

from . import custom_routes
from .connect_host import init_tunnel
from .comfy_services import start_comfy_services

init_tunnel()
custom_routes.register()
start_comfy_services()
# __all__= []