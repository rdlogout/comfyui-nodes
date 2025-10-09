"""
Custom Node Installer Helper
Complete utility for installing custom nodes from Git repositories with dependency management
"""

import os
import sys
import subprocess
import json
import logging
import threading
import re
from typing import Set, Dict, Optional

# Configure logging
logger = logging.getLogger(__name__)

# Try to import pkg_resources, fallback to subprocess if not available
try:
    import pkg_resources
    HAS_PKG_RESOURCES = True
except ImportError:
    HAS_PKG_RESOURCES = False

def get_installed_packages() -> Dict[str, str]:
    """Get dictionary of currently installed packages and their versions"""
    try:
        if HAS_PKG_RESOURCES:
            return {pkg.key: pkg.version for pkg in pkg_resources.working_set}
        else:
            # Fallback: use pip list to get installed packages
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'list', '--format=json'],
                capture_output=True, text=True, check=True
            )
            packages = json.loads(result.stdout)
            return {pkg['name'].lower(): pkg['version'] for pkg in packages}
    except Exception as e:
        logger.error(f"Error getting installed packages: {e}")
        return {}

def parse_requirement_line(line: str) -> Optional[dict]:
    """Parse a requirements.txt line and extract package info"""
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    
    # Handle various formats: package, package>=1.0, package==1.0, package<1.0, etc.
    import re
    match = re.match(r'^([a-zA-Z0-9_-]+)([><=!~]+.*)?$', line)
    if match:
        return {
            'name': match.group(1).lower().replace('_', '-'),
            'original': line,
            'constraint': match.group(2) or ''
        }
    return None

def analyze_requirements(requirements_path: str, repo_name: str) -> dict:
    """Analyze requirements file and return what would be installed/skipped"""
    try:
        # Critical ComfyUI dependencies that should not be upgraded
        CRITICAL_DEPS = {
            'torch', 'torchvision', 'torchaudio', 'numpy', 'pillow', 'opencv-python',
            'opencv-contrib-python', 'transformers', 'accelerate', 'safetensors',
            'xformers', 'einops', 'diffusers', 'compel', 'tokenizers', 'huggingface-hub',
            'scipy', 'scikit-learn', 'matplotlib', 'requests', 'aiohttp', 'websockets'
        }
        
        installed_packages = get_installed_packages()
        safe_requirements = []
        skipped_packages = []
        already_installed = []
        
        with open(requirements_path, 'r') as f:
            for line in f:
                parsed = parse_requirement_line(line)
                if not parsed:
                    continue
                
                package_name = parsed['name']
                original_line = parsed['original']
                
                # Check if package is critical
                if package_name in CRITICAL_DEPS:
                    if package_name in installed_packages:
                        skipped_packages.append(f"{package_name} (installed: {installed_packages[package_name]} - protected from upgrade)")
                    else:
                        # Allow installing critical packages if not already installed
                        safe_requirements.append(original_line)
                    continue
                
                # For non-critical packages, always allow installation (including updates)
                safe_requirements.append(original_line)
        
        return {
            'safe_to_install': safe_requirements,
            'skipped_critical': skipped_packages,
            'already_installed': already_installed,
            'total_requested': len(safe_requirements) + len(skipped_packages) + len(already_installed)
        }
        
    except Exception as e:
        logger.error(f"Error analyzing requirements for {repo_name}: {e}")
        return {
            'safe_to_install': [],
            'skipped_critical': [],
            'already_installed': [],
            'total_requested': 0,
            'error': str(e)
        }

