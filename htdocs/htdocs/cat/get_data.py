#!/usr/bin/env python
import json
import os
import sys

print("Content-Type: application/json")
print()

# 데이터 파일 경로
data_file = "C:/Apache24/htdocs/cat/data.json"

# 데이터 파일에서 읽기
if os.path.exists(data_file):
    with open(data_file, 'r') as file:
        data = json.load(file)
else:
    data = {"error": "Data file not found"}

# JSON 데이터 출력
print(json.dumps(data))
