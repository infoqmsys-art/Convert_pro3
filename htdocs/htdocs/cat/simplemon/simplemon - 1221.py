#!C:/Users/메인3/AppData/Local/Programs/Python/Python311/python.exe

import os
import json
import cgi
from datetime import datetime

# Content-Type 헤더에 UTF-8 인코딩 추가
print("Content-Type: text/html; charset=utf-8")
print()  # Headers must be followed by a blank line

# URL 파라미터에서 'code' 값 읽기
form = cgi.FieldStorage()
selected_code = form.getvalue('code', 'all')  # 기본값은 'all'

data_dir = "C:/cat/data/temporary"
files = [f for f in os.listdir(data_dir) if f.endswith('.txt')]

print(f"""
<html>
<head>
    <title>Simple Monitor</title>
    <meta http-equiv="refresh" content="30"; URL=?code={selected_code}">
    <style>
        body {{ font-family: Arial, sans-serif; text-align: center; padding-top: 50px; }}
        .viewer-btn {{
            position: absolute;
            top: 5px;
            left: 5px; /* 로고 오른쪽 여백 */
            color: white;
            background-color: #808080;
            padding: 10px 20px;
            text-decoration: none;
            border-radius: 5px;
            font-size: 14px;
            box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.2);
        }}
        .logo {{
            position: absolute;
            top: 5px; /* 상단 위치 */
            left: 50%; /* 화면의 50% 지점 */
            transform: translateX(-50%); /* 수평 중앙 정렬 */
            width: 140px; /* 로고 너비 */
            height: auto;
        }}
        .logo-container {{
            margin-bottom: px; /* 로고 아래 여백 */
        }}
        .viewer-btn:hover {{ background-color: #6e6e6e; }}
        #code-filter {{
            position: absolute;
            top: 5px;
            right: 5px; /* 우측 정렬 */
            font-size: 14px;
            padding: 5px;
        }}
        .group-box {{
            border: 2px solid #ddd;
            border-radius: 10px;
            margin: 2px auto;
            padding: 5px;
            background-color: #f9f9f9;
            width: 90%;
            box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.1);
        }}
        .group-title {{
            font-size: 12오전 10:39 2024-12-21px;
            font-weight: bold;
            text-align: left;
            margin-bottom: 10px;
        }}
        .widget-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 3px;
            justify-content: flex-start;
            margin-top: 3px;
        }}
        .widget {{
            width: 110px;
            height: 160px;
            border: 1px solid #ddd;
            box-shadow: 2px 2px 10px rgba(0, 0, 0, 0.1);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-end;
            background-color: #f0f0f0;
            text-align: center;
            font-size: 11px;
            color: #333;
            border-radius: 10px;
            padding: 8px;
        }}
        .widget-title {{
            font-weight: bold;
            margin-bottom: 2px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .status-indicator {{
            display: inline-block;
            width: 11px;
            height: 11px;
            border-radius: 50%;
            margin-left: 5px;
        }}
        .horizontal-bar-container {{
            display: flex;
            justify-content: center;
            width: 100%;
            margin-bottom: 1.5px;
            gap: 2px;
            position: relative;
        }}
        .vertical-bar-container {{
            width: 15px;
            height: 15px;
            background-color: #ddd;
            border-radius: 2px;
            position: relative;
            overflow: hidden;
            display: flex;
            align-items: flex-end;
            justify-content: center;
        }}
        .vertical-bar {{
            width: 100%;
            background-color: #4CAF50;
            position: absolute;
            bottom: 0;
        }}
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
        .battery-container {{
            width: 100%;
            height: 15px;
            background-color: #ddd;
            border-radius: 5px;
            overflow: hidden;
            margin-top: 0px;
            position: relative;
        }}
        .battery-level {{
            height: 100%;
            position: absolute;
            top: 0;
            left: 0;
            border-radius: 3px;
        }}
        .battery-text {{
            position: absolute;
            top: 0;
            left: 50%;
            transform: translateX(-50%);
            height: 100%;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            color: white;
            font-weight: bold;
            pointer-events: none;
        }}
    </style>
</head>
<body>
    <img src="http://qmserver.iptime.org/cat/image/logo.png" alt="Logo" class="logo">
    <a href="/cat/viewer.py" class="viewer-btn">go to viewer</a>
    <select id="code-filter" onchange="location.href='?code=' + this.value;">
        <option value="all" {"selected" if selected_code == "all" else ""}>전체보기</option>
""")
# 나머지 Python 로직은 변경 없음
grouped_data = {}
site_codes = set()

for file in files:
    file_path = os.path.join(data_dir, file)
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    device_id = data.get("deviceId", "Unknown")
    site_code = device_id[:4]
    site_codes.add(site_code)
    if site_code not in grouped_data:
        grouped_data[site_code] = []
    grouped_data[site_code].append((file, data))

sorted_site_codes = sorted(site_codes)
for site_code in sorted_site_codes:
    print(f'<option value="{site_code}" {"selected" if site_code == selected_code else ""}>{site_code}</option>')

print("</select>")

current_time = datetime.now()

for site_code, entries in grouped_data.items():
    if selected_code != 'all' and site_code != selected_code:
        continue

    print(f"""
    <div class="group-box">
        <div class="group-title">업체 코드: {site_code}</div>
        <div class="widget-container">
    """)

    for file, data in sorted(entries, key=lambda x: x[1].get("deviceId", "")[-6:]):
        device_id = data.get("deviceId", "Unknown")
        title = file.replace('_temp.txt', '')
        title_display = f"0{title[:2]}-{title[2:6]}-{title[6:]}"
        battery_level = data.get("batLevel", 0)
        timestamp_str = data.get("timestamp", "N/A")
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            time_diff_minutes = (current_time - timestamp).total_seconds() / 60
            indicator_color = (
                "#4CAF50" if time_diff_minutes <= 60
                else "#FFCC00" if time_diff_minutes <= 1440
                else "#FF0000"
            )
        except ValueError:
            indicator_color = "#808080"

        battery_color = (
            "#FF0000" if battery_level <= 20
            else "#FFCC00" if battery_level <= 40
            else "#4CAF50"
        )

        inside_temp = data.get("InsideTemperature", "N/A")
        temp_display = f"{inside_temp}&deg;C" if isinstance(inside_temp, (int, float)) else "N/A"

        amounts_html = "".join([f"""
            <div class="vertical-bar-container">
                <div class="vertical-bar" style="height: {min(100, max(0, float(data.get('AmountCH' + str(i), 0)) * 20))}%;"></div>
                <div class="bar-label">{i}</div>
            </div>
        """ for i in range(8)])

        print(f"""
        <div class="widget" data-code="{site_code}">
            <div class="widget-title">
                {title_display}
                <span class="status-indicator" style="background-color: {indicator_color};"></span>
            </div>
            <div><b>ID: {device_id}</b></div>
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

print("</body></html>")
