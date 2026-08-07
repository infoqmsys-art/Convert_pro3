#!C:/Users/메인3/AppData/Local/Programs/Python/Python311/python.exe
import sys
import json
import struct
import os
from datetime import datetime, timedelta

print("Content-Type: text/plain")
print()

# 타임스탬프 변환 함수 (2000년 1월 1일을 기준으로 계산하고 한국 시간으로 변환)
def convert_timestamp(seconds_since_2000):
    base_date = datetime(2000, 1, 1, 0, 0, 0)
    target_date = base_date + timedelta(seconds=seconds_since_2000)
    kst_date = target_date + timedelta(hours=9)  # UTC에서 9시간 추가
    return kst_date.strftime("%Y-%m-%d %H:%M:%S")

# 비트 상태를 6개의 항목으로 해석하고 16진수와 비트를 개행으로 표시
def parse_status_byte(status_byte):
    bits = f"{status_byte:08b}"  # 8비트 문자열로 변환
    parsed_status = (
        f"THsts: {int(bits[7])}\n"
        f"DEGsts: {int(bits[6])}\n"
        f"D-Type: {int(bits[5])}\n"
        f"CRSts: {int(bits[4])}\n"
        f"Sleep: {int(bits[3])}\n"
        f"BATsts: {int(bits[2])}\n"
        f"hex : 0x{status_byte:02X}\n"
        f"bit: {bits}"  # 원래 8비트
    )
    return parsed_status

# JSON 데이터 읽기
data = sys.stdin.read()

try:
    # JSON 데이터 파싱
    json_data = json.loads(data)
    hex_data = json_data.get("payload", "")
    byte_data = bytes.fromhex(hex_data)

    # 데이터의 길이를 확인하고 128바이트로 맞추기
    if len(byte_data) < 128:
        byte_data = byte_data.ljust(128, b'\x00')  # 부족한 경우 패딩 추가

    # Payload_struct 형식 정의
    payload_format = (
        "<4s I f I I I f f f f f f f f f f f f f f f f 20s I I f I 4s"
    )

    # 데이터 파싱
    payload = struct.unpack(payload_format, byte_data)

    # 인덱스 24의 4바이트 중 첫 번째 바이트만 추출
    status_first_byte = payload[24] & 0xFF  # 4바이트 중 첫 번째 바이트 추출
    
    # 필드 매핑 (필요한 값들은 반올림 및 계산 적용)
    parsed_data = {
        "STX": payload[0].decode(),
        "Length": payload[1],
        "Protocolversion": round(payload[2], 2),  # 소수점 2째 자리로 반올림
        "lineNumber": payload[3],
        "intervalTimeSet": payload[4],
        "timestamp": convert_timestamp(payload[5]),  # 타임스탬프 변환 적용
        "amplifierX": payload[6],
        "amplifierY": payload[7],
        "amplifierZ": payload[8],
        "frequencyX": payload[9],
        "frequencyY": payload[10],
        "frequencyZ": payload[11],
        "degreeXAmount": round(payload[12], 3),
        "degreeYAmount": round(payload[13], 3),
        "degreeZAmount": round(payload[14], 3),
        "crackAmount": round(payload[15], 3),
        "initDegreeX": round(payload[16], 3),
        "initDegreeY": round(payload[17], 3),
        "initDegreeZ": round(payload[18], 3),
        "initCrack": round(payload[19], 3),
        "temperature": round(payload[20], 2),  # 소수점 2째 자리로 반올림
        "humidity": round(payload[21], 2),  # 소수점 2째 자리로 반올림
        "Reserve": payload[22].decode(errors="ignore"),
        "Reserve_status": payload[23],
        "Status": parse_status_byte(status_first_byte),  # 첫 번째 바이트만 사용
        "batLevel": round(payload[25], 2),  # 배터리 레벨 계산 수정 (소수점 2째 자리까지)
        "_CRC": payload[26],
        "ETX": payload[27].decode(errors="ignore")
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
