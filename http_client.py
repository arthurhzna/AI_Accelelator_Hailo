import requests
import cv2
import socket
import os
import threading
from dotenv import load_dotenv

class InitHTTPClient:
    
    def __init__(self):
        load_dotenv("basic_pipelines/.env", override=True) 
        self.authorization_token = os.getenv('AUTHORIZATION_TOKEN')
    
    def send_screenshot(self, user_data, frame):
        # print(user_data.screenshoot_count_path)
        cv2.imwrite(user_data.screenshoot_count_path, frame)

        headers = {
            "Authorization": self.authorization_token
        }
        
        files = {
            "file": open(user_data.screenshoot_count_path, "rb"),
        }
        
        data = {
            "id": user_data.deviceId
        }
        
        try:
            response = requests.post(user_data.image_screenshot_count["url"], headers=headers, files=files, data=data)
            # print(response.status_code)
            files["file"].close()
            response_json = response.json()
            # print(response_json)
            return response_json
            
        except socket.gaierror as e:
            # print(f"Network error occurred while sending: {e}")
            return None
        except requests.exceptions.RequestException as e:
            # print(f"Request failed: {e}")
            return None
        except Exception as e:
            # print(f"An unexpected error occurred: {e}")
            return None