#!C:/Users/메인3/AppData/Local/Programs/Python/Python311/python.exe
import sys
import json
import struct
import os
from datetime import datetime, timedelta

print("Content-Type: text/plain")
print()

# 타임스탬프 변환 함수
def convert_timestamp(seconds_since_2000):
    base_date = datetime(2000, 1, 1, 0, 0, 0)
    target_date = base_date + timedelta(seconds=seconds_since_2000)
    kst_date = target_date + timedelta(hours=9)
    return kst_date.strftime("%Y-%m-%d %H:%M:%S")

# 비트 상태를 해석하는 함수
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
    """
    데이터를 지정된 파일에 CSV 형식으로 누적 저장. timestamp를 맨 앞으로 이동.
    """
    if "timestamp" not in data_dict:
        raise KeyError("The key 'timestamp' is missing in the data dictionary.")

    # 'timestamp'를 맨 앞으로 이동한 데이터 생성
    reordered_data = {"timestamp": data_dict["timestamp"]}
    for key, value in data_dict.items():
        if key != "timestamp":
            reordered_data[key] = value

    file_exists = os.path.exists(file_path)
    with open(file_path, "a", encoding="utf-8") as csv_file:
        if not file_exists:
            # 헤더 추가
            csv_file.write(",".join(reordered_data.keys()) + "\n")
        # 데이터 추가
        csv_file.write(",".join(map(str, reordered_data.values())) + "\n")

# JSON 데이터 읽기
data = sys.stdin.read()

try:
    # JSON 데이터 파싱
    json_data = json.loads(data)
    device_id = json_data.get("deviceId", "Unknown")
    hex_data = json_data.get("payload", "")
    if not hex_data:
        raise ValueError("Payload is missing or empty.")

    # Payload를 바이트로 변환
    byte_data = bytes.fromhex(hex_data)

    # 데이터의 길이를 확인하고 220바이트로 맞추기
    if len(byte_data) < 220:
        byte_data = byte_data.ljust(220, b'\x00')

    # Payload_struct 형식 정의
    payload_format = (
        "<4s I f I I I f f f f f f f f f f f f f f f f f f f f f f f f "
        "f f f f f f f f 48s I I f I 4s"
    )

    # 데이터 파싱
    payload = struct.unpack(payload_format, byte_data)

    # 배터리 레벨 추출
    battery_level_bytes = byte_data[208:212]
    battery_level = struct.unpack('<f', battery_level_bytes)[0]

    # 필드 매핑
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
        "crackAmount": round(payload[15], 3),
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

    # 파일 저장 경로 설정
    line_number = parsed_data["lineNumber"]
    base_dir = "C:/cat/data"
    hex_dir = os.path.join(base_dir, "hex")
    temp_dir = os.path.join(base_dir, "temporary")
    json_file_path = os.path.join(base_dir, f"{line_number}.txt")
    hex_file_path = os.path.join(hex_dir, f"{line_number}_hex.txt")
    temp_file_path = os.path.join(temp_dir, f"{line_number}_temp.txt")
    csv_file_path = os.path.join(base_dir, f"{line_number}csv.txt")

    # 디렉토리가 없으면 생성
    os.makedirs(hex_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    # 데이터 JSON 형식으로 파일에 저장
    with open(json_file_path, "a", encoding="utf-8") as json_file:
        json_file.write(json.dumps(parsed_data, indent=2) + "\n$$$\n")

    # hex 파일에 timestamp와 hex 값을 누적하여 저장
    with open(hex_file_path, "a", encoding="utf-8") as hex_file:
        hex_file.write(f"{convert_timestamp(payload[5])}, {hex_data}\n")

    # 최신 값만 저장 (deviceId 포함)
    with open(temp_file_path, "w", encoding="utf-8") as temp_file:
        temp_file.write(json.dumps(parsed_data, indent=2))

    # CSV 파일에 누적 저장
    append_to_csv(csv_file_path, parsed_data)

    # 응답 메시지 출력
    print(f"Data saved to {json_file_path}, {hex_file_path}, {temp_file_path}, and {csv_file_path}")

except ValueError as ve:
    print(f"ValueError: {ve}")
except json.JSONDecodeError:
    print("Invalid JSON data received.")
except struct.error as e:
    print(f"Data unpacking error: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
