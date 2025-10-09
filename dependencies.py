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
                item_name = item.get('name')
                item_type = item.get('type')  # 'model' or 'custom_node'
                item_url = item.get('url')
                model_repo_id = item.get('model_repo_id')
                model_type = item.get('model_type')  # 'file', 'folder', or 'repo'
                model_local_dir = item.get('model_local_dir')
                model_allow_patterns = item.get('model_allow_patterns')
                
                # Validate required fields
                if not item_type:
                    logger.warning(f"Skipping dependency {item_id}: missing 'type' field")
                    continue
                    
                if item_type not in ['model', 'custom_node']:
                    logger.warning(f"Skipping dependency {item_id}: invalid type '{item_type}'. Must be 'model' or 'custom_node'")
                    continue

                
                if item_type == 'custom_node':
                    if not item_url:
                        logger.warning(f"Skipping custom_node dependency {item_id}: missing 'url' field")
                        results.append({
                            'id': item_id,
                            'msg': f'Failed to install custom node {item_name or item_id}: missing URL'
                        })
                        continue
                        
                    result = install_custom_node(item_url)
                    if result is False:
                        results.append({
                            'id': item_id,
                            'msg': f'Failed to install custom node: {item_name or item_url}'
                        })
                
                elif item_type == 'model':
                    if not model_repo_id:
                        logger.warning(f"Skipping model dependency {item_id}: missing 'model_repo_id' field")
                        results.append({
                            'id': item_id,
                            'msg': f'Failed to download model {item_name or item_id}: missing repository ID'
                        })
                        continue
                        
                    if model_type and model_type not in ['file', 'folder', 'repo']:
                        logger.warning(f"Invalid model_type '{model_type}' for dependency {item_id}. Using default behavior.")
                        model_type = None
                    # Determine download parameters based on model configuration
                    download_params = {
                        'repo_id': model_repo_id,
                        'local_dir': model_local_dir
                    }
                    
                    # Handle different model types
                    if model_type == 'file' and item_name:
                        # For single file downloads
                        download_params['filename'] = item_name
                    elif model_type == 'folder':
                        # For folder downloads, don't specify filename
                        pass
                    elif model_type == 'repo':
                        # For full repository downloads
                        pass
                    
                    # Add allow patterns if specified
                    if model_allow_patterns:
                        download_params['allow_patterns'] = model_allow_patterns.split(',') if isinstance(model_allow_patterns, str) else model_allow_patterns
                    
                    # Call download_model function
                    already_cached = download_model(**download_params)
                    
                    # Add to results if newly downloaded (not cached)
                    if not already_cached:
                        model_name = item_name if item_name else model_repo_id
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