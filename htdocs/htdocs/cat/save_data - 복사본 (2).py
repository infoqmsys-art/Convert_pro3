#!C:/Python311/python.exe
import sys
import json
import struct
import os
from datetime import datetime, timedelta
import requests
import logging

print("Content-Type: text/plain")
print()

def convert_timestamp(seconds_since_2000):
    base_date = datetime(2000, 1, 1, 0, 0, 0)
    target_date = base_date + timedelta(seconds=seconds_since_2000)
    kst_date = target_date + timedelta(hours=9)

    if kst_date.second >= 50:
        kst_date += timedelta(minutes=1)
        kst_date = kst_date.replace(second=0)
    elif kst_date.second < 10:
        kst_date = kst_date.replace(second=0)

    return kst_date.strftime("%Y-%m-%d %H:%M:%S")

def parse_status_bits(status):
    bits = f"{status:016b}"
    return {
        "Channel_7_sensor": int(bits[0]),
        "Channel_6_sensor": int(bits[1]),
        "Channel_5_sensor": int(bits[2]),
        "Channel_4_sensor": int(bits[3]),
        "Channel_3_sensor": int(bits[4]),
        "Channel_2_sensor": int(bits[5]),
        "Channel_1_sensor": int(bits[6]),
        "Channel_0_sensor": int(bits[7]),
        "Outside_temperature_status": int(bits[8]),
        "Inside_temperature_status": int(bits[9]),
        "Tilt_sensor_status": int(bits[10]),
        "Data_event_type": int(bits[11]),
        "Displacement_status": int(bits[12]),
        "Deep_sleep": int(bits[13]),
        "Battery_status": int(bits[14]),
        "Power_type": int(bits[15]),
    }

def append_to_csv(file_path, data_dict):
    if "timestamp" not in data_dict:
        raise KeyError("The key 'timestamp' is missing in the data dictionary.")

    reordered_data = {"timestamp": data_dict["timestamp"]}
    for key, value in data_dict.items():
        if key != "timestamp":
            reordered_data[key] = value

    file_exists = os.path.exists(file_path)
    with open(file_path, "a", encoding="utf-8") as csv_file:
        if not file_exists:
            csv_file.write(",".join(reordered_data.keys()) + "\n")
        csv_file.write(",".join(map(str, reordered_data.values())) + "\n")

data = sys.stdin.read()

