

#!/usr/bin/env bash

# ComfyUI Nodes Installation Script
# This script will install or update the comfyui-nodes repository in ComfyUI's custom_nodes directory

# set -e  # Exit on any error

# Configuration
REPO_URL="https://github.com/rdlogout/comfyui-nodes"
COMFY_DIR="$HOME/ComfyUI"
CUSTOM_NODES_DIR="$COMFY_DIR/custom_nodes"
TARGET_DIR="$CUSTOM_NODES_DIR/comfyui-nodes"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if ComfyUI directory exists
check_comfyui_installation() {
    if [ ! -d "$COMFY_DIR" ]; then
        print_error "ComfyUI directory not found at $COMFY_DIR"
        print_error "Please install ComfyUI first or set the correct path"
        exit 1
    fi
    
    if [ ! -d "$CUSTOM_NODES_DIR" ]; then
        print_warning "custom_nodes directory not found, creating it..."
        mkdir -p "$CUSTOM_NODES_DIR"
    fi
}

# Check if git is installed
check_git() {
    if ! command -v git &> /dev/null; then
        print_error "Git is not installed. Please install git first."
        exit 1
    fi
}

# Install or update the repository
install_or_update() {
    if [ -d "$TARGET_DIR" ]; then
        print_status "Directory exists at $TARGET_DIR"
        
        # Check if it's a git repository
        if [ -d "$TARGET_DIR/.git" ]; then
            print_status "Updating existing repository..."
            cd "$TARGET_DIR"
            
            # Fetch latest changes
            git fetch origin
            
            # Check if there are updates available
            LOCAL=$(git rev-parse HEAD)
            REMOTE=$(git rev-parse origin/main 2>/dev/null || git rev-parse origin/master 2>/dev/null)
            
            if [ "$LOCAL" = "$REMOTE" ]; then
                print_success "Repository is already up to date!"
            else
                print_status "Updates available, pulling latest changes..."
                git pull origin main 2>/dev/null || git pull origin master 2>/dev/null
                print_success "Repository updated successfully!"
            fi
        else
            print_warning "Directory exists but is not a git repository"
            print_status "Removing existing directory and cloning fresh..."
            rm -rf "$TARGET_DIR"
            clone_repository
        fi
    else
        clone_repository
    fi
}

# Clone the repository
clone_repository() {
    print_status "Cloning repository from $REPO_URL..."
    cd "$CUSTOM_NODES_DIR"
    
    if git clone "$REPO_URL" comfyui-nodes; then
        print_success "Repository cloned successfully to $TARGET_DIR"
    else
        print_error "Failed to clone repository"
        exit 1
    fi
}

# Install dependencies if requirements.txt exists
install_dependencies() {
    if [ -f "$TARGET_DIR/requirements.txt" ]; then
        print_status "Installing Python dependencies..."
        
        # Check if we're in a virtual environment or if pip is available
        if command -v pip &> /dev/null; then
            pip install -r "$TARGET_DIR/requirements.txt"
            print_success "Dependencies installed successfully!"
        elif command -v pip3 &> /dev/null; then
            pip3 install -r "$TARGET_DIR/requirements.txt"
            print_success "Dependencies installed successfully!"
        else
            print_warning "pip not found. Please install dependencies manually:"
            print_warning "pip install -r $TARGET_DIR/requirements.txt"
        fi
    else
        print_status "No requirements.txt found, skipping dependency installation"
    fi
}

# Main installation process
main() {
    print_status "Starting ComfyUI Nodes installation..."
    print_status "ComfyUI Directory: $COMFY_DIR"
    print_status "Target Directory: $TARGET_DIR"
    
    check_git
    check_comfyui_installation
    install_or_update
    install_dependencies
    
    print_success "Installation completed!"
    print_status "Please restart ComfyUI to load the new nodes."
    
    # Show some helpful information
    echo ""
    print_status "Installed nodes location: $TARGET_DIR"
    print_status "To uninstall, simply remove the directory: rm -rf $TARGET_DIR"
}

# Run the main function
main "$@"

#start comfyui now
cd $HOME/ComfyUI && source venv/bin/activate && python main.py --listen --enable-cors-header