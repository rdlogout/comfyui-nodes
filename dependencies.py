"""
Dependencies Route Handler
Handles dependency management by fetching from API and installing custom nodes
"""

import logging
from aiohttp import web
from server import PromptServer
from .helper.request_function import get_data
from .helper.custom_node_installer import install_custom_node
from .helper.download_model import download_model

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def register_dependencies_routes():
    """Register the dependencies routes with PromptServer"""
    
    @PromptServer.instance.routes.get('/api/dependencies')
    async def dependencies_endpoint(request):
        """
        GET /api/dependencies
        Fetch dependencies from API and install custom nodes
        """
        try:
            logger.info("Fetching dependencies from API...")
            
            # Fetch dependencies from API
            dependencies_data = get_data('api/machines/dependencies')
            
            if not dependencies_data:
                return web.json_response({
                    'success': False,
                    'error': 'Failed to fetch dependencies from API'
                }, status=500)
            
            if not isinstance(dependencies_data, list):
                return web.json_response({
                    'success': False,
                    'error': 'Invalid dependencies data format'
                }, status=500)
            
            results = []
            
            # Process each dependency item
            for item in dependencies_data:
                item_id = item.get('id')
                custom_node_url = item.get('custom_node_url')
                model_repo_id = item.get('model_repo_id')
                model_filename = item.get('model_filename')
                model_is_directory = item.get('model_is_directory', False)
                model_local_dir = item.get('model_local_dir')

                
                if custom_node_url:
                    result = install_custom_node(custom_node_url)
                    if result is False:
                        results.append({
                            'id': item_id,
                            'msg': f'Failed to install custom node: {custom_node_url}'
                        })
                
                if model_repo_id:
                    # Determine download parameters based on model configuration
                    download_params = {
                        'repo_id': model_repo_id,
                        'local_dir': model_local_dir
                    }
                    
                    # Add filename if specified and not downloading directory
                    if model_filename and not model_is_directory:
                        download_params['filename'] = model_filename
                    
                    # Call download_model function
                    already_cached = download_model(**download_params)
                    
                    # Add to results if newly downloaded (not cached)
                    if not already_cached:
                        model_name = model_filename if model_filename else model_repo_id
                        results.append({
                            'id': item_id,
                            'msg': f'Downloaded model: {model_name}'
                        })
            
            return web.json_response({
                'success': True,
                'results': results
            })
            
        except Exception as e:
            logger.error(f"Error in dependencies endpoint: {str(e)}")
            return web.json_response({
                'success': False,
                'error': f'Internal server error: {str(e)}'
            }, status=500)