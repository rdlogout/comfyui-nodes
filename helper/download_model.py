"""
Simplified download utility for Hugging Face models and files.
Leverages HF Hub's built-in caching and locking mechanisms.
"""

import os
from typing import Optional, Union, List

from huggingface_hub import hf_hub_download, snapshot_download

# Global cache directory configuration with environment variable fallback
CACHE_DIR = os.environ.get('HF_HOME', os.path.expanduser('~/.cache/huggingface'))


def download_model(
    repo_id: str,
    local_dir: Optional[str] = None,
    filename: Optional[str] = None,
    allow_patterns: Optional[Union[str, List[str]]] = None,
    revision: Optional[str] = None,
    cache_dir: Optional[str] = None
) -> bool:
    """
    Download files from a Hugging Face repository.
    
    This function leverages HF Hub's built-in caching and locking mechanisms
    to prevent re-downloading and handle concurrent access automatically.
    
    Args:
        repo_id: Repository ID (e.g., "microsoft/DialoGPT-medium")
        local_dir: Local directory to download to (optional, uses HF cache if None)
        filename: Specific file to download (if None, downloads entire repo/folder)
        allow_patterns: Patterns of files to download (only used when filename is None)
        revision: Git revision (branch, tag, or commit hash, defaults to "main")
        cache_dir: Custom cache directory (defaults to HF_HOME or ~/.cache/huggingface)
        
    Returns:
        bool: True if file/repo was already downloaded (cached), False if newly downloaded or failed
        
    Examples:
        # Download a single file
        already_cached = download_model("microsoft/DialoGPT-medium", filename="config.json")
        
        # Download entire repository
        already_cached = download_model("microsoft/DialoGPT-medium")
        
        # Download with patterns
        already_cached = download_model("microsoft/DialoGPT-medium", allow_patterns=["*.json", "*.txt"])
        
        # Download to specific local directory
        already_cached = download_model("microsoft/DialoGPT-medium", local_dir="./models", filename="config.json")
    """
    try:
        # Use global cache directory if not specified
        effective_cache_dir = cache_dir or CACHE_DIR
        
        if filename:
            # Download single file using hf_hub_download
            print(f"Checking/downloading {filename} from {repo_id}...")
            
            # Check if file is already cached using try_to_load_from_cache
            from huggingface_hub import try_to_load_from_cache
            cached_path = try_to_load_from_cache(
                repo_id=repo_id,
                filename=filename,
                revision=revision,
                cache_dir=effective_cache_dir
            )
            
            if cached_path and isinstance(cached_path, str):
                print(f"File {filename} already cached")
                return True
            
            # File not cached, download it
            downloaded_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=local_dir,
                local_dir_use_symlinks=True,
                revision=revision,
                cache_dir=effective_cache_dir
            )
            
            print(f"Successfully downloaded {filename}")
            return False  # Newly downloaded
            
        else:
            # Download entire repository/folder using snapshot_download
            print(f"Checking/downloading repository {repo_id}...")
            
            # For repositories, we'll rely on HF Hub's internal caching
            # snapshot_download will use cached files when available
            downloaded_path = snapshot_download(
                repo_id=repo_id,
                local_dir=local_dir,
                local_dir_use_symlinks=True,
                revision=revision,
                cache_dir=effective_cache_dir,
                allow_patterns=allow_patterns
            )
            
            print(f"Repository {repo_id} processed (may use cached files)")
            return False  # Always return False for repo downloads as we can't easily determine if fully cached
            
    except Exception as e:
        print(f"Error downloading from {repo_id}: {e}")
        return False


# Export the main function
__all__ = ["download_model", "CACHE_DIR"]
