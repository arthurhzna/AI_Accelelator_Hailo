from pathlib import Path
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import numpy as np
import cv2
import hailo
import json
from datetime import datetime, timedelta
from collections import defaultdict 
from dotenv import load_dotenv
import threading
import socket
import certifi
import paho.mqtt.client as mqtt
import time
import requests
import sqlite3
import math
import threading
import logging
from logging.handlers import TimedRotatingFileHandler
import re

log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
os.makedirs(log_dir, exist_ok=True)
today_str = datetime.now().strftime("%Y-%m-%d")
log_file_path = os.path.join(log_dir, f"{today_str}.txt")
logger = logging.getLogger("hailo_count")
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
formatter = logging.Formatter(
    "%(asctime)s %(levelname)s: %(message)s"
)
file_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(file_handler)

from hailo_apps.hailo_app_python.core.common.buffer_utils import get_caps_from_pad, get_numpy_from_buffer
from hailo_apps.hailo_app_python.core.gstreamer.gstreamer_app import app_callback_class
from hailo_apps.hailo_app_python.apps.detection.detection_pipeline import GStreamerDetectionApp
from database import InitDatabase
from mqtt_client import InitMQTTClient
from http_client import InitHTTPClient

load_dotenv("basic_pipelines/.env", override=True) 

