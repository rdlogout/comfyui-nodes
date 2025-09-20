import os
import requests
import logging

logging.basicConfig(level=logging.INFO)

BASE_URL = "https://fussion.studio"
MACHINE_ID = os.environ.get("MACHINE_ID")

def get_data(path):
    """
    Makes a GET request to the specified path.
    """
    if not MACHINE_ID:
        logging.error("MACHINE_ID not found in environment variables.")
        return None

    headers = {
        "x-machine-id": MACHINE_ID
    }
    try:
        response = requests.get(f"{BASE_URL}/{path}", headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred: {e}")
        return None

def post_data(path, data_to_post):
    """
    Makes a POST request to the specified path with the given data.
    """
    if not MACHINE_ID:
        logging.error("MACHINE_ID not found in environment variables.")
        return None

    headers = {
        "x-machine-id": MACHINE_ID
    }
    try:
        response = requests.post(f"{BASE_URL}/{path}", json=data_to_post, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred: {e}")
        return None