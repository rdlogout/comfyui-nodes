import os
import asyncio
import aiohttp
import logging
from aiohttp import web, ClientTimeout
from server import PromptServer
import threading
from typing import Dict, Optional
import time
import sys
import random
from .helper.request_function import get_data
from .comfy_services import get_comfyui_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global dictionary to track download progress
download_tasks: Dict[str, Dict] = {}
download_lock = threading.Lock()

# Constants for retry mechanism
MAX_RETRIES = 3
BASE_DELAY = 1.0  # Base delay in seconds
MAX_DELAY = 60.0  # Maximum delay in seconds

class ModelDownloader:
    def __init__(self, url: str, path: str, comfyui_path: str, force: bool = False):
        self.url = url
        # Ensure path is relative by removing leading slashes
        self.path = path.lstrip('/')
        self.comfyui_path = comfyui_path
        self.force = force  # Force re-download even if file exists
        self.full_path = os.path.join(comfyui_path, self.path)
        self.tmp_path = self.full_path + ".tmp"
        self.task_id = f"{url}:{self.path}"
        self.retry_count = 0
        
        # Log download start for visibility
        logger.info(f"ModelDownloader: {os.path.basename(self.path)} (force={self.force})")
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter"""
        delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
        # Add jitter to prevent thundering herd
        jitter = random.uniform(0.1, 0.3) * delay
        return delay + jitter
    
    def _format_bytes(self, bytes_count: int) -> str:
        """Format bytes into human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_count < 1024.0:
                return f"{bytes_count:.1f}{unit}"
            bytes_count /= 1024.0
        return f"{bytes_count:.1f}TB"
    
    def _log_progress(self, downloaded: int, total: int, speed: float = 0):
        """Log progress in a single line like wget/curl"""
        if total > 0:
            percent = (downloaded / total) * 100
            downloaded_str = self._format_bytes(downloaded)
            total_str = self._format_bytes(total)
            speed_str = self._format_bytes(speed) + "/s" if speed > 0 else ""
            
            # Create progress bar
            bar_width = 30
            filled = int(bar_width * downloaded / total)
            bar = "=" * filled + ">" + " " * (bar_width - filled - 1)
            
            # Print progress on same line (overwrite previous)
            progress_line = f"\r{percent:6.1f}% [{bar}] {downloaded_str}/{total_str} {speed_str}"
            print(progress_line, end="", flush=True)
        else:
            downloaded_str = self._format_bytes(downloaded)
            speed_str = self._format_bytes(speed) + "/s" if speed > 0 else ""
            progress_line = f"\r{downloaded_str} downloaded {speed_str}"
            print(progress_line, end="", flush=True)
        
    async def download_with_progress(self):
        """Download file with progress tracking, resume capability, and retry logic"""
        logger.info(f"download_with_progress called for: {self.path}")
        logger.info(f"download_with_progress details - URL: {self.url}, Full path: {self.full_path}, Force: {self.force}")
        for attempt in range(MAX_RETRIES + 1):
            try:
                # Initialize or update task in download_tasks
                with download_lock:
                    if self.task_id not in download_tasks:
                        download_tasks[self.task_id] = {
                            'progress': 0,
                            'status': 'starting',
                            'url': self.url,
                            'path': self.path,
                            'message': 'Checking file status...',
                            'downloaded': 0,
                            'total': 0,
                            'retry_count': 0
                        }
                    
                    # Update retry count
                    download_tasks[self.task_id]['retry_count'] = attempt
                    if attempt > 0:
                        download_tasks[self.task_id]['message'] = f'Retrying download (attempt {attempt + 1}/{MAX_RETRIES + 1})...'
                
                # Check if file already exists and handle based on force parameter
                if os.path.exists(self.full_path) and not self.force:
                    actual_size = os.path.getsize(self.full_path)
                    
                    # If force=false and file exists with reasonable size (> 0), skip verification
                    if actual_size > 0:
                        logger.info(f"File already exists, skipping verification (force=false): {self.full_path}")
                        with download_lock:
                            download_tasks[self.task_id] = {
                                'progress': 100,
                                'status': 'completed',
                                'url': self.url,
                                'path': self.path,
                                'message': 'File already exists (skipped verification)',
                                'downloaded': actual_size,
                                'total': actual_size,
                                'retry_count': 0
                            }
                        print(f"\nFile already exists: {self.path}")
                        return  # This is correct - skip download if file exists and force=false
                    else:
                        # File exists but has 0 size - delete and re-download
                        logger.info(f"File exists but is empty, deleting: {self.full_path}")
                        os.remove(self.full_path)
                elif os.path.exists(self.full_path) and self.force:
                    # Force re-download - verify file size with server
                    actual_size = os.path.getsize(self.full_path)
                    
                    if actual_size > 0:
                        try:
                            timeout = ClientTimeout(total=30, connect=10)
                            async with aiohttp.ClientSession(timeout=timeout) as session:
                                async with session.head(self.url) as response:
                                    if response.status == 200:
                                        expected_size = int(response.headers.get('Content-Length', 0))
                                        
                                        if expected_size > 0 and actual_size == expected_size:
                                            # File is complete, but force=true means we should re-download
                                            logger.info(f"File exists and is complete, but force=true - re-downloading: {self.full_path}")
                                            os.remove(self.full_path)  # Delete existing file
                                        elif expected_size > 0 and actual_size != expected_size:
                                            logger.info(f"File exists but size mismatch (force=true). Expected: {expected_size}, Actual: {actual_size}")
                                            os.remove(self.full_path)  # Delete mismatched file
                                        else:
                                            # Server doesn't provide Content-Length, re-download
                                            logger.info(f"Server doesn't provide size info (force=true), re-downloading: {self.full_path}")
                                            os.remove(self.full_path)
                                    else:
                                        # Server error, but force=true means re-download anyway
                                        logger.info(f"Server unreachable (force=true), re-downloading: {self.full_path}")
                                        os.remove(self.full_path)
                        except Exception as e:
                            logger.warning(f"Could not verify file size from server (force=true): {e}")
                            # Server verification failed, but force=true means re-download anyway
                            logger.info(f"Server verification failed (force=true), re-downloading: {self.full_path}")
                            os.remove(self.full_path)
                    else:
                        # File exists but has 0 size - delete and re-download
                        logger.info(f"File exists but is empty (force=true), deleting: {self.full_path}")
                        os.remove(self.full_path)

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

                # Configure session with better timeouts and connection settings
                connector = aiohttp.TCPConnector(
                    limit=10,
                    limit_per_host=5,
                    ttl_dns_cache=300,
                    use_dns_cache=True,
                    keepalive_timeout=30,
                    enable_cleanup_closed=True
                )
                timeout = ClientTimeout(total=300, connect=30, sock_read=60)  # Increased timeouts
                
                logger.info(f"Making HTTP request to: {self.url}")
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                    async with session.get(self.url, headers=headers) as response:
                        logger.info(f"HTTP response received: {response.status} for {self.url}")
                        if response.status not in [200, 206]:  # 206 for partial content
                            raise aiohttp.ClientResponseError(
                                request_info=response.request_info,
                                history=response.history,
                                status=response.status,
                                message=f"HTTP {response.status}: {response.reason}"
                            )
                        
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
                        last_update_time = time.time()
                        last_downloaded = downloaded
                        
                        # Update progress tracking with download info
                        with download_lock:
                            download_tasks[self.task_id].update({
                                'progress': int((downloaded / total_size) * 100) if total_size > 0 else 0,
                                'status': 'downloading',
                                'downloaded': downloaded,
                                'total': total_size,
                                'message': 'Starting download...'
                            })
                        
                        print(f"\nDownloading: {self.path}")
                        logger.info(f"Starting to write data to file: {self.tmp_path}")
                        
                        # Open file in append mode for resume
                        mode = 'ab' if resume_pos > 0 else 'wb'
                        with open(self.tmp_path, mode) as file:
                            chunk_size = 32768  # Increased chunk size for better performance
                            async for chunk in response.content.iter_chunked(chunk_size):
                                file.write(chunk)
                                downloaded += len(chunk)
                                
                                # Calculate speed and update progress
                                current_time = time.time()
                                if current_time - last_update_time >= 0.5:  # Update every 0.5 seconds
                                    speed = (downloaded - last_downloaded) / (current_time - last_update_time)
                                    self._log_progress(downloaded, total_size, speed)
                                    
                                    # Update progress in download_tasks
                                    if total_size > 0:
                                        progress = int((downloaded / total_size) * 100)
                                        with download_lock:
                                            if self.task_id in download_tasks:
                                                download_tasks[self.task_id].update({
                                                    'progress': progress,
                                                    'downloaded': downloaded,
                                                    'message': f'Downloading... {progress}%'
                                                })
                                    
                                    last_update_time = current_time
                                    last_downloaded = downloaded
                
                # Final progress update
                if total_size > 0:
                    self._log_progress(downloaded, total_size)
                print()  # New line after progress
                
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
                        'message': 'Download completed successfully',
                        'retry_count': attempt
                    }
                
                logger.info(f"Download completed: {self.full_path}")
                print(f"Download completed: {self.path}")
                
                # Refresh ComfyUI object info to update model cache
                try:
                    await refresh_comfyui_object_info()
                except Exception as e:
                    logger.warning(f"Failed to refresh ComfyUI object info: {e}")
                
                return  # Success, exit retry loop
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Download attempt {attempt + 1} failed: {error_msg}")
                
                # Determine if this error is retryable
                is_retryable = True
                should_keep_partial = True
                
                # Categorize errors for better retry handling
                if isinstance(e, aiohttp.ClientResponseError):
                    if e.status in [404, 410]:  # Not found or gone - don't retry
                        is_retryable = False
                        should_keep_partial = False
                    elif e.status in [401, 403]:  # Authentication errors - don't retry
                        is_retryable = False
                        should_keep_partial = False
                    elif e.status >= 500:  # Server errors - retry with longer delay
                        should_keep_partial = True
                    else:  # Other HTTP errors - retry
                        should_keep_partial = True
                elif isinstance(e, (aiohttp.ClientConnectorError, aiohttp.ClientProxyConnectionError)):
                    # Network connection errors - retry
                    should_keep_partial = True
                elif isinstance(e, asyncio.TimeoutError):
                    # Timeout errors - retry
                    should_keep_partial = True
                elif isinstance(e, (ConnectionError, OSError)):
                    # Connection and OS errors - retry
                    should_keep_partial = True
                else:
                    # Unknown errors - retry cautiously
                    should_keep_partial = True
                
                # Clean up partial download based on error type
                if os.path.exists(self.tmp_path):
                    if not should_keep_partial or attempt == MAX_RETRIES:
                        # Remove partial file on non-retryable errors or final failure
                        os.remove(self.tmp_path)
                        logger.info(f"Removed partial download: {self.tmp_path}")
                    elif should_keep_partial and attempt < MAX_RETRIES:
                        # Keep partial file for resume on retryable errors
                        logger.info(f"Keeping partial download for resume: {self.tmp_path}")
                
                if attempt < MAX_RETRIES and is_retryable:
                    # Calculate delay for next retry
                    delay = self._calculate_retry_delay(attempt)
                    logger.info(f"Retrying in {delay:.1f} seconds... (retryable error)")
                    
                    with download_lock:
                        download_tasks[self.task_id].update({
                            'status': 'retrying',
                            'message': f'Retry {attempt + 1}/{MAX_RETRIES} in {delay:.1f}s: {error_msg}'
                        })
                    
                    await asyncio.sleep(delay)
                else:
                    # Final failure or non-retryable error
                    final_status = 'error'
                    if not is_retryable:
                        final_status = 'failed_permanent'
                        error_msg = f'Non-retryable error: {error_msg}'
                    
                    with download_lock:
                        download_tasks[self.task_id] = {
                            'progress': -1,
                            'status': final_status,
                            'url': self.url,
                            'path': self.path,
                            'message': f'Download failed after {attempt + 1} attempts: {error_msg}',
                            'retry_count': attempt
                        }
                    logger.error(f"Download failed permanently after {attempt + 1} attempts: {error_msg}")
                    print(f"\nDownload failed: {self.path} - {error_msg}")
                    break