def install_requirements_threaded(pip_executable, requirements_path, repo_name):
    """Install requirements in a separate thread with dependency protection"""
    try:
        logger.info(f"Installing dependencies for {repo_name} in background...")
        
        # Critical ComfyUI dependencies that should not be upgraded
        CRITICAL_DEPS = {
            'torch', 'torchvision', 'torchaudio', 'numpy', 'pillow', 'opencv-python',
            'opencv-contrib-python', 'transformers', 'accelerate', 'safetensors',
            'xformers', 'einops', 'diffusers', 'compel', 'tokenizers', 'huggingface-hub',
            'scipy', 'scikit-learn', 'matplotlib', 'requests', 'aiohttp', 'websockets'
        }
        
        # Get currently installed packages
        installed_packages = get_installed_packages()
        
        # Read requirements file and filter out critical dependencies
        safe_requirements = []
        skipped_packages = []
        
        try:
            with open(requirements_path, 'r') as f:
                for line in f:
                    parsed = parse_requirement_line(line)
                    if not parsed:
                        continue
                    
                    package_name = parsed['name']
                    original_line = parsed['original']
                    
                    # Check if package is critical
                    if package_name in CRITICAL_DEPS:
                        if package_name in installed_packages:
                            skipped_packages.append(f"{package_name} (installed: {installed_packages[package_name]} - protected from upgrade)")
                        else:
                            # Allow installing critical packages if not already installed
                            logger.info(f"Allowing installation of critical package {package_name} (not yet installed)")
                            safe_requirements.append(original_line)
                        continue
                    
                    # For non-critical packages, allow installation even if already installed
                    safe_requirements.append(original_line)
        
        except Exception as e:
            logger.error(f"Error reading requirements file for {repo_name}: {e}")
            return
        
        if skipped_packages:
            logger.warning(f"Skipped critical packages for {repo_name}: {', '.join(skipped_packages)}")
        
        if not safe_requirements:
            logger.info(f"No new safe dependencies to install for {repo_name}")
            return
        
        logger.info(f"Installing {len(safe_requirements)} safe dependencies for {repo_name}")
        
        # Create a temporary requirements file with safe dependencies only
        temp_requirements_path = requirements_path + '.safe'
        try:
            with open(temp_requirements_path, 'w') as f:
                f.write('\n'.join(safe_requirements))
            
            # Install safe dependencies normally (without --no-deps to allow dependency resolution)
            result = subprocess.run([
                pip_executable, "install", "-r", temp_requirements_path
            ], capture_output=True, text=True, check=True)
            
            logger.info(f"Successfully installed safe dependencies for {repo_name}")
            if result.stdout:
                logger.debug(f"Install output: {result.stdout}")
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_requirements_path):
                os.remove(temp_requirements_path)
                
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install dependencies for {repo_name}: {e}")
        if e.stdout:
            logger.error(f"Stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"Stderr: {e.stderr}")
        
    except Exception as e:
        logger.error(f"Unexpected error installing dependencies for {repo_name}: {e}")

def install_custom_node(node_url):
    """
    Install a custom node from URL with automatic dependency installation
    
    Supports GitHub URLs with branches:
    - https://github.com/user/repo
    - https://github.com/user/repo/tree/branch-name
    - https://github.com/user/repo.git
    
    Args:
        node_url (str): Git repository URL for the custom node
        
    Returns:
        bool: True if folder already exists, False if newly installed, None if failed
    """
    try:
        from ..comfy_services import get_comfyui_path
        
        comfyui_path = get_comfyui_path()
        custom_nodes_path = os.path.join(comfyui_path, "custom_nodes")
        venv_path = os.path.join(comfyui_path, "venv")
        pip_executable = os.path.join(venv_path, "bin", "pip")
        
        if not os.path.isdir(custom_nodes_path):
            logger.error('Custom nodes directory not found')
            return None
        
        # Parse the URL to extract repository information
        github_info = parse_github_url(node_url)
        
        if github_info:
            # GitHub URL with branch support
            repo_name = github_info['repo']
            clone_url = github_info['clone_url']
            branch = github_info['branch']
            logger.info(f"Parsed GitHub URL: {github_info['user']}/{repo_name} (branch: {branch})")
        else:
            # Fallback to original parsing for non-GitHub URLs
            repo_name = node_url.split("/")[-1].replace(".git", "")
            clone_url = node_url
            branch = "main"  # Default branch
            logger.info(f"Using fallback parsing for non-GitHub URL: {repo_name}")
        
        repo_path = os.path.join(custom_nodes_path, repo_name)
        
        # Check if folder already exists
        if os.path.isdir(repo_path):
            logger.info(f"Custom node {repo_name} already exists")
            
            # Check if requirements.txt exists and install missing dependencies in background
            requirements_path = os.path.join(repo_path, "requirements.txt")
            if os.path.isfile(requirements_path):
                # Analyze requirements first
                analysis = analyze_requirements(requirements_path, repo_name)
                
                if analysis['safe_to_install']:
                    # Start pip install in a separate thread
                    thread = threading.Thread(
                        target=install_requirements_threaded,
                        args=(pip_executable, requirements_path, repo_name),
                        daemon=True
                    )
                    thread.start()
                    logger.info(f"Installing {len(analysis['safe_to_install'])} safe dependencies for existing node {repo_name} in background")
            
            return True
        
        # Clone the repository with branch support
        logger.info(f"Cloning custom node from {clone_url} (branch: {branch})")
        
        if branch and branch != "main":
            # Clone specific branch
            subprocess.run([
                "git", "clone", "--branch", branch, "--single-branch", 
                clone_url, repo_path
            ], check=True)
            logger.info(f"Custom node {repo_name} (branch: {branch}) installed successfully")
        else:
            # Clone default branch
            subprocess.run(["git", "clone", clone_url, repo_path], check=True)
            logger.info(f"Custom node {repo_name} installed successfully")
        
        # Check if requirements.txt exists and install dependencies in background
        requirements_path = os.path.join(repo_path, "requirements.txt")
        if os.path.isfile(requirements_path):
            # Analyze requirements first
            analysis = analyze_requirements(requirements_path, repo_name)
            
            if analysis['safe_to_install']:
                # Start pip install in a separate thread for faster response
                thread = threading.Thread(
                    target=install_requirements_threaded,
                    args=(pip_executable, requirements_path, repo_name),
                    daemon=True
                )
                thread.start()
                logger.info(f"Installing {len(analysis['safe_to_install'])} safe dependencies for new node {repo_name} in background")
        
        return False  # Newly installed
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install custom node {node_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error installing custom node {node_url}: {e}")
        return None


def parse_github_url(url: str) -> Optional[dict]:
    """
    Parse GitHub URL to extract repository information and branch.
    
    Supports formats:
    - https://github.com/user/repo
    - https://github.com/user/repo.git
    - https://github.com/user/repo/tree/branch-name
    - https://github.com/user/repo/tree/branch-name/subfolder
    
    Args:
        url: GitHub URL to parse
        
    Returns:
        dict with 'user', 'repo', 'branch', 'subfolder', 'clone_url' or None if not a GitHub URL
    """
    try:
        # Remove trailing slashes and .git extension
        url = url.rstrip('/')
        
        # Pattern for GitHub URLs with optional branch/tree
        github_pattern = r'https?://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+)(?:/(.*))?)?(?:\.git)?$'
        
        match = re.match(github_pattern, url)
        if not match:
            return None
        
        user = match.group(1)
        repo = match.group(2)
        branch = match.group(3) if match.group(3) else 'main'  # Default to main branch
        subfolder = match.group(4) if match.group(4) else None
        
        # Create clean clone URL
        clone_url = f"https://github.com/{user}/{repo}.git"
        
        return {
            'user': user,
            'repo': repo,
            'branch': branch,
            'subfolder': subfolder,
            'clone_url': clone_url,
            'original_url': url
        }
        
    except Exception as e:
        logger.error(f"Error parsing GitHub URL {url}: {e}")
        return None