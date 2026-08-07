#!C:/Users/메인3/AppData/Local/Programs/Python/Python311/python.exe

import os
import json
from datetime import datetime

print("Content-Type: application/json")
print()

data_dir = "C:/cat/data/temporary"
files = [f for f in os.listdir(data_dir) if f.endswith('.txt')]
current_time = datetime.now()

grouped_data = []

for file in files:
    file_path = os.path.join(data_dir, file)
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    device_id = data.get("deviceId", "Unknown")
    timestamp_str = data.get("timestamp", "N/A")

    # 배터리 및 기타 데이터 계산
    battery_level = data.get("batLevel", 0)
    temp_display = f"{data.get('InsideTemperature', 'N/A')}°C"
    amounts_html = "".join([
        f"<div class='vertical-bar-container'><div class='vertical-bar' style='height: {min(100, max(0, float(data.get('AmountCH' + str(i), 0)) * 20))}%;'></div></div>"
        for i in range(8)
    ])

    # 결과 추가
    grouped_data.append({
        "title": file.replace('_temp.txt', ''),
        "device_id": device_id,
        "timestamp": timestamp_str,
        "battery_level": battery_level,
        "temp_display": temp_display,
        "amounts_html": amounts_html,
        "battery_color": "#4CAF50" if battery_level > 40 else "#FFCC00" if battery_level > 20 else "#FF0000",
        "indicator_color": "#4CAF50",  # 예제 값을 추가, 로직 개선 가능
        "humidity": data.get("InsideHumidity", "N/A"),
        "intervalTimeSet": data.get("intervalTimeSet", "N/A"),
        "degreeXAmount": data.get("degreeXAmount", "N/A"),
        "degreeYAmount": data.get("degreeYAmount", "N/A"),
        "degreeZAmount": data.get("degreeZAmount", "N/A"),
    })

print(json.dumps(grouped_data))
