#!C:/Users/메인3/AppData/Local/Programs/Python/Python311/python.exe

import os
import cgi
import json
import struct
from datetime import datetime, timedelta

print("Content-Type: text/html")
print()

# 타임스탬프 변환 함수
def convert_timestamp(seconds_since_2000):
    base_date = datetime(2000, 1, 1, 0, 0, 0)
    target_date = base_date + timedelta(seconds=seconds_since_2000)
    kst_date = target_date + timedelta(hours=9)  # 한국시간(KST)
    return kst_date.strftime("%Y-%m-%d %H:%M:%S")

# JSON 데이터 읽기
form = cgi.FieldStorage()
data = form.getvalue("payload")

if data:
    try:
        payload_hex = data
        byte_data = bytes.fromhex(payload_hex)

        # 구조체 포맷 정의 (220바이트)
        payload_format = (
            "<4s I f I I I f f f f f f f f f f f f f f f f f f f f f "
            "f f f f f f f f f f f f f f f f 4s"
        )

        # 데이터 파싱
        payload = struct.unpack(payload_format, byte_data)

        parsed_data = {
            "STX": payload[0].decode(errors="ignore"),
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
            "AmountCH1": round(payload[15], 3),
            "AmountCH2": round(payload[16], 3),
            "AmountCH3": round(payload[17], 3),
            "AmountCH4": round(payload[18], 3),
            "AmountCH5": round(payload[19], 3),
            "AmountCH6": round(payload[20], 3),
            "AmountCH7": round(payload[21], 3),
            "AmountCH8": round(payload[22], 3),
            "initDegreeX": round(payload[23], 3),
            "initDegreeY": round(payload[24], 3),
            "initDegreeZ": round(payload[25], 3),
            "initCH1": round(payload[26], 3),
            "initCH2": round(payload[27], 3),
            "initCH3": round(payload[28], 3),
            "initCH4": round(payload[29], 3),
            "initCH5": round(payload[30], 3),
            "initCH6": round(payload[31], 3),
            "initCH7": round(payload[32], 3),
            "initCH8": round(payload[33], 3),
            "InsideTemperature": round(payload[34], 3),
            "InsideHumidity": round(payload[35], 3),
            "OutsideTemperature": round(payload[36], 3),
            "OutsideHumidity": round(payload[37], 3),
            "Reserve": payload[38].decode(errors="ignore"),
            "batLevel": round(payload[40], 2),
            "CRC": payload[41],
            "ETX": payload[42].decode(errors="ignore"),
        }

        # 파일 저장 경로 설정
        line_number = parsed_data["lineNumber"]
        base_dir = "C:/cat/data"
        json_file_path = os.path.join(base_dir, f"{line_number}.txt")
        hex_file_path = os.path.join(base_dir, "hex", f"{line_number}_hex.txt")
        temp_file_path = os.path.join(base_dir, "temporary", f"{line_number}_temp.txt")

        # 디렉토리가 없으면 생성
        os.makedirs(os.path.dirname(json_file_path), exist_ok=True)
        os.makedirs(os.path.dirname(hex_file_path), exist_ok=True)
        os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)

        # JSON 형식으로 파일에 저장
        with open(json_file_path, "a") as json_file:
            json_file.write(json.dumps(parsed_data, indent=2) + "\n$$$\n")

        # hex 파일에 timestamp와 hex 값을 누적하여 저장
        with open(hex_file_path, "a") as hex_file:
            hex_file.write(f"{convert_timestamp(payload[5])}, {payload_hex}\n")

        # 최신 값만 저장
        with open(temp_file_path, "w") as temp_file:
            temp_file.write(json.dumps(parsed_data, indent=2))

        # 응답 메시지 출력
        print(f"Data saved to {json_file_path}, {hex_file_path}, and {temp_file_path}")

    except Exception as e:
        print(f"An error occurred: {e}")
else:
    print("No payload received.")
