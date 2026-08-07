#!C:\Python\Python313\python.exe
import sys
import json
import struct
import os
from datetime import datetime, timedelta

print("Content-Type: text/plain")
print()

# 타임스탬프 변환 함수 (2000년 1월 1일을 기준으로 계산)
def convert_timestamp(seconds_since_2000):
    base_date = datetime(2000, 1, 1, 0, 0, 0)
    target_date = base_date + timedelta(seconds=seconds_since_2000)
    return target_date.strftime("%Y-%m-%d %H:%M:%S")

# JSON 데이터 읽기
data = sys.stdin.read()

try:
    # JSON 데이터 파싱
    json_data = json.loads(data)
    hex_data = json_data.get("payload", "")
    byte_data = bytes.fromhex(hex_data)

    # 데이터의 길이를 확인하고 128바이트로 맞추기
    if len(byte_data) < 128:
        byte_data += b'\x00' * (128 - len(byte_data))  # 부족한 경우 패딩 추가

    # Payload_struct 형식 정의
    payload_format = (
        "<4s I f I I I f f f f f f f f f f f f f f f f 20s I I f I 4s"
    )

    # 데이터 파싱
    payload = struct.unpack(payload_format, byte_data)

    # 필드 매핑
    parsed_data = {
        "STX": payload[0].decode(),
        "Length": payload[1],
        "Protocolversion": payload[2],
        "lineNumber": payload[3],
        "intervalTimeSet": payload[4],
        "timestamp": convert_timestamp(payload[5]),  # 타임스탬프 변환 적용
        "amplifierX": payload[6],
        "amplifierY": payload[7],
        "amplifierZ": payload[8],
        "frequencyX": payload[9],
        "frequencyY": payload[10],
        "frequencyZ": payload[11],
        "degreeXAmount": payload[12],
        "degreeYAmount": payload[13],
        "degreeZAmount": payload[14],
        "crackAmount": payload[15],
        "initDegreeX": payload[16],
        "initDegreeY": payload[17],
        "initDegreeZ": payload[18],
        "initCrack": payload[19],
        "temperature": payload[20],
        "humidity": payload[21],
        "Reserve": payload[22].decode(errors="ignore"),
        "Reserve_status": payload[23],
        "Status": payload[24],
        "batLevel": payload[25],
        "_CRC": payload[26],
        "ETX": payload[27].decode()
    }

    # 파일 저장 경로 설정
    line_number = parsed_data["lineNumber"]
    json_file_path = f"C:/cat/data/{line_number}.txt"
    hex_file_path = f"C:/cat/data/hex/{line_number}_hex.txt"
    temp_file_path = f"C:/cat/data/temporary/{line_number}_temp.txt"

    # 디렉토리가 없으면 생성
    os.makedirs(os.path.dirname(json_file_path), exist_ok=True)
    os.makedirs(os.path.dirname(hex_file_path), exist_ok=True)
    os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)

    # 데이터 JSON 형식으로 파일에 저장
    with open(json_file_path, "a") as json_file:  # 'a' 모드로 파일 열기
        json_file.write(json.dumps(parsed_data, indent=2) + "\n$$$\n")

    # hex 파일에 timestamp와 hex 값을 누적하여 저장
    with open(hex_file_path, "a") as hex_file:  # 'a' 모드로 파일 열기
        hex_file.write(f"{convert_timestamp(payload[5])}, {hex_data}\n")

    # 최신 값만 저장
    with open(temp_file_path, "w") as temp_file:  # 쓰기 모드로 파일 열기
        temp_file.write(json.dumps(parsed_data, indent=2))  # 최신 값을 저장

    # 응답 메시지 출력
    print(f"Data saved to {json_file_path}, {hex_file_path}, and {temp_file_path}")

except json.JSONDecodeError:
    print("Invalid JSON data received.")

except struct.error as e:
    print(f"Data unpacking error: {e}")

except Exception as e:
    print(f"An error occurred: {e}")
