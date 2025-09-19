"""
@author: BennyKok
@title: comfyui-deploy
@nickname: Comfy Deploy
@description:
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__)))

import inspect
import importlib
from .utils import get_python_files, append_to_sys_path, split_camel_case
from . import custom_routes
from .connect_host import init_tunnel

ag_path = os.path.join(os.path.dirname(__file__))

init_tunnel()

paths = ["comfy-nodes"]
files = []

for path in paths:
    full_path = os.path.join(ag_path, path)
    append_to_sys_path(full_path)
    files.extend(get_python_files(full_path))

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}



# Import all the modules and append their mappings
for file in files:
    module = importlib.import_module(file)

    # Check if the module has explicit mappings
    if hasattr(module, "NODE_CLASS_MAPPINGS"):
        NODE_CLASS_MAPPINGS.update(module.NODE_CLASS_MAPPINGS)
    if hasattr(module, "NODE_DISPLAY_NAME_MAPPINGS"):
        NODE_DISPLAY_NAME_MAPPINGS.update(module.NODE_DISPLAY_NAME_MAPPINGS)

    # Auto-discover classes with ComfyUI node attributes
    for name, obj in inspect.getmembers(module):
        # Check if it's a class and has the required ComfyUI node attributes
        if (
            inspect.isclass(obj)
            and hasattr(obj, "INPUT_TYPES")
            and hasattr(obj, "RETURN_TYPES")
        ):
            # Use the class name as the key if not already in mappings
            if name not in NODE_CLASS_MAPPINGS:
                NODE_CLASS_MAPPINGS[name] = obj
                # Create a display name by converting camelCase to Title Case with spaces
                words = split_camel_case(name.replace("ComfyUIDeploy", ""))
                display_name = " ".join(word.capitalize() for word in words)
                # print(display_name, name)
                NODE_DISPLAY_NAME_MAPPINGS[name] = display_name

WEB_DIRECTORY = "web-plugin"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
