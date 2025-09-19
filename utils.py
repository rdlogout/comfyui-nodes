import os
import sys
import re

def get_python_files(path):
    return [f[:-3] for f in os.listdir(path) if f.endswith(".py")]


def append_to_sys_path(path):
    if path not in sys.path:
        sys.path.append(path)

def split_camel_case(name):
    # Split on underscores first, then split each part on camelCase
    parts = []
    for part in name.split("_"):
        # Find all camelCase boundaries
        words = re.findall("[A-Z][^A-Z]*", part)
        if not words:  # If no camelCase found, use the whole part
            words = [part]
        parts.extend(words)
    return parts