import os
import subprocess
import json
import logging
from aiohttp import web
from server import PromptServer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def register_custom_nodes_routes():
    @PromptServer.instance.routes.post('/custom_nodes')
    async def install_custom_nodes(request):
        try:
            # Parse JSON body
            data = await request.json()
            nodes = data.get('nodes', [])
            
            if not nodes or not isinstance(nodes, list):
                return web.json_response({
                    'success': False, 
                    'error': 'Invalid request: nodes array is required'
                }, status=400)

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
            
            for node_url in nodes:
                try:
                    repo_name = node_url.split("/")[-1].replace(".git", "")
                    repo_path = os.path.join(custom_nodes_path, repo_name)

                    if os.path.isdir(repo_path):
                        logger.info(f"Custom node {repo_name} already exists. Skipping.")
                        results.append({
                            'url': node_url,
                            'status': 'skipped',
                            'message': f'Custom node {repo_name} already exists'
                        })
                        continue

                    logger.info(f"Cloning custom node from {node_url} into {repo_path}")
                    subprocess.run(["git", "clone", node_url, repo_path], check=True)

                    requirements_path = os.path.join(repo_path, "requirements.txt")
                    if os.path.isfile(requirements_path):
                        logger.info(f"Installing dependencies from {requirements_path}")
                        subprocess.run([pip_executable, "install", "-r", requirements_path], check=True)
                        results.append({
                            'url': node_url,
                            'status': 'success',
                            'message': f'Custom node {repo_name} installed with dependencies'
                        })
                    else:
                        results.append({
                            'url': node_url,
                            'status': 'success',
                            'message': f'Custom node {repo_name} installed (no requirements.txt found)'
                        })

                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to install custom node {node_url}: {e}")
                    results.append({
                        'url': node_url,
                        'status': 'error',
                        'message': f'Failed to install: {str(e)}'
                    })
                except Exception as e:
                    logger.error(f"An unexpected error occurred: {e}")
                    results.append({
                        'url': node_url,
                        'status': 'error',
                        'message': f'Unexpected error: {str(e)}'
                    })

            return web.json_response({
                'success': True,
                'message': 'Custom nodes installation completed',
                'results': results
            })

        except Exception as e:
            logger.error(f"Error processing custom nodes request: {e}")
            return web.json_response({
                'success': False, 
                'error': str(e)
            }, status=500)