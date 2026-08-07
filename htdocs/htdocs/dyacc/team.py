#!C:/Users/메인3/AppData/Local/Programs/Python/Python311/python.exe

import os
import json
from collections import defaultdict
from datetime import datetime

# Content-Type 헤더에 UTF-8 인코딩 추가
print("Content-Type: text/html; charset=utf-8")
print()  # Headers must be followed by a blank line

# 고정된 업체 코드 설정 (예: 'TEAM')
selected_code = 'TEAM'

data_dir = "C:/cat/data/temporary"
files = [f for f in os.listdir(data_dir) if f.endswith('.txt')]

print(f"""
<html>
<head>
    <title>QM - {selected_code}</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body {{ font-family: Arial, sans-serif; text-align: center; padding-top: 20px; }}
        .logo {{ width: 200px; height: auto; margin-bottom: 10px; }}
        .group-container {{ border: 2px solid #ccc; margin: 10px auto; padding: 15px; border-radius: 10px; width: 90%; text-align: left; background-color: #f9f9f9; }}
        .group-title {{ font-size: 20px; color: #333; margin-bottom: 10px; text-align: flex-start; font-weight: bold; }}
        .widget-container {{ display: flex; flex-wrap: wrap; gap: 3px; justify-content:flex-start; }}
        .widget {{ width: 110px; height: 160px; border: 1px solid #ddd; box-shadow: 2px 2px 10px rgba(0, 0, 0, 0.1); display: flex; flex-direction: column; align-items: center; justify-content: flex-end; background-color: #f0f0f0; text-align: center; font-size: 11px; color: #333; border-radius: 10px; padding: 8px; }}
        .widget-title {{ font-weight: bold; margin-bottom: 2px; display: flex; align-items: center; justify-content: center; }}
        .status-indicator {{ display: inline-block; width: 11px; height: 11px; border-radius: 50%; margin-left: 5px; }}
        .horizontal-bar-container {{ display: flex; justify-content: center; width: 100%; margin-bottom: 1.5px; gap: 2px; position: relative; }}
        .vertical-bar-container {{ width: 15px; height: 15px; background-color: #ddd; border-radius: 2px; position: relative; overflow: hidden; display: flex; align-items: flex-end; justify-content: center; }}
        .vertical-bar {{ width: 100%; background-color: #4CAF50; position: absolute; bottom: 0; }}
        .bar-label {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 6px;
            font-weight: bold;
            color: white;
            text-align: center;
            line-height: 1.2;
            white-space: pre-line;
            pointer-events: none;
        }}
        .battery-container {{ width: 100%; height: 15px; background-color: #ddd; border-radius: 5px; overflow: hidden; margin-top: 0px; position: relative; }}
        .battery-level {{ height: 100%; position: absolute; top: 0; left: 0; border-radius: 3px; }}
        .battery-text {{ position: absolute; top: 0; left: 50%; transform: translateX(-50%); height: 100%; width: 100%; display: flex; align-items: center; justify-content: center; font-size: 12px; color: white; font-weight: bold; pointer-events: none; }}
    </style>
</head>
<body>
    <img src="/cat/image/logo.png" alt="Logo" class="logo">
""")

# 데이터를 그룹화
grouped_data = defaultdict(list)

for file in files:
    file_path = os.path.join(data_dir, file)
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 필터링: 선택된 업체 코드로 시작하는 deviceId만 포함
    device_id = data.get("deviceId", "Unknown")
    if not device_id.startswith(selected_code):
        continue

    # 그룹화 키: TEAM 이후 값
    group_key = device_id[len(selected_code):]
    grouped_data[group_key].append(data)

# 현재 시간
current_time = datetime.now()

# 그룹별로 위젯 출력
for group_key, group_entries in grouped_data.items():
    print(f"""
    <div class="group-container">
        <div class="group-title">현장코드(우편번호): {group_key}</div>
        <div class="widget-container">
    """)
    for data in group_entries:
        title = data.get("title", "N/A")
        battery_level = data.get("batLevel", 0)
        timestamp_str = data.get("timestamp", "N/A")
        line_number = data.get("lineNumber", "N/A")  # lineNumber 추가
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            time_diff_minutes = (current_time - timestamp).total_seconds() / 60
            if time_diff_minutes <= 70:
                indicator_color = "#4CAF50"
            elif time_diff_minutes <= 241:
                indicator_color = "#FFCC00"
            else:
                indicator_color = "#FF0000"
        except ValueError:
            indicator_color = "#808080"

        if battery_level <= 20:
            battery_color = "#FF0000"
        elif battery_level <= 40:
            battery_color = "#FFCC00"
        else:
            battery_color = "#4CAF50"

        inside_temp = data.get("InsideTemperature", "N/A")
        temp_display = f"{inside_temp}&deg;C" if isinstance(inside_temp, (int, float)) else "N/A"

        amounts_html = "".join([
            f"""
            <div class="vertical-bar-container">
                <div class="vertical-bar" style="height: {min(100, max(0, float(data.get('AmountCH' + str(i), 0)) * 20))}%;"></div>
                <div class="bar-label">{i}</div>
            </div>
            """ for i in range(8)
        ])

        print(f"""
        <div class="widget" data-code="{group_key}">
            <div class="widget-title">
                Line Number: {line_number} <!-- lineNumber 맨 위에 출력 -->
            </div>
            <div><b>ID: {data.get("deviceId", "Unknown")}</b></div>
            <div>{timestamp_str}</div>
            <div>Interval: {data.get("intervalTimeSet", "N/A")}</div>
            <div>X: {data.get("degreeXAmount", "N/A")}</div>
            <div>Y: {data.get("degreeYAmount", "N/A")}</div>
            <div>Z: {data.get("degreeZAmount", "N/A")}</div>
            <div class="horizontal-bar-container">
                {amounts_html}
            </div>
            <div class="battery-container">
                <div class="battery-level" style="width: {max(0, min(100, float(battery_level)))}%; background-color: {battery_color};"></div>
                <div class="battery-text">{battery_level}%</div>
            </div>
            <div>Temp: {temp_display}</div>
            <div>Humidity: {data.get("InsideHumidity", "N/A")}%</div>
        </div>
        """)
    print("</div></div>")

print("""
</body>
</html>
""")
