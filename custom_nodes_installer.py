import os
import subprocess
import json
import logging
import threading
from aiohttp import web
from server import PromptServer
from .helper.request_function import get_data, post_data

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def install_requirements_threaded(pip_executable, requirements_path, repo_name, node_id):
    """Install requirements in a separate thread for existing nodes"""
    try:
        logger.info(f"Installing dependencies for existing node {repo_name} in background...")
        subprocess.run([pip_executable, "install", "-r", requirements_path], check=True)
        logger.info(f"Successfully installed dependencies for {repo_name}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install dependencies for {repo_name}: {e}")
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
                                'message': f'Custom node {repo_name} already exists, installing dependencies in background'
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
                        logger.info(f"Installing dependencies from {requirements_path}")
                        subprocess.run([pip_executable, "install", "-r", requirements_path], check=True)
                        results.append({
                            'url': node_url,
                            'id': node_id,
                            'status': 'success',
                            'message': f'Custom node {repo_name} installed with dependencies'
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
