import os
import asyncio
import aiohttp
import logging
from aiohttp import web
from server import PromptServer
import threading
from typing import Dict, Optional
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global dictionary to track download progress
download_tasks: Dict[str, Dict] = {}
download_lock = threading.Lock()

class ModelDownloader:
    def __init__(self, url: str, path: str, comfyui_path: str):
        self.url = url
        self.path = path
        self.comfyui_path = comfyui_path
        self.full_path = os.path.join(comfyui_path, path)
        self.tmp_path = self.full_path + ".tmp"
        self.task_id = f"{url}:{path}"
        
    async def download_with_progress(self):
        """Download file with progress tracking and resume capability"""
        try:
            # Check if file already exists
            if os.path.exists(self.full_path):
                with download_lock:
                    download_tasks[self.task_id] = {
                        'progress': 100,
                        'status': 'completed',
                        'url': self.url,
                        'path': self.path,
                        'message': 'File already exists'
                    }
                return

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.full_path), exist_ok=True)
            
            # Check if partial download exists
            resume_pos = 0
            if os.path.exists(self.tmp_path):
                resume_pos = os.path.getsize(self.tmp_path)
                logger.info(f"Resuming download from position {resume_pos}")

            headers = {}
            if resume_pos > 0:
                headers['Range'] = f'bytes={resume_pos}-'

            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, headers=headers) as response:
                    if response.status not in [200, 206]:  # 206 for partial content
                        raise Exception(f"HTTP {response.status}: {response.reason}")
                    
                    # Get total file size
                    if response.status == 206:
                        # For resumed downloads, get size from Content-Range header
                        content_range = response.headers.get('Content-Range', '')
                        if content_range:
                            total_size = int(content_range.split('/')[-1])
                        else:
                            total_size = resume_pos + int(response.headers.get('Content-Length', 0))
                    else:
                        total_size = int(response.headers.get('Content-Length', 0))
                    
                    downloaded = resume_pos
                    
                    # Initialize progress tracking
                    with download_lock:
                        download_tasks[self.task_id] = {
                            'progress': 0 if total_size > 0 else -1,
                            'status': 'downloading',
                            'url': self.url,
                            'path': self.path,
                            'downloaded': downloaded,
                            'total': total_size,
                            'message': 'Downloading...'
                        }
                    
                    # Open file in append mode for resume
                    mode = 'ab' if resume_pos > 0 else 'wb'
                    with open(self.tmp_path, mode) as file:
                        async for chunk in response.content.iter_chunked(8192):
                            file.write(chunk)
                            downloaded += len(chunk)
                            
                            # Update progress
                            if total_size > 0:
                                progress = int((downloaded / total_size) * 100)
                                with download_lock:
                                    if self.task_id in download_tasks:
                                        download_tasks[self.task_id].update({
                                            'progress': progress,
                                            'downloaded': downloaded,
                                            'message': f'Downloading... {progress}%'
                                        })
            
            # Move from .tmp to final location (atomic operation)
            os.rename(self.tmp_path, self.full_path)
            
            # Update final status
            with download_lock:
                download_tasks[self.task_id] = {
                    'progress': 100,
                    'status': 'completed',
                    'url': self.url,
                    'path': self.path,
                    'downloaded': downloaded,
                    'total': total_size,
                    'message': 'Download completed successfully'
                }
            
            logger.info(f"Download completed: {self.full_path}")
            
        except Exception as e:
            logger.error(f"Download failed: {e}")
            with download_lock:
                download_tasks[self.task_id] = {
                    'progress': -1,
                    'status': 'error',
                    'url': self.url,
                    'path': self.path,
                    'message': f'Download failed: {str(e)}'
                }

def register_model_downloader_routes():
    @PromptServer.instance.routes.post('/download_model')
    async def download_model(request):
        try:
            # Parse JSON body
            data = await request.json()
            url = data.get('url')
            path = data.get('path')
            
            if not url or not path:
                return web.json_response({
                    'success': False,
                    'error': 'Both url and path are required'
                }, status=400)
            
            # Get ComfyUI path
            home_path = os.path.expanduser("~")
            comfyui_path = os.path.join(home_path, "ComfyUI")
            
            if not os.path.isdir(comfyui_path):
                return web.json_response({
                    'success': False,
                    'error': 'ComfyUI directory not found'
                }, status=500)
            
            task_id = f"{url}:{path}"
            
            # Check if task already exists
            with download_lock:
                if task_id in download_tasks:
                    existing_task = download_tasks[task_id]
                    return web.json_response({
                        'success': True,
                        'task_id': task_id,
                        'progress': existing_task['progress'],
                        'status': existing_task['status'],
                        'message': existing_task['message']
                    })
            
            # Start new download task
            downloader = ModelDownloader(url, path, comfyui_path)
            
            # Run download in background
            asyncio.create_task(downloader.download_with_progress())
            
            return web.json_response({
                'success': True,
                'task_id': task_id,
                'message': 'Download started',
                'progress': 0,
                'status': 'starting'
            })
            
        except Exception as e:
            logger.error(f"Error processing download request: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @PromptServer.instance.routes.get('/download_progress/{task_id}')
    async def get_download_progress(request):
        try:
            task_id = request.match_info['task_id']
            
            with download_lock:
                if task_id in download_tasks:
                    task = download_tasks[task_id]
                    return web.json_response({
                        'success': True,
                        'task_id': task_id,
                        'progress': task['progress'],
                        'status': task['status'],
                        'message': task['message'],
                        'downloaded': task.get('downloaded', 0),
                        'total': task.get('total', 0)
                    })
                else:
                    return web.json_response({
                        'success': False,
                        'error': 'Task not found'
                    }, status=404)
                    
        except Exception as e:
            logger.error(f"Error getting download progress: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @PromptServer.instance.routes.get('/download_tasks')
    async def list_download_tasks(request):
        try:
            with download_lock:
                return web.json_response({
                    'success': True,
                    'tasks': dict(download_tasks)
                })
                
        except Exception as e:
            logger.error(f"Error listing download tasks: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)