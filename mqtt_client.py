import os
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
import threading
import time
import socket
import json
import math
import logging
logger = logging.getLogger("hailo_count")

load_dotenv("basic_pipelines/.env", override=True) 

class InitMQTTClient:
    def __init__(self, user_data):
        self.db = user_data.db
        self.device_status = user_data.device_status
        self.line_value = user_data.line_value
        self.region_line = user_data.region_line
        self.class_active = user_data.class_active
        self.image_screenshot_count = user_data.image_screenshot_count
        self.unacked_publish = user_data.unacked_publish
        self.id_type_to_class_name_coco = user_data.id_type_to_class_name_coco
        self.mqttBroker = os.getenv('MQTT_BROKER')
        self.mqttPort = int(os.getenv('MQTT_PORT'))
        self.mqttUser = os.getenv('MQTT_USER')
        self.mqttPass = os.getenv('MQTT_PASS')
        self.deviceId = os.getenv('DEVICE_ID')
        self.clientMqttId = f"vehicle-count-{self.deviceId}-client"
        self.loop_running = False
        self.subscribeTopic = [
            f"carcamera/subscribe/{self.deviceId}",
            f"carcamera/{self.deviceId}/screenshoot",
        ]

        self.client = mqtt.Client(
            transport='tcp',
            client_id=self.clientMqttId,
            clean_session=True,  
            protocol=mqtt.MQTTv311,
            userdata=self.unacked_publish,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
            )
        
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_publish = self.on_publish

        if self.connect_to_mqtt(): 
            self.client.loop_start() 
            # user_app_callback_class.write_log(self.log_path, "Connected to MQTT broker.")
            self.loop_running = True  
        else: 
            # print("Initial connection failed. Starting reconnect mechanism...") 
            pass

        self.reconnect_thread = threading.Thread( 
            target=self.reconnect_mqtt, 
            daemon=True 
        ) 
        self.reconnect_thread.start() 
    
    @staticmethod
    def calculate_points(x1, y1, x2, y2, o):
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        p1 = (int(round(x1 + nx * o)), int(round(y1 + ny * o)))
        p2 = (int(round(x2 + nx * o)), int(round(y2 + ny * o)))
        p3 = (int(round(x2 - nx * o)), int(round(y2 - ny * o)))
        p4 = (int(round(x1 - nx * o)), int(round(y1 - ny * o)))
        return p1, p2, p3, p4
 
    def connect_to_mqtt(self, max_retries=10):
        self.client.username_pw_set(self.mqttUser, self.mqttPass)
        count_connect = 0

        while count_connect < max_retries:
            try:
                # print(f"Attempting to connect to MQTT broker ({count_connect + 1}/{max_retries})...")
                logger.info(f"Attempting to connect to MQTT broker ({count_connect + 1}/{max_retries})...")
                self.client.connect(self.mqttBroker, self.mqttPort)
                # print("Successfully connected to MQTT broker.")
                logger.info("Successfully connected to MQTT broker.")
                return True
            except (socket.gaierror, ConnectionRefusedError, TimeoutError, OSError) as e:
                # print(f"Connection failed: {e}. Retrying in 5 seconds...")
                # user_app_callback_class.write_log(self.log_path, f"Connection failed: {e}. Retrying in 5 seconds...")
                count_connect += 1
                time.sleep(5)

        # print("Failed to connect after maximum retries.")
        return False
    
    def reconnect_mqtt(self):
        while True:
            if not self.client.is_connected():
                # print("MQTT client is not connected. Attempting to reconnect...") 
                logger.info("MQTT client is not connected. Attempting to reconnect...")
                # user_app_callback_class.write_log(self.log_path, "MQTT client is not connected. Attempting to reconnect...")
                if self.connect_to_mqtt():
                    # print("Reconnected successfully!") 
                    logger.info("Reconnected successfully!")
                    if not self.loop_running: 
                        self.client.loop_start() 
                        self.loop_running = True
                else: 
                    # print("Reconnection failed. Retrying...") 
                    logger.info("Reconnection failed. Retrying...")
                    # user_app_callback_class.write_log(self.log_path, "Reconnection failed. Retrying...")
            time.sleep(10) 

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            # print("Connected to MQTT broker.")  
            logger.info("Connected to MQTT broker.")
            for topic in self.subscribeTopic:
                client.subscribe(topic, qos=1)
            logger.info("Subscribed to topics successfully.")
        else:
            # print(f"Failed to connect with return code {rc}")
            logger.info(f"Failed to connect with return code {rc}")
    def on_message(self, client, userdata, message):
        payload = json.loads(message.payload.decode())
        topic = message.topic
        logger.info(f"Received message from topic: {topic}")
        if topic == f"carcamera/subscribe/{self.deviceId}": 
            if payload.get("action") == "carcamera_registered":
                # print(f"    Camera registered: ID={payload['id']}, Connection={payload['connection']}, Name={payload['name']}")
                logger.info(f"Camera registered: ID={payload['id']}, Connection={payload['connection']}, Name={payload['name']}")
                self.device_status["is_registered"] = True
                self.db.update_device_registration(self.deviceId, 1)

                if 'type_code' in payload:
                    self.db.clear_all_classes()
                    self.db.insert_multiple_classes(self, payload['type_code'])
                    self.class_active.clear()
                    self.class_active.extend(self.db.get_all_class_names())

            elif payload.get("action") == "config_line":
                # print(f"Received config_line action with data: {payload['data']}")
                logger.info(f"Received config_line action with data: {payload['data']}")
                temp_line_value = []
                temp_region_line = []
                for line in payload['data']:
                    point1, point2 = line['points']
                    x1, y1 = point1
                    x2, y2 = point2
                    self.db.insert_line(line['line_number'], int(x1), int(x2), int(y1), int(y2))
                    temp_line_value.append([(int(x1), int(y1)), (int(x2), int(y2))])
                    p1, p2, p3, p4 = InitMQTTClient.calculate_points(int(x1), int(y1), int(x2), int(y2), 50)
                    temp_region_line.append([p1, p2, p3, p4])

                self.line_value.clear()
                self.line_value.extend(temp_line_value)
                self.region_line.clear()
                self.region_line.extend(temp_region_line)
                self.image_screenshot_count['url'] = payload['url']      
                time.sleep(1)
                self.image_screenshot_count['flag'] = True   
        
        elif topic == f"carcamera/{self.deviceId}/screenshoot":
            # print(f"Camera Screenshoot Count: ID={payload['id']}, Url={payload['url']}")
            logger.info(f"Camera Screenshoot Count: ID={payload['id']}, Url={payload['url']}")
            self.image_screenshot_count['url'] = payload['url']      
            time.sleep(1)
            self.image_screenshot_count['flag'] = True

        elif topic == f"carcamera/config/{self.deviceId}": 
            if payload.get("action") == "carcamera_config_type":
                # print(f"Received carcamera_config_type action with data: {payload['type_code']}")
                logger.info(f"Received carcamera_config_type action with data: {payload['type_code']}")
                self.db.clear_all_classes()
                self.db.insert_multiple_classes(user_data, payload['type_code'])
                self.class_active.clear()
                self.class_active.extend(self.db.get_all_class_names())

    def on_publish(self, client, userdata, mid, reason_code=None, properties=None):
        try:
            userdata.discard(mid)
        except Exception as e:
            # print(f"Warning: Error in on_publish callback: {e}")
            logger.warning(f"Warning: Error in on_publish callback: {e}")


