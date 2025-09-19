## ComfyUI Deploy API Routes

This document outlines the API routes available in the ComfyUI Deploy custom node.

### Tunnel Management

- **GET /tunnel/status**
  - **Description:** Retrieves the current status of the Cloudflare tunnel, including the URL, whether it's running, and the port it's connected to.
  - **Response:** JSON object with `success`, `url`, `running`, and `port` fields.

- **POST /comfyui-deploy/tunnel/start**
  - **Description:** Starts the Cloudflare tunnel, exposing the ComfyUI instance to the internet.
  - **Response:** JSON object indicating success or failure.

- **POST /comfyui-deploy/tunnel/stop**
  - **Description:** Stops the Cloudflare tunnel.
  - **Response:** JSON object indicating success or failure.

### Workflow Execution

- **POST /comfyui-deploy/run**
  - **Description:** Executes a workflow in a non-streaming fashion.
  - **Request Body:** JSON object containing the workflow and other parameters.
  - **Response:** JSON object with the execution result.

- **POST /comfyui-deploy/run/streaming**
  - **Description:** Executes a workflow in a streaming fashion, allowing for real-time updates.
  - **Request Body:** JSON object containing the workflow and other parameters.
  - **Response:** Streaming response with progress and results.

- **POST /comfyui-deploy/interrupt**
  - **Description:** Interrupts a running workflow execution.
  - **Response:** JSON object indicating success or failure.

### Model and File Management

- **GET /comfyui-deploy/models**
  - **Description:** Retrieves a list of available models.
  - **Response:** JSON array of model objects.

- **POST /comfyui-deploy/upload-file**
  - **Description:** Uploads a file to the server.
  - **Request Body:** Multipart form data with the file.
  - **Response:** JSON object with the file details.

- **GET /comfyui-deploy/get-file-hash**
  - **Description:** Retrieves the hash of a file.
  - **Query Parameters:** `filename`
  - **Response:** JSON object with the file hash.

- **GET /comfyui-deploy/filename_list_cache**
  - **Description:** Retrieves a cached list of filenames.
  - **Response:** JSON array of filenames.

- **GET /comfyui-deploy/upload-queue-status**
  - **Description:** Retrieves the status of the file upload queue.
  - **Response:** JSON object with the queue status.

- **POST /comfyui-deploy/cancel-uploads**
  - **Description:** Cancels all pending file uploads.
  - **Response:** JSON object indicating success or failure.

### WebSocket and Status

- **GET /comfyui-deploy/ws**
  - **Description:** Establishes a WebSocket connection for real-time communication.

- **GET /comfyui-deploy/check-status**
  - **Description:** Checks the status of the ComfyUI Deploy service.
  - **Response:** JSON object with the service status.

- **GET /comfyui-deploy/check-ws-status**
  - **Description:** Checks the status of the WebSocket connection.
  - **Response:** JSON object with the WebSocket status.

### Workflow Management

- **POST /comfyui-deploy/workflow**
  - **Description:** Creates or updates a workflow.
  - **Request Body:** JSON object containing the workflow data.
  - **Response:** JSON object with the workflow details.

- **POST /comfyui-deploy/workflow/version**
  - **Description:** Creates a new version of a workflow.
  - **Request Body:** JSON object with the workflow data and version information.
  - **Response:** JSON object with the new workflow version details.

- **GET /comfyui-deploy/workflows**
  - **Description:** Retrieves a list of all workflows.
  - **Response:** JSON array of workflow objects.

- **GET /comfyui-deploy/workflow**
  - **Description:** Retrieves a specific workflow.
  - **Query Parameters:** `workflow_id`
  - **Response:** JSON object with the workflow details.

- **GET /comfyui-deploy/workflow/versions**
  - **Description:** Retrieves all versions of a specific workflow.
  - **Query Parameters:** `workflow_id`
  - **Response:** JSON array of workflow version objects.

- **GET /comfyui-deploy/workflow/version**
  - **Description:** Retrieves a specific version of a workflow.
  - **Query Parameters:** `workflow_id`, `version`
  - **Response:** JSON object with the workflow version details.

- **POST /comfyui-deploy/workflow/convert**
  - **Description:** Converts a workflow to a different format.
  - **Request Body:** JSON object with the workflow data.
  - **Response:** JSON object with the converted workflow.

- **POST /comfyui-deploy/workflow/validate**
  - **Description:** Validates a workflow.
  - **Request Body:** JSON object with the workflow data.
  - **Response:** JSON object with the validation result.

### Machine Management

- **GET /comfyui-deploy/machine**
  - **Description:** Retrieves details about the current machine.
  - **Response:** JSON object with machine details.

- **POST /comfyui-deploy/machine/update**
  - **Description:** Updates the machine configuration.
  - **Request Body:** JSON object with the updated configuration.
  - **Response:** JSON object indicating success or failure.

- **POST /comfyui-deploy/machine/create**
  - **Description:** Creates a new machine.
  - **Request Body:** JSON object with the machine configuration.
  - **Response:** JSON object with the new machine details.

- **POST /comfyui-deploy/snapshot-to-docker**
  - **Description:** Creates a Docker snapshot of the current environment.
  - **Response:** JSON object indicating success or failure.

### Miscellaneous

- **GET /comfydeploy/{tail:.*}**
  - **Description:** Generic GET endpoint for ComfyDeploy.

- **POST /comfydeploy/{tail:.*}**
  - **Description:** Generic POST endpoint for ComfyDeploy.

- **GET /comfyui-deploy/auth-response**
  - **Description:** Handles the authentication response from the ComfyDeploy service.

- **GET /comfyui-deploy/comfyui-version**
  - **Description:** Retrieves the version of the ComfyUI instance.
  - **Response:** JSON object with the version number.

- **POST /comfyui-deploy/volume/model**
  - **Description:** Manages models on a volume.

- **GET /comfyui-deploy/fs/stat**
  - **Description:** Retrieves file system statistics.