async def refresh_comfyui_object_info():
    """Call ComfyUI's object_info API to refresh model cache after download completion"""
    try:
        config = get_comfyui_config()
        object_info_url = f"{config['url']}/api/object_info"
        
        logger.info(f"Refreshing ComfyUI object info: {object_info_url}")
        
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as session:
            async with session.get(object_info_url) as response:
                if response.status == 200:
                    logger.info("Successfully refreshed ComfyUI object info")
                    return True
                else:
                    logger.warning(f"Failed to refresh object info: HTTP {response.status}")
                    return False
                    
    except Exception as e:
        logger.error(f"Error refreshing ComfyUI object info: {e}")
        return False

def register_model_downloader_routes():
    async def process_single_model(model_data, comfyui_path, semaphore, session):
        """Process a single model with concurrency control and shared session"""
        async with semaphore:  # Limit concurrent operations
            try:
                model_url = model_data.get('url')
                model_id = model_data.get('id')
                model_path = model_data.get('path')
                force = model_data.get('force', False)  # Default to False for backward compatibility
                
                if not model_url or not model_id or not model_path:
                    logger.warning(f"Skipping invalid model data: {model_data}")
                    return {
                        'id': model_id,
                        'path': model_path,
                        'progress': -1  # Error indicator
                    }
                
                # Validate force parameter
                if not isinstance(force, bool):
                    force = str(force).lower() in ['true', '1', 'yes']
                
                # Create downloader with force parameter
                logger.info(f"Creating ModelDownloader for: {os.path.basename(model_path)}")
                logger.info(f"  URL: {model_url}")
                logger.info(f"  Path: {model_path}")
                logger.info(f"  Force: {force}")
                
                downloader = ModelDownloader(model_url, model_path, comfyui_path, force=force)
                task_id = downloader.task_id
                
                logger.info(f"ModelDownloader created successfully. Task ID: {task_id}")
                logger.info(f"Processing model: {os.path.basename(model_path)} (force={force})")
                
                # Check if file already exists and handle based on force parameter
                if os.path.exists(downloader.full_path):
                    actual_size = os.path.getsize(downloader.full_path)
                    
                    # If file has reasonable size (> 0), try to verify with server
                    if actual_size > 0:
                        try:
                            # Use shared session for better performance with increased timeout
                            async with session.head(model_url, timeout=ClientTimeout(total=30, connect=10)) as response:
                                if response.status == 200:
                                    expected_size = int(response.headers.get('Content-Length', 0))
                                    
                                    if expected_size > 0 and actual_size == expected_size:
                                        # File is complete
                                        if force:
                                            logger.debug(f"File exists and is complete, but force=true - re-downloading: {os.path.basename(downloader.full_path)}")
                                            os.remove(downloader.full_path)  # Delete existing file
                                        else:
                                            return {
                                                'id': model_id,
                                                'path': model_path,
                                                'progress': 100
                                            }
                                    elif expected_size > 0 and actual_size != expected_size:
                                        logger.debug(f"File exists but size mismatch for {os.path.basename(model_url)}. Expected: {expected_size}, Actual: {actual_size}")
                                        # Continue to re-download
                                    else:
                                        # Server doesn't provide Content-Length
                                        if force:
                                            logger.debug(f"Server doesn't provide size info (force=true), re-downloading: {os.path.basename(downloader.full_path)}")
                                            os.remove(downloader.full_path)
                                        else:
                                            return {
                                                'id': model_id,
                                                'path': model_path,
                                                'progress': 100
                                            }
                                else:
                                    # Server error
                                    if force:
                                        logger.debug(f"Server unreachable (force=true), re-downloading: {os.path.basename(downloader.full_path)}")
                                        os.remove(downloader.full_path)
                                    else:
                                        return {
                                            'id': model_id,
                                            'path': model_path,
                                            'progress': 100
                                        }
                        except Exception as e:
                            logger.debug(f"Could not verify file size for {os.path.basename(model_url)}: {e}")
                            # Server verification failed
                            if force:
                                logger.debug(f"Server verification failed (force=true), re-downloading: {os.path.basename(downloader.full_path)}")
                                os.remove(downloader.full_path)
                            else:
                                return {
                                    'id': model_id,
                                    'path': model_path,
                                    'progress': 100
                                }
                    else:
                        # File exists but has 0 size - delete and re-download
                        logger.debug(f"File exists but is empty, deleting: {os.path.basename(downloader.full_path)}")
                        os.remove(downloader.full_path)
                
                # Check if download is already in progress
                with download_lock:
                    if task_id in download_tasks and not force:
                        existing_task = download_tasks[task_id]
                        progress = existing_task['progress']
                        if progress == -1:  # Error state
                            progress = 0  # Reset for retry
                        return {
                            'id': model_id,
                            'path': model_path,
                            'progress': progress
                        }
                    elif task_id in download_tasks and force:
                        # If force=true and task exists, reset the task for re-download
                        logger.debug(f"Force download requested for {task_id}, resetting existing task")
                        del download_tasks[task_id]
                
                # File doesn't exist or is incomplete, schedule download
                logger.info(f"Starting download for: {os.path.basename(model_path)}")
                
                # Create the download task with error handling
                try:
                    download_task = asyncio.create_task(downloader.download_with_progress())
                    logger.info(f"Download task created successfully for: {os.path.basename(model_path)}")
                    
                    # Add a callback to log if the task fails
                    def task_done_callback(task):
                        try:
                            exception = task.exception()
                            if exception:
                                logger.error(f"Download task failed for {os.path.basename(model_path)}: {exception}")
                            else:
                                logger.info(f"Download task completed for: {os.path.basename(model_path)}")
                        except asyncio.CancelledError:
                            logger.warning(f"Download task was cancelled for: {os.path.basename(model_path)}")
                        except Exception as e:
                            logger.error(f"Error in download task callback for {os.path.basename(model_path)}: {e}")
                    
                    download_task.add_done_callback(task_done_callback)
                    
                except Exception as e:
                    logger.error(f"Failed to create download task for {os.path.basename(model_path)}: {e}")
                    return {
                        'id': model_id,
                        'path': model_path,
                        'progress': -1  # Error indicator
                    }
                
                return {
                    'id': model_id,
                    'path': model_path,
                    'progress': 0
                }
                
            except Exception as e:
                logger.error(f"Error processing model {model_data}: {e}")
                return {
                    'id': model_data.get('id'),
                    'path': model_data.get('path'),
                    'progress': -1  # Error indicator
                }

    @PromptServer.instance.routes.get('/api/sync-models')
    @PromptServer.instance.routes.post('/api/sync-models')
    async def download_models(request):
        try:
            # Fetch models data from API
            logger.info("Fetching models from API...")
            models_data = get_data('api/machines/models')
            
            if not models_data or not isinstance(models_data, list):
                return web.json_response({
                    'success': False,
                    'error': 'Failed to fetch models data from API'
                }, status=500)
            
            # Display the models list we received
            logger.info(f"📥 Received {len(models_data)} models from API:")
            for i, model in enumerate(models_data):  # Show ALL models
                model_name = os.path.basename(model.get('path', 'unknown'))
                model_id = model.get('id', 'unknown')
                logger.info(f"   {i+1}. {model_name} (ID: {model_id})")
            
            # Get ComfyUI path
            home_path = os.path.expanduser("~")
            comfyui_path = os.path.join(home_path, "ComfyUI")
            
            if not os.path.isdir(comfyui_path):
                return web.json_response({
                    'success': False,
                    'error': f'ComfyUI directory not found at {comfyui_path}'
                }, status=500)
            
            # Create semaphore to limit concurrent operations (max 8 concurrent checks/downloads)
            semaphore = asyncio.Semaphore(8)
            
            # Process all models in parallel with shared session
            logger.info(f"Processing {len(models_data)} models...")
            logger.info("=" * 60)
            
            # Configure session with connection pooling and timeouts
            connector = aiohttp.TCPConnector(
                limit=20,  # Total connection pool size
                limit_per_host=5,  # Max connections per host (reduced to prevent overwhelming servers)
                ttl_dns_cache=300,  # DNS cache TTL
                use_dns_cache=True,
                keepalive_timeout=30,
                enable_cleanup_closed=True,
                force_close=False
            )
            
            timeout = ClientTimeout(total=60, connect=15, sock_read=30)  # Increased timeouts
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                tasks = [process_single_model(model_data, comfyui_path, semaphore, session) for model_data in models_data]
                models_status = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Handle any exceptions that occurred during processing
            final_models_status = []
            downloaded_count = 0
            skipped_count = 0
            error_count = 0
            
            for i, result in enumerate(models_status):
                model_name = os.path.basename(models_data[i].get('path', 'unknown'))
                model_id = models_data[i].get('id', 'unknown')
                
                if isinstance(result, Exception):
                    logger.error(f"❌ {model_name}: Error - {result}")
                    final_models_status.append({
                        'id': model_id,
                        'path': models_data[i].get('path'),
                        'progress': -1
                    })
                    error_count += 1
                else:
                    final_models_status.append(result)
                    if result['progress'] == 100:
                        logger.info(f"✅ {model_name}: Already downloaded")
                        downloaded_count += 1
                    elif result['progress'] == 0:
                        logger.info(f"⬇️  {model_name}: Queued for download")
                        skipped_count += 1  # Track queued downloads
                    elif result['progress'] == -1:
                        logger.info(f"❌ {model_name}: Error")
                        error_count += 1
                    else:
                        logger.info(f"⏳ {model_name}: {result['progress']}% complete")
                        skipped_count += 1  # Track in-progress downloads
            
            # Print summary
            logger.info(f"\n📊 Model Sync Summary:")
            logger.info(f"   ✅ Already downloaded: {downloaded_count}")
            logger.info(f"   ⬇️  Queued for download: {skipped_count}")
            logger.info(f"   ❌ Errors: {error_count}")
            logger.info(f"   📋 Total models: {len(models_data)}")
            logger.info("=" * 60)
            
            return web.json_response({
                'success': True,
                'message': 'Models download status checked and downloads scheduled',
                'models': final_models_status,
                'summary': {
                    'total': len(models_data),
                    'downloaded': downloaded_count,
                    'queued': len(models_data) - downloaded_count - skipped_count - error_count,
                    'errors': error_count
                }
            })
            
        except Exception as e:
            logger.error(f"Error processing models download request: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    # Keep the original POST route for backward compatibility
    @PromptServer.instance.routes.post('/download_model')
    async def download_single_model(request):
        try:
            # Parse JSON body
            data = await request.json()
            url = data.get('url')
            path = data.get('path')
            force = data.get('force', False)  # Default to False for backward compatibility
            
            if not url or not path:
                return web.json_response({
                    'success': False,
                    'error': 'Both url and path are required'
                }, status=400)
            
            # Validate force parameter
            if not isinstance(force, bool):
                force = str(force).lower() in ['true', '1', 'yes']
            
            # Get ComfyUI path
            home_path = os.path.expanduser("~")
            comfyui_path = os.path.join(home_path, "ComfyUI")
            
            logger.debug(f"ComfyUI path: {comfyui_path}")
            logger.debug(f"Requested path: {path}")
            logger.debug(f"Force download: {force}")
            
            if not os.path.isdir(comfyui_path):
                return web.json_response({
                    'success': False,
                    'error': f'ComfyUI directory not found at {comfyui_path}'
                }, status=500)
            
            # Create downloader with force parameter
            downloader = ModelDownloader(url, path, comfyui_path, force=force)
            task_id = downloader.task_id
            
            # Check if task already exists and not forced
            with download_lock:
                if task_id in download_tasks and not force:
                    existing_task = download_tasks[task_id]
                    return web.json_response({
                        'success': True,
                        'task_id': task_id,
                        'progress': existing_task['progress'],
                        'status': existing_task['status'],
                        'message': existing_task['message'],
                        'force': force
                    })
                elif task_id in download_tasks and force:
                    # If force=true and task exists, reset the task for re-download
                    logger.debug(f"Force download requested, resetting existing task: {task_id}")
                    del download_tasks[task_id]
            
            # Run download in background
            asyncio.create_task(downloader.download_with_progress())
            logger.debug(f"Started download for {os.path.basename(path)} (force={force})")
            
            return web.json_response({
                'success': True,
                'task_id': task_id,
                'message': 'Download started',
                'progress': 0,
                'status': 'starting',
                'force': force
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
            task_id = request.match_info.get('task_id', '').strip()
            
            if not task_id:
                return web.json_response({
                    'success': False,
                    'error': 'Task ID is required'
                }, status=400)
            
            with download_lock:
                if task_id in download_tasks:
                    task = download_tasks[task_id]
                    return web.json_response({
                        'success': True,
                        'task_id': task_id,
                        'progress': task.get('progress', 0),
                        'status': task.get('status', 'unknown'),
                        'message': task.get('message', ''),
                        'downloaded': task.get('downloaded', 0),
                        'total': task.get('total', 0),
                        'retry_count': task.get('retry_count', 0)
                    })
                else:
                    return web.json_response({
                        'success': False,
                        'error': f'Task not found: {task_id}'
                    }, status=404)
                    
        except Exception as e:
            logger.error(f"Error getting download progress for task {task_id}: {e}")
            return web.json_response({
                'success': False,
                'error': f'Internal server error: {str(e)}'
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