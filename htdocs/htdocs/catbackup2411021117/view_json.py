#!C:\Python\Python313\python.exe
import sys
import json
import os
from urllib.parse import parse_qs

print("Content-Type: application/json")
print()

# 쿼리 스트링 파싱
query_string = os.environ.get('QUERY_STRING', '')
params = parse_qs(query_string)
line_number = params.get('line_number', [None])[0]

# 파일 경로 설정
if line_number:
    json_file_path = f"C:/cat/data/temporary/{line_number}_temp.txt"
    try:
        with open(json_file_path, "r") as file:
            data = json.load(file)
            print(json.dumps(data))  # JSON 데이터 출력
    except FileNotFoundError:
        print(json.dumps({"error": "File not found."}))
    except json.JSONDecodeError:
        print(json.dumps({"error": "Failed to decode JSON."}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
else:
    print(json.dumps({"error": "No line number provided."}))