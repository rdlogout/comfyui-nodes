import os
import subprocess
import logging
import shutil
from pathlib import Path
from aiohttp import web
from server import PromptServer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
REPO_URL = "https://github.com/rdlogout/comfyui-nodes"
COMFY_DIR = os.path.expanduser("~/ComfyUI")
CUSTOM_NODES_DIR = os.path.join(COMFY_DIR, "custom_nodes")
TARGET_DIR = os.path.join(CUSTOM_NODES_DIR, "comfyui-nodes")

def check_comfyui_installation():
    """Check if ComfyUI directory exists and create custom_nodes if needed"""
    if not os.path.isdir(COMFY_DIR):
        raise Exception(f"ComfyUI directory not found at {COMFY_DIR}. Please install ComfyUI first.")
    
    if not os.path.isdir(CUSTOM_NODES_DIR):
        logger.warning("custom_nodes directory not found, creating it...")
        os.makedirs(CUSTOM_NODES_DIR, exist_ok=True)
    
    return True

def check_git():
    """Check if git is installed"""
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise Exception("Git is not installed. Please install git first.")

def get_git_revision(directory):
    """Get the current git revision"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=directory,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def get_remote_revision(directory, branch="main"):
    """Get the remote git revision"""
    try:
        # Try main branch first, then master
        for branch_name in ["main", "master"]:
            try:
                result = subprocess.run(
                    ["git", "rev-parse", f"origin/{branch_name}"],
                    cwd=directory,
                    check=True,
                    capture_output=True,
                    text=True
                )
                return result.stdout.strip()
            except subprocess.CalledProcessError:
                continue
        return None
    except subprocess.CalledProcessError:
        return None

def clone_repository():
    """Clone the repository"""
    logger.info(f"Cloning repository from {REPO_URL}...")
    
    try:
        subprocess.run(
            ["git", "clone", REPO_URL, "comfyui-nodes"],
            cwd=CUSTOM_NODES_DIR,
            check=True,
            capture_output=True
        )
        logger.info(f"Repository cloned successfully to {TARGET_DIR}")
        return True
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to clone repository: {e}")

def update_repository():
    """Update existing repository"""
    logger.info("Updating existing repository...")
    
    try:
        # Fetch latest changes
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=TARGET_DIR,
            check=True,
            capture_output=True
        )
        
        # Check if updates are available
        local_rev = get_git_revision(TARGET_DIR)
        remote_rev = get_remote_revision(TARGET_DIR)
        
        if local_rev == remote_rev:
            logger.info("Repository is already up to date!")
            return {"updated": False, "message": "Repository is already up to date"}
        else:
            # Pull latest changes
            try:
                subprocess.run(
                    ["git", "pull", "origin", "main"],
                    cwd=TARGET_DIR,
                    check=True,
                    capture_output=True
                )
            except subprocess.CalledProcessError:
                subprocess.run(
                    ["git", "pull", "origin", "master"],
                    cwd=TARGET_DIR,
                    check=True,
                    capture_output=True
                )
            
            logger.info("Repository updated successfully!")
            return {"updated": True, "message": "Repository updated successfully"}
            
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to update repository: {e}")

def install_or_update():
    """Install or update the repository"""
    if os.path.isdir(TARGET_DIR):
        logger.info(f"Directory exists at {TARGET_DIR}")
        
        # Check if it's a git repository
        if os.path.isdir(os.path.join(TARGET_DIR, ".git")):
            return update_repository()
        else:
            logger.warning("Directory exists but is not a git repository")
            logger.info("Removing existing directory and cloning fresh...")
            shutil.rmtree(TARGET_DIR)
            clone_repository()
            return {"updated": True, "message": "Directory replaced and repository cloned"}
    else:
        clone_repository()
        return {"updated": True, "message": "Repository cloned successfully"}

def install_dependencies():
    """Install dependencies if requirements.txt exists"""
    requirements_path = os.path.join(TARGET_DIR, "requirements.txt")
    
    if os.path.isfile(requirements_path):
        logger.info("Installing Python dependencies...")
        
        try:
            # Try to use pip from ComfyUI's virtual environment first
            venv_pip = os.path.join(COMFY_DIR, "venv", "bin", "pip")
            if os.path.isfile(venv_pip):
                subprocess.run(
                    [venv_pip, "install", "-r", requirements_path],
                    check=True,
                    capture_output=True
                )
            else:
                # Fallback to system pip
                subprocess.run(
                    ["pip", "install", "-r", requirements_path],
                    check=True,
                    capture_output=True
                )
            
            logger.info("Dependencies installed successfully!")
            return {"dependencies_installed": True}
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to install dependencies: {e}")
            return {"dependencies_installed": False, "error": str(e)}
    else:
        logger.info("No requirements.txt found, skipping dependency installation")
        return {"dependencies_installed": False, "message": "No requirements.txt found"}

def register_pull_update_routes():
    @PromptServer.instance.routes.get('/api/pull-update')
    @PromptServer.instance.routes.post('/api/pull-update')
    async def pull_update(request):
        try:
            logger.info("Starting ComfyUI Nodes pull-update process...")
            
            # Check prerequisites
            check_git()
            check_comfyui_installation()
            
            # Install or update repository
            repo_result = install_or_update()
            
            # Install dependencies
            deps_result = install_dependencies()
            
            # Combine results
            result = {
                "success": True,
                "message": "Pull-update completed successfully",
                "repository": repo_result,
                "dependencies": deps_result,
                "target_directory": TARGET_DIR
            }
            
            logger.info("Pull-update completed successfully!")
            return web.json_response(result)
            
        except Exception as e:
            logger.error(f"Error during pull-update: {e}")
            return web.json_response({
                "success": False,
                "error": str(e),
                "message": "Pull-update failed"
            }, status=500)