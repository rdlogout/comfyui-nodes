import os
import sys
import subprocess
import json
import logging
import threading
from typing import Set, Dict, Optional
from aiohttp import web
from server import PromptServer
from .helper.request_function import get_data, post_data

# Try to import pkg_resources, fallback to subprocess if not available
try:
    import pkg_resources
    HAS_PKG_RESOURCES = True
except ImportError:
    HAS_PKG_RESOURCES = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def install_requirements_threaded(pip_executable, requirements_path, repo_name, node_id):
    """Install requirements in a separate thread for existing nodes with dependency protection"""
    try:
        logger.info(f"Installing dependencies for existing node {repo_name} in background...")
        
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
                            # This ensures new nodes get their required dependencies
                            logger.info(f"Allowing installation of critical package {package_name} (not yet installed)")
                            safe_requirements.append(original_line)
                        continue
                    
                    # For non-critical packages, allow installation even if already installed
                    # This allows for updates of safe dependencies
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

def register_custom_nodes_routes():
    @PromptServer.instance.routes.get('/api/sync-nodes')
    @PromptServer.instance.routes.post('/api/sync-nodes')
    async def install_custom_nodes(request):
        try:
            # Fetch custom nodes data from API
            logger.info("Fetching custom nodes from API...")
            nodes_data = get_data('api/machines/custom_nodes')
            
            if not nodes_data or not isinstance(nodes_data, list):
                return web.json_response({
                    'success': False, 
                    'error': 'Failed to fetch custom nodes data from API'
                }, status=500)

            # Get ComfyUI paths
            home_path = os.path.expanduser("~")
            comfyui_path = os.path.join(home_path, "ComfyUI")
            custom_nodes_path = os.path.join(comfyui_path, "custom_nodes")
            venv_path = os.path.join(comfyui_path, "venv")
            pip_executable = os.path.join(venv_path, "bin", "pip")

            if not os.path.isdir(custom_nodes_path):
                return web.json_response({
                    'success': False, 
                    'error': 'Custom nodes directory not found'
                }, status=500)

            results = []
            successful_node_ids = []
            
            for node_data in nodes_data:
                try:
                    node_url = node_data.get('url')
                    node_id = node_data.get('id')
                    
                    if not node_url or not node_id:
                        logger.warning(f"Skipping invalid node data: {node_data}")
                        results.append({
                            'url': node_url,
                            'id': node_id,
                            'status': 'error',
                            'message': 'Invalid node data: missing url or id'
                        })
                        continue
                    
                    repo_name = node_url.split("/")[-1].replace(".git", "")
                    repo_path = os.path.join(custom_nodes_path, repo_name)

                    if os.path.isdir(repo_path):
                        logger.info(f"Custom node {repo_name} already exists.")
                        
                        # Check if requirements.txt exists and install dependencies in background
                        requirements_path = os.path.join(repo_path, "requirements.txt")
                        if os.path.isfile(requirements_path):
                            # Analyze requirements first
                            analysis = analyze_requirements(requirements_path, repo_name)
                            
                            if analysis['safe_to_install']:
                                # Start pip install in a separate thread
                                thread = threading.Thread(
                                    target=install_requirements_threaded,
                                    args=(pip_executable, requirements_path, repo_name, node_id),
                                    daemon=True
                                )
                                thread.start()
                                
                                results.append({
                                    'url': node_url,
                                    'id': node_id,
                                    'status': 'skipped',
                                    'message': f'Custom node {repo_name} already exists, installing {len(analysis["safe_to_install"])} safe dependencies in background'
                                })
                            else:
                                results.append({
                                    'url': node_url,
                                    'id': node_id,
                                    'status': 'skipped',
                                    'message': f'Custom node {repo_name} already exists (no new safe dependencies to install)'
                                })
                        else:
                            results.append({
                                'url': node_url,
                                'id': node_id,
                                'status': 'skipped',
                                'message': f'Custom node {repo_name} already exists (no requirements.txt found)'
                            })
                        
                        successful_node_ids.append(node_id)  # Consider existing nodes as successful
                        continue

                    logger.info(f"Cloning custom node from {node_url} into {repo_path}")
                    subprocess.run(["git", "clone", node_url, repo_path], check=True)

                    requirements_path = os.path.join(repo_path, "requirements.txt")
                    if os.path.isfile(requirements_path):
                        # Analyze requirements first
                        analysis = analyze_requirements(requirements_path, repo_name)
                        
                        if analysis['safe_to_install']:
                            # Start pip install in a separate thread for faster response
                            thread = threading.Thread(
                                target=install_requirements_threaded,
                                args=(pip_executable, requirements_path, repo_name, node_id),
                                daemon=True
                            )
                            thread.start()
                            
                            results.append({
                                'url': node_url,
                                'id': node_id,
                                'status': 'success',
                                'message': f'Custom node {repo_name} cloned successfully, installing {len(analysis["safe_to_install"])} safe dependencies in background'
                            })
                        else:
                            results.append({
                                'url': node_url,
                                'id': node_id,
                                'status': 'success',
                                'message': f'Custom node {repo_name} cloned successfully (no new safe dependencies to install)'
                            })
                    else:
                        results.append({
                            'url': node_url,
                            'id': node_id,
                            'status': 'success',
                            'message': f'Custom node {repo_name} installed (no requirements.txt found)'
                        })
                    
                    successful_node_ids.append(node_id)

                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to install custom node {node_url}: {e}")
                    results.append({
                        'url': node_url,
                        'id': node_id,
                        'status': 'error',
                        'message': f'Failed to install: {str(e)}'
                    })
                except Exception as e:
                    logger.error(f"An unexpected error occurred: {e}")
                    results.append({
                        'url': node_url,
                        'id': node_id,
                        'status': 'error',
                        'message': f'Unexpected error: {str(e)}'
                    })

            # Post successful node IDs back to the API
            if successful_node_ids:
                logger.info(f"Posting {len(successful_node_ids)} successful node IDs back to API...")
                post_response = post_data('api/machines/custom_nodes', {'node_ids': successful_node_ids})
                if post_response:
                    logger.info("Successfully posted node IDs to API")
                else:
                    logger.warning("Failed to post node IDs to API")

            return web.json_response({
                'success': True,
                'message': 'Custom nodes installation completed',
                'results': results,
                'successful_nodes_count': len(successful_node_ids),
                'posted_to_api': post_response is not None if successful_node_ids else False
            })

        except Exception as e:
            logger.error(f"Error processing custom nodes request: {e}")
            return web.json_response({
                'success': False, 
                'error': str(e)
            }, status=500)