class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        self.deviceId = os.getenv('DEVICE_ID')
        self.object_counter_RB = defaultdict(lambda: defaultdict(int))
        self.object_counter_BR = defaultdict(lambda: defaultdict(int))

        self.id_type_to_class_name_coco = {
            "0": "person", "1": "bicycle", "2": "car", "3": "motorcycle", "4": "airplane",
            "5": "bus", "6": "train", "7": "truck", "8": "boat", "9": "traffic light",
            "10": "fire hydrant", "11": "stop sign", "12": "parking meter", "13": "bench",
            "14": "bird", "15": "cat", "16": "dog", "17": "horse", "18": "sheep", "19": "cow",
            "20": "elephant", "21": "bear", "22": "zebra", "23": "giraffe", "24": "backpack",
            "25": "umbrella", "26": "handbag", "27": "tie", "28": "suitcase", "29": "frisbee",
            "30": "skis", "31": "snowboard", "32": "sports ball", "33": "kite",
            "34": "baseball bat", "35": "baseball glove", "36": "skateboard", "37": "surfboard",
            "38": "tennis racket", "39": "bottle", "40": "wine glass", "41": "cup",
            "42": "fork", "43": "knife", "44": "spoon", "45": "bowl", "46": "banana",
            "47": "apple", "48": "sandwich", "49": "orange", "50": "broccoli", "51": "carrot",
            "52": "hot dog", "53": "pizza", "54": "donut", "55": "cake", "56": "chair",
            "57": "couch", "58": "potted plant", "59": "bed", "60": "dining table",
            "61": "toilet", "62": "tv", "63": "laptop", "64": "mouse", "65": "remote",
            "66": "keyboard", "67": "cell phone", "68": "microwave", "69": "oven",
            "70": "toaster", "71": "sink", "72": "refrigerator", "73": "book", "74": "clock",
            "75": "vase", "76": "scissors", "77": "teddy bear", "78": "hair drier",
            "79": "toothbrush"
        }

        self.class_name_to_id_type_coco = {v: k for k, v in self.id_type_to_class_name_coco.items()}

        self.time_send_every_15_minutes = set()
        self.time_send_every_1_minutes = set()
        self.time_send_every_1_hour = set()

        self.executed_send_data_times_15_minutes = set()
        self.executed_send_data_times_1_minutes = set()
        self.executed_send_data_times_1_hour = set()

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.save_last_data_count_path = os.path.join(BASE_DIR, "save_data", "last_data_count.json")
        self.last_data_count = user_app_callback_class.load_data_from_json_file(self.save_last_data_count_path)
        # self.class_active = ["person", "motorcycle", "car", "truck", "bus"]
        # self.line_value = [ [(256,36),(383,431)], [(527,16),(553,223)]] #line_value = [[] for _ in range(MaxIteration)]

        self.position_history = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        self.current_position = defaultdict(lambda: defaultdict(lambda: defaultdict(str)))
        self.object_center_x = defaultdict(list)
        self.object_center_y = defaultdict(list)

        self.current_day = None
        self.last_day = None

        for hour in range(24): 
            # for minute in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59]: 
            for minute in [0, 15, 30, 45]:  
                self.time_send_every_15_minutes.add(f"{hour:02d}:{minute:02d}") 
        self.time_send_every_15_minutes.add("24:00")  

        for hour in range(24): 
            # for minute in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59]: 
            for minute in [0]: 
                self.time_send_every_1_hour.add(f"{hour:02d}:{minute:02d}")
        self.time_send_every_1_hour.add("24:00")

        for hour in range(24):
            for minute in range (60):
                self.time_send_every_1_minutes.add(f"{hour:02d}:{minute:02d}")

        self.db = InitDatabase('count.db')
        self.db.init_database()
        BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 
        self.screenshoot_count_path = os.path.join(BASE_DIR, "dynamic/screenshoot/count/screenshot_count.jpg")

        self.device_status = {
            "is_registered": self.db.get_device_info_formatted(self.deviceId)
        }
        if self.device_status["is_registered"] is None:
            print("Device Not Found")
            self.db.insert_device_info(self.deviceId, is_registered=0)
            self.device_status["is_registered"] = False

        # print(f"device status {self.device_status['is_registered']}")   

        self.line_value = self.db.get_all_lines_formatted() 
        print(print(f"lines_value {self.line_value}"))
        self.region_line = [] # [ [(256,36), (383,431), (383,431), (383,431)], [(256,36), (383,431), (383,431), (383,431)]]
        for line in self.line_value:
            p1, p2, p3, p4 = user_app_callback_class.calculate_points(line[0][0], line[0][1], line[1][0], line[1][1], 50)
            self.region_line.append([p1, p2, p3, p4])

        self.counted_object_RB = defaultdict(lambda: defaultdict(set))
        self.counted_object_BR = defaultdict(lambda: defaultdict(set))
        self.class_active = []
        self.class_active = self.db.get_all_class_names()
        print(print(f"class_active {self.class_active}"))

        self.image_screenshot_count = {
            "url": None,
            "flag": False
        }

        self.unacked_publish = set()

        self.mqtt_client = InitMQTTClient(self)
        
        self.http_client = InitHTTPClient()

        self.update_counter_with_class(self)

    @staticmethod
    def update_counter_with_class(user_data):

        if not user_data.load_data:
            return

        if 'RB' in user_data.load_data:
            for line_num in range(len(user_data.line_value)):
                line_key = f"line{line_num + 1}"
                if line_key in user_data.load_data['RB']:
                    for class_id, count in user_data.load_data['RB'][line_key].items():
                        if count > 0 and class_id in user_data.id_type_to_class_name_coco:  
                            class_name = user_data.id_type_to_class_name_coco[class_id]  
                            user_data.object_counter_RB[line_num][class_name] = count
    
        if 'BR' in user_data.load_data:
            for line_num in range(len(user_data.line_value)):
                line_key = f"line{line_num + 1}"
                if line_key in user_data.load_data['BR']:
                    for class_id, count in user_data.load_data['BR'][line_key].items():
                        if count > 0 and class_id in user_data.id_type_to_class_name_coco:  
                            class_name = user_data.id_type_to_class_name_coco[class_id]  
                            user_data.object_counter_BR[line_num][class_name] = count

    @staticmethod
    def calculate_points(x1, y1, x2, y2, o):
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0

        nx = -dy / length
        ny = dx / length

        p1 = (x1 + nx * o, y1 + ny * o)
        p2 = (x2 + nx * o, y2 + ny * o)
        p3 = (x2 - nx * o, y2 - ny * o)
        p4 = (x1 - nx * o, y1 - ny * o)

        return (int(round(p1[0])), int(round(p1[1]))), \
            (int(round(p2[0])), int(round(p2[1]))), \
            (int(round(p3[0])), int(round(p3[1]))), \
            (int(round(p4[0])), int(round(p4[1])))

    @staticmethod
    def wait_status(msg_info, timeout=0.5):
        try:
            msg_info.wait_for_publish(timeout=timeout)
            return msg_info.is_published()
        except Exception as e:
            print("Error saat publish:", e)
            return False

    # @staticmethod
    # def load_data_from_json_file(filename):
    #     try:
    #         with open(filename, 'r') as file:
    #             data = json.load(file)
    #         return data
    #     except FileNotFoundError:
    #         print("No saved data found. Starting fresh.")
    #         return None

    @staticmethod
    def load_data_from_json_file(filename):
        try:
            if not os.path.exists(filename):
                print("JSON file not found. Starting fresh.")
                return None

            if os.path.getsize(filename) == 0:
                print("JSON file is empty. Starting fresh.")
                return None

            with open(filename, 'r') as file:
                return json.load(file)

        except json.JSONDecodeError as e:
            print(f"Invalid JSON format: {e}. Starting fresh.")
            return None

        except Exception as e:
            print(f"Unexpected error while loading JSON: {e}")
            return None
        
    @staticmethod
    def save_last_data_count_to_json(user_data):
        
        data = {
            "RB": {},
            "BR": {}
        }
        
        for line_num in range(len(user_data.line_value)):
            line_key = f"line{line_num + 1}"
            data["RB"][line_key] = {}
            data["BR"][line_key] = {}
            
            for class_id in range(80):
                data["RB"][line_key][str(class_id)] = 0
                data["BR"][line_key][str(class_id)] = 0
            
            if line_num in user_data.object_counter_RB:
                for class_name, count in user_data.object_counter_RB[line_num].items():
                    class_id = user_data.class_name_to_id_type_coco.get(class_name)
                    if class_id:
                        data["RB"][line_key][class_id] = count
            
            if line_num in user_data.object_counter_BR:
                for class_name, count in user_data.object_counter_BR[line_num].items():
                    class_id = user_data.class_name_to_id_type_coco.get(class_name)
                    if class_id:
                        data["BR"][line_key][class_id] = count
        
        try:
            with open(user_data.save_last_data_count_path, 'w') as file:
                json.dump(data, file)
        except Exception as e:
            print(f"❌ Error saat menyimpan data: {e}")
    
    @staticmethod
    def draw_line_and_regions(img, img_count, image_coordinates_list):
        H, W = img.shape[:2]
        
        m_list = []
        c_list = []
        
        for i, coordinates in enumerate(image_coordinates_list, 1):
            if len(coordinates) >= 2:
                x1, y1 = coordinates[0]
                x2, y2 = coordinates[1]

                if x1 != x2:
                    m = (y2 - y1) / (x2 - x1)
                else:
                    x2 += 1
                    m = (y2 - y1) / (x2 - x1)
                c = y1 - m * x1
                
                cv2.line(img, (x1, y1), (x2, y2), (0, 255, 255), 2)
                cv2.line(img_count, (x1, y1), (x2, y2), (0, 255, 255), 2)

                mid_x = int((x1 + x2) / 2)
                mid_y = int((y1 + y2) / 2)

                cv2.putText(img, f"{i}", (mid_x, mid_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                cv2.putText(img_count, f"{i}", (mid_x, mid_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

                blue_text = f"B {i}"
                red_text = f"R {i}"

                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.5
                thickness = 2
                
                (text_width_blue, text_height_blue), _ = cv2.getTextSize(blue_text, font, font_scale, thickness)
                (text_width_red, text_height_red), _ = cv2.getTextSize(red_text, font, font_scale, thickness)
                
                if m <= -2 or (-2 < m < -1) or (1 <= m < 2) or (m >= 2):
                    # mid_x_1 = int((mid_x + 640) / 2) 
                    # mid_x_2 = int((mid_x + 0) / 2)

                    mid_x_1 = mid_x + 50
                    mid_x_2 = mid_x - 50

                    if m <= -2 or (-2 < m < -1):
                        red_x = mid_x_1 - text_width_blue // 2
                        blue_x = mid_x_2 - text_width_red // 2
                    elif (1 <= m < 2) or (m >= 2):
                        blue_x = mid_x_1 - text_width_blue // 2
                        red_x = mid_x_2 - text_width_red // 2
                    #
                    cv2.putText(img, blue_text, (blue_x, mid_y), 
                            font, font_scale, (0, 0, 255), thickness)
                    cv2.putText(img, red_text, (red_x, mid_y), 
                            font, font_scale, (255, 0, 0), thickness)
                    cv2.putText(img_count, blue_text, (blue_x, mid_y), 
                            font, font_scale, (0, 0, 255), thickness)
                    cv2.putText(img_count, red_text, (red_x, mid_y), 
                            font, font_scale, (255, 0, 0), thickness)
                    
                elif (-1 <= m < 0) or (0 <= m < 1):
                    # mid_y_1 = int((mid_y + 480) / 2)  
                    # mid_y_2 = int((mid_y + 0) / 2)   

                    mid_y_1 = mid_y + 50
                    mid_y_2 = mid_y - 50
                    
                    blue_x = mid_x - text_width_blue // 2
                    red_x = mid_x - text_width_red // 2

                    cv2.putText(img, blue_text, (blue_x, mid_y_2), 
                            font, font_scale, (0, 0, 255), thickness)
                    cv2.putText(img, red_text, (red_x, mid_y_1), 
                            font, font_scale, (255, 0, 0), thickness)
                    
                    cv2.putText(img_count, blue_text, (blue_x, mid_y_2), 
                            font, font_scale, (255, 0, 0), thickness)
                    cv2.putText(img_count, red_text, (red_x, mid_y_1), 
                            font, font_scale, (0, 0, 255), thickness) 
          
                m_list.append(m)
                c_list.append(c)
            else:
                m_list.append(0)
                c_list.append(0)
        
        return m_list, c_list
    
    @staticmethod
    def send_mqtt_payload(client, topic, payload, qos=1):
        payload_json = json.dumps(payload)
        result = client.publish(topic, payload_json, qos=qos)
        return result

    @staticmethod
    def send_data_device_status_mqtt(user_data):
        payload = {
            "action": "device_status",
            "data": {
                "id": user_data.deviceId,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }
        print(payload)
        user_app_callback_class.send_mqtt_payload(user_data.mqtt_client.client, "carcamera/publish", payload)

    @staticmethod
    def send_data_device_registration_mqtt(user_data):
        payload = {
            "action": "new_carcamera",
            "data": {
                "id": user_data.deviceId,
                "connection": "LAN"
            }
        }
        print(payload)
        user_app_callback_class.send_mqtt_payload(user_data.mqtt_client.client, "carcamera/publish", payload)
    
    @staticmethod
    def parsing_imp_data_line_count(user_data):

        lines_data = []

        for line in range (len(user_data.line_value)):

            types_data = []

            all_classes = set()
            if line in user_data.object_counter_RB:
                all_classes.update(user_data.object_counter_RB[line].keys())
            if line in user_data.object_counter_BR:
                all_classes.update(user_data.object_counter_BR[line].keys())
            
            for class_name in all_classes:
                type_id = user_data.class_name_to_id_type_coco.get(class_name, "unknown")
                rb_count = user_data.object_counter_RB[line].get(class_name, 0)
                br_count = user_data.object_counter_BR[line].get(class_name, 0)
                
                if rb_count > 0 or br_count > 0:
                    types_data.append({
                        "type_id": type_id,
                        "rb": rb_count,
                        "br": br_count
                    })

            if types_data:
                lines_data.append({
                    "line": line + 1, 
                    "types": types_data
                })

        return lines_data
    
    @staticmethod
    def save_data_line_count_to_db(user_data, lines_data, timestamp=None, is_send=0):
        if timestamp is None:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        inserted_ids = []
        for line_data in lines_data:
            line_number = line_data["line"]
            
            for type_data in line_data["types"]:
                type_id = type_data["type_id"]
                rb_count = type_data["rb"]
                br_count = type_data["br"]
                
                id = user_data.db.insert_impression(
                    line_number=line_number,
                    type_val=type_id,
                    rb=rb_count,
                    br=br_count,
                    time_stamp=timestamp,
                    is_send=is_send
                )
                inserted_ids.append(id)
                print(f"Impression ID {id} berhasil disimpan")
        return inserted_ids

    @staticmethod
    def mark_impression_as_sent_by_ids(inserted_ids):
        if not inserted_ids:
            return
        for id in inserted_ids:
            if id is not None:
                user_data.db.mark_impression_as_sent(id)

    @staticmethod
    def send_data_line_count_mqtt(user_data):
        lines_data = user_app_callback_class.parsing_imp_data_line_count(user_data)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "action": "send_data_count",
            "data": {
                "id": user_data.deviceId,
                "lines": lines_data,
                "timestamp": timestamp
            }
        }
        print(payload)
        logger.info(f"Sending data line count to MQTT: {payload}")
        result = user_app_callback_class.send_mqtt_payload(user_data.mqtt_client.client, "carcamera/publish", payload)
        logger.info("send_data_line_count_mqtt() returned result: %s", result)
        inserted_ids = user_app_callback_class.save_data_line_count_to_db(user_data, lines_data, timestamp, 0)
        if result is None:
            print("Publish did not return result object; will keep impressions pending")
            logger.warning("Publish did not return result object; will keep impressions pending")
            return
        user_data.unacked_publish.add(result.mid)
        ok = user_app_callback_class.wait_status(result, timeout=5)
        if ok:
            logger.info("Publish acked; marking impressions as sent")
            user_app_callback_class.mark_impression_as_sent_by_ids(inserted_ids)
        else:
            print("Publish not acked; impressions remain pending for retry")
            logger.info("Publish not acked; impressions remain pending for retry")

    @staticmethod
    def threading_send_data_to_mqtt_schedule(user_data, current_time):
        user_app_callback_class.send_data_to_mqtt_schedule(user_data, current_time)


    @staticmethod
    def resend_data_line_count_mqtt(user_data):
        rows = user_data.db.get_pending_impressions()
        if rows is not None:
            grouped = defaultdict(list)
            for r in rows:
                ts = r[5]
                grouped[ts].append(r)

            for ts, imps in grouped.items():
                lines_by_line = defaultdict(list)
                impression_ids = []
                for imp in imps:
                    imp_id, line_number, type_val, rb, br, time_stamp, is_send = imp
                    impression_ids.append(imp_id)
                    lines_by_line[line_number].append({
                        "type_id": type_val,
                        "rb": rb,
                        "br": br
                    })

                lines = []
                for line_num, types in lines_by_line.items():
                    lines.append({
                        "line": line_num,
                        "types": types
                    })

                payload = {
                    "action": "send_data_count",
                    "data": {
                        "id": user_data.deviceId,
                        "lines": lines,
                        "timestamp": ts
                    }
                }

                print(f"Resending {len(impression_ids)} impressions for timestamp {ts} ...")
                ok = user_app_callback_class.send_mqtt_payload(user_data.mqtt_client.client, "carcamera/publish", payload)
                if ok:
                    for id in impression_ids:
                        user_data.db.mark_impression_as_sent(id)
                    logger.info(f"Marked {impression_ids} impressions as sent")
                else:
                    print(f"Failed to send batch for {ts}; will retry later")
                    logger.warning(f"Failed to send batch for {ts}; will retry later")


    @staticmethod
    def reset_all_counters(user_data):
        user_data.object_counter_RB = defaultdict(lambda: defaultdict(int))
        user_data.object_counter_BR = defaultdict(lambda: defaultdict(int))
        
        user_data.counted_object_RB = defaultdict(lambda: defaultdict(set))
        user_data.counted_object_BR = defaultdict(lambda: defaultdict(set))
        
        user_data.position_history = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        user_data.current_position = defaultdict(lambda: defaultdict(lambda: defaultdict(str)))
        user_data.object_center_x = defaultdict(list)
        user_data.object_center_y = defaultdict(list)

    @staticmethod
    def send_data_to_mqtt_schedule(user_data, current_time):
        # logger.debug("Schedule check at %s", current_time)
        try:
            if user_data.device_status["is_registered"] is False:
                logger.info("Device not registered — sending registration at %s", current_time)
                user_data.send_data_device_registration_mqtt(user_data)
            else:
                logger.info("Device registered — sending heartbeat/status at %s", current_time)
                user_data.send_data_device_status_mqtt(user_data)
        except Exception as e:
            logger.exception("Error sending device status/registration: %s", e)

        if current_time in user_data.time_send_every_15_minutes and current_time not in user_data.executed_send_data_times_15_minutes:
            user_data.executed_send_data_times_15_minutes.add(current_time)
            logger.info("15-min slot triggered: %s", current_time)
            # user_data.send_data_to_mqtt()
            pass

        if current_time in user_data.time_send_every_1_hour and current_time not in user_data.executed_send_data_times_1_hour:
            user_data.executed_send_data_times_1_hour.add(current_time)
            logger.info("Hourly send triggered: %s", current_time)

            try:
                logger.info("Sending line count to MQTT (hourly) at %s", current_time)
                user_data.send_data_line_count_mqtt(user_data)
                logger.info("send_data_line_count_mqtt() returned")
            except Exception as e:
                logger.exception("Error during send_data_line_count_mqtt: %s", e)

            try:
                user_app_callback_class.reset_all_counters(user_data)
                logger.info("Counters reset after hourly send")
            except Exception as e:
                logger.exception("Error resetting counters: %s", e)

            try:
                logger.info("Attempting resend of pending impressions after hourly send")
                user_app_callback_class.resend_data_line_count_mqtt(user_data)
            except Exception as e:
                logger.exception("Error during resend_data_line_count_mqtt: %s", e)

    @staticmethod
    def draw_square(frame, square_points, color, number_of_lines, type="Area"):
        for i in range(number_of_lines):
            if len(square_points[i]) == 4:
                sorted_points = user_app_callback_class.sort_points_clockwise(square_points[i])
                A, B, C, D = sorted_points

                cv2.line(frame, A, B, color, 2)
                cv2.line(frame, B, C, color, 2)
                cv2.line(frame, C, D, color, 2)
                cv2.line(frame, D, A, color, 2)

                center_x = int((A[0] + B[0] + C[0] + D[0]) / 4)
                center_y = int((A[1] + B[1] + C[1] + D[1]) / 4)
                
                cv2.putText(frame, f"{type}{i+1}", 
                        (center_x - 19, center_y - 19),  
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        0.5, 
                        (255, 255, 255),  
                        2, 
                        cv2.LINE_AA)
                
                cv2.putText(frame, f"{type}{i+1}", 
                        (center_x - 20, center_y - 20),  
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        0.5, 
                        (0, 0, 255),  
                        2, 
                        cv2.LINE_AA)
    
    @staticmethod
    def sort_points_clockwise(points):
        center_x = np.mean([p[0] for p in points])
        center_y = np.mean([p[1] for p in points])

        def angle_from_center(point):
            dx = point[0] - center_x
            dy = point[1] - center_y
            return np.arctan2(dy, dx)

        sorted_points = sorted(points, key=angle_from_center, reverse=True)
        return sorted_points
    
    @staticmethod
    def is_point_in_square(square_points, point):
        square_points = user_app_callback_class.sort_points_clockwise(square_points)
        A, B, C, D = square_points
        P = point

        def cross_product(v1, v2):
            return v1[0] * v2[1] - v1[1] * v2[0]

        AB = (B[0] - A[0], B[1] - A[1])
        AP = (P[0] - A[0], P[1] - A[1])
        cross_AB_AP = cross_product(AB, AP)

        BC = (C[0] - B[0], C[1] - B[1])
        BP = (P[0] - B[0], P[1] - B[1])
        cross_BC_BP = cross_product(BC, BP)

        CD = (D[0] - C[0], D[1] - C[1])
        CP = (P[0] - C[0], P[1] - C[1])
        cross_CD_CP = cross_product(CD, CP)

        DA = (A[0] - D[0], A[1] - D[1])
        DP = (P[0] - D[0], P[1] - D[1])
        cross_DA_DP = cross_product(DA, DP)

        return (cross_AB_AP >= 0 and cross_BC_BP >= 0 and cross_CD_CP >= 0 and cross_DA_DP >= 0) or \
                (cross_AB_AP <= 0 and cross_BC_BP <= 0 and cross_CD_CP <= 0 and cross_DA_DP <= 0)

def app_callback(pad, info, user_data):

    user_data.current_day = datetime.now().day 

    if user_data.current_day != user_data.last_day:  
        user_data.executed_send_data_times_1_hour.clear()
        user_data.executed_send_data_times_1_minutes.clear()
        user_data.executed_send_data_times_15_minutes.clear()
        user_data.last_day = user_data.current_day  

    current_time = datetime.now().strftime("%H:%M")
    if current_time in user_data.time_send_every_1_minutes and current_time not in user_data.executed_send_data_times_1_minutes:
        user_data.executed_send_data_times_1_minutes.add(current_time)
        thread_send_data = threading.Thread(
            target=user_app_callback_class.threading_send_data_to_mqtt_schedule,
            args=(user_data, current_time,)  
        )
        thread_send_data.start()

    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK
    user_data.increment()
    format, width, height = get_caps_from_pad(pad)

    frame = None
    if user_data.use_frame and format is not None and width is not None and height is not None:
    
        frame = get_numpy_from_buffer(buffer, format, width, height)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        user_data.set_frame(frame)
        frame_line_count = frame.copy()
        frame_line_count = cv2.cvtColor(frame_line_count, cv2.COLOR_RGB2BGR)

    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    m_list, c_list = user_app_callback_class.draw_line_and_regions(frame,frame_line_count, user_data.line_value)
    user_app_callback_class.draw_square(frame, user_data.region_line, (0, 255, 0), len(user_data.region_line))
    for detection in detections:
        label = detection.get_label()
        bbox = detection.get_bbox()
        confidence = detection.get_confidence()

        for class_active in user_data.class_active:
            if label == class_active:
                track_id = 0
                track = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
                if len(track) == 1:
                    track_id = track[0].get_id()
                
                if user_data.use_frame and frame is not None:
                    xmin = int(bbox.xmin() * frame.shape[1])
                    ymin = int(bbox.ymin() * frame.shape[0])
                    xmax = int(bbox.xmax() * frame.shape[1])
                    ymax = int(bbox.ymax() * frame.shape[0])

                    centroid = ((xmin + xmax) // 2, (ymin + ymax) // 2)

                    user_data.object_center_x[track_id].append(centroid[0])
                    user_data.object_center_y[track_id].append(centroid[1])

                    cv2.circle(frame, centroid, 4, (0, 0, 255), -1)

                    cv2.putText(frame, f"ID: {track_id}", (centroid[0] - 30, centroid[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)

                    if len(user_data.object_center_y[track_id]) >= 2:
                        for i in range(len(user_data.line_value)):
                            result = user_app_callback_class.is_point_in_square(user_data.region_line[i], centroid)
                            if result:
                                if centroid[1] >= (m_list[i] * centroid[0] + c_list[i]):
                                    user_data.current_position[i][track_id][label] = "red"
                                elif centroid[1] <= (m_list[i] * centroid[0] + c_list[i]):
                                    user_data.current_position[i][track_id][label] = "blue"
                                if not user_data.position_history[i][track_id][label] or user_data.position_history[i][track_id][label][-1] != user_data.current_position[i][track_id][label]:
                                    user_data.position_history[i][track_id][label].append(user_data.current_position[i][track_id][label])
                                if len(user_data.position_history[i][track_id][label]) >= 2:
                                    if track_id not in user_data.counted_object_RB[i][label] and track_id not in user_data.counted_object_BR[i][label]:
                                        if "red" in user_data.position_history[i][track_id][label] and "blue" in user_data.position_history[i][track_id][label]:
                                            if user_data.position_history[i][track_id][label].index("red") < user_data.position_history[i][track_id][label].index("blue"):
                                                user_data.object_counter_RB[i][label] += 1
                                                user_data.counted_object_RB[i][label].add(track_id)
                                            elif user_data.position_history[i][track_id][label].index("blue") < user_data.position_history[i][track_id][label].index("red"):
                                                user_data.object_counter_BR[i][label] += 1
                                                user_data.counted_object_BR[i][label].add(track_id)

                                    if (track_id in user_data.counted_object_RB[i][label] or track_id in user_data.counted_object_BR[i][label]) and \
                                    len(user_data.position_history[i][track_id][label]) >= 2 and \
                                    (user_data.position_history[i][track_id][label][-2:] == ["red", "blue"] or 
                                        user_data.position_history[i][track_id][label][-2:] == ["blue", "red"]):
                                        if track_id in user_data.counted_object_RB[i][label]:
                                            user_data.counted_object_RB[i][label].remove(track_id)
                                        if track_id in user_data.counted_object_BR[i][label]:
                                            user_data.counted_object_BR[i][label].remove(track_id)
                                        user_data.position_history[i][track_id][label] = []
                    
    for i in range(len(user_data.line_value)):
        y_offset = 120
        for class_name in user_data.object_counter_RB[i].keys():
            cv2.putText(frame, f"Line {i+1} {class_name} R-B: {user_data.object_counter_RB[i][class_name]}", 
                        (10, y_offset + i*40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
            cv2.putText(frame, f"Line {i+1} {class_name} B-R: {user_data.object_counter_BR[i][class_name]}", 
                        (10, y_offset + 20 + i*40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            y_offset += 40

    if user_data.image_screenshot_count["flag"]:
        user_data.http_client.send_screenshot(user_data, frame_line_count)
        user_data.image_screenshot_count["flag"] = False

    user_app_callback_class.save_last_data_count_to_json(user_data)

    return Gst.PadProbeReturn.OK

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    env_file     = project_root / ".env"
    env_path_str = str(env_file)
    os.environ["HAILO_ENV_FILE"] = env_path_str

    user_data = user_app_callback_class()
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()
