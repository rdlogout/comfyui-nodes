import os
import requests
import aiohttp
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

BASE_URL = "https://fussion.studio"

def get_data(path):
    """
    Makes a GET request to the specified path.
    """
    machine_id = os.environ.get("MACHINE_ID")
    if not machine_id:
        logging.error("MACHINE_ID not found in environment variables.")
        return None

    headers = {
        "x-machine-id": machine_id
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
    machine_id = os.environ.get("MACHINE_ID")
    if not machine_id:
        logging.error("MACHINE_ID not found in environment variables.")
        return None

    headers = {
        "x-machine-id": machine_id
    }
    try:
        response = requests.post(f"{BASE_URL}/{path}", json=data_to_post, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred: {e}")
        return None

# Async versions for better performance with aiohttp
async def get_data_async(path, base_url=None):
    """
    Makes an async GET request to the specified path.
    """
    machine_id = os.environ.get("MACHINE_ID")
    if not machine_id:
        logging.error("MACHINE_ID not found in environment variables.")
        return None

    url = f"{(base_url or BASE_URL)}/{path}"
    headers = {
        "x-machine-id": machine_id
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                return await response.json()
    except aiohttp.ClientError as e:
        logging.error(f"An error occurred during async GET: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return None

async def post_data_async(path, data_to_post, base_url=None):
    """
    Makes an async POST request to the specified path with the given data.
    """
    machine_id = os.environ.get("MACHINE_ID")
    if not machine_id:
        logging.error("MACHINE_ID not found in environment variables.")
        return None

    url = f"{(base_url or BASE_URL)}/{path}"
    headers = {
        "x-machine-id": machine_id
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data_to_post, headers=headers) as response:
                response.raise_for_status()
                return await response.json()
    except aiohttp.ClientError as e:
        logging.error(f"An error occurred during async POST: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return None