try:
    json_data = json.loads(data)
    device_id = json_data.get("deviceId", "Unknown")
    hex_data = json_data.get("payload", "")
    if not hex_data:
        raise ValueError("Payload is missing or empty.")

    specific_line_number = 1231337210

    byte_data = bytes.fromhex(hex_data)
    if len(byte_data) < 220:
        byte_data = byte_data.ljust(220, b'\x00')

    payload_format = (
        "<4s I f I I I f f f f f f f f f f f f f f f f f f f f f f f f "
        "f f f f f f f f 48s I I f I 4s"
    )

    payload = struct.unpack(payload_format, byte_data)
    battery_level_bytes = byte_data[208:212]
    battery_level = struct.unpack('<f', battery_level_bytes)[0]

    parsed_data = {
        "deviceId": device_id,
        "STX": payload[0].decode(errors="ignore") if isinstance(payload[0], bytes) else str(payload[0]),
        "Length": payload[1],
        "ProtocolVersion": round(payload[2], 2),
        "lineNumber": payload[3],
        "intervalTimeSet": payload[4],
        "timestamp": convert_timestamp(payload[5]),
        "amplifierX": round(payload[6], 3),
        "amplifierY": round(payload[7], 3),
        "amplifierZ": round(payload[8], 3),
        "frequencyX": round(payload[9], 3),
        "frequencyY": round(payload[10], 3),
        "frequencyZ": round(payload[11], 3),
        "degreeXAmount": round(payload[12], 3),
        "degreeYAmount": round(payload[13], 3),
        "degreeZAmount": round(payload[14], 3),
        "AmountCH0": round(payload[15], 3),
        "AmountCH1": round(payload[16], 3),
        "AmountCH2": round(payload[17], 3),
        "AmountCH3": round(payload[18], 3),
        "AmountCH4": round(payload[19], 3),
        "AmountCH5": round(payload[20], 3),
        "AmountCH6": round(payload[21], 3),
        "AmountCH7": round(payload[22], 3),
        "initDegreeX": round(payload[23], 3),
        "initDegreeY": round(payload[24], 3),
        "initDegreeZ": round(payload[25], 3),
        "initCrack": round(payload[26], 3),
        "initCH1": round(payload[27], 3),
        "initCH2": round(payload[28], 3),
        "initCH3": round(payload[29], 3),
        "initCH4": round(payload[30], 3),
        "initCH5": round(payload[31], 3),
        "initCH6": round(payload[32], 3),
        "initCH7": round(payload[33], 3),
        "InsideTemperature": round(payload[34], 3),
        "InsideHumidity": round(payload[35], 3),
        "OutsideTemperature": round(payload[36], 3),
        "OutsideHumidity": round(payload[37], 3),
        "Reserve": payload[38].decode(errors="ignore") if isinstance(payload[38], bytes) else str(payload[38]),
        "status_bits": json.dumps(parse_status_bits(payload[39])),
        "batLevel": round(battery_level, 3),
        "CRC": payload[42],
        "ETX": payload[43].decode(errors="ignore") if isinstance(payload[43], bytes) else str(payload[43]),
    }

    line_number = parsed_data["lineNumber"]
    base_dir = "C:/cat/data"
    hex_dir = os.path.join(base_dir, "hex")
    temp_dir = os.path.join(base_dir, "temporary")
    csv_dir = os.path.join(base_dir, "csv", device_id)
    csv_file_path = os.path.join(csv_dir, f"{line_number}.csv")
    hex_file_path = os.path.join(hex_dir, f"{line_number}_hex.txt")
    temp_file_path = os.path.join(temp_dir, f"{line_number}_temp.txt")

    os.makedirs(hex_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(csv_dir, exist_ok=True)

    with open(hex_file_path, "a", encoding="utf-8") as hex_file:
        hex_file.write(f"{convert_timestamp(payload[5])}, {hex_data}\n")

    with open(temp_file_path, "w", encoding="utf-8") as temp_file:
        temp_file.write(json.dumps(parsed_data, indent=2))

    append_to_csv(csv_file_path, parsed_data)

    if line_number == specific_line_number:
        response_data = {
            "nid": str(specific_line_number),
            "sendPeriod": "10",
            "SlopeCalX": "1.05",
            "SlopeCalY": "1.05",
            "SlopeCalZ": "1.05",
            "reset": "0"
        }

        headers = {
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                'http://machine-server.local/api/receive_data',
                json=response_data,
                headers=headers
            )
            if response.status_code == 200:
                with open("response.txt", "a", encoding="utf-8") as log_file:
                    log_file.write(f"{datetime.now()} - Sent response to machine: {json.dumps(response_data, separators=(',', ':'))}\n")
                    log_file.write(f"{datetime.now()} - Machine response: {response.text}\n")
            else:
                with open("response.txt", "a", encoding="utf-8") as log_file:
                    log_file.write(f"{datetime.now()} - Failed to send response. Status code: {response.status_code}\n")
        except requests.exceptions.RequestException as e:
            with open("response.txt", "a", encoding="utf-8") as log_file:
                log_file.write(f"{datetime.now()} - Error sending response: {e}\n")

        print(f"Data saved to {csv_file_path}, {hex_file_path}, and {temp_file_path}")

except ValueError as ve:
    print(f"ValueError: {ve}")
except json.JSONDecodeError:
    print("Invalid JSON data received.")
except struct.error as e:
    print(f"Data unpacking error: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
