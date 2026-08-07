#!C:/Python311/python.exe
import pandas as pd
import math
import cgi
import matplotlib.pyplot as plt
import os
from datetime import datetime, timedelta

# 현재 시간 가져오기
current_time = datetime.now()
default_end_date = current_time.strftime('%Y-%m-%d')  # YYYY-MM-DD 형식
default_start_date = (current_time - timedelta(days=7)).strftime('%Y-%m-%d')  # 7일 전

# CGI 파라미터 읽기
form = cgi.FieldStorage()
selected_demo = form.getvalue("data", "DEMO000001")  # 기본값은 DEMO000001
start_date = form.getvalue("start_date", default_start_date)  # 시작 날짜 기본값 설정
end_date = form.getvalue("end_date", default_end_date)  # 종료 날짜 기본값 설정

# 날짜 값이 비어 있으면 기본값 설정
if not start_date:
    start_date = default_start_date
if not end_date:
    end_date = default_end_date

# 파일 경로 매핑
file_mapping = {
    "DEMO000001": r"C:\cat\data\csv\QMDM000001\1232942954.csv",
    "DEMO000002": r"C:\cat\data\csv\QMDM000002\1227916622.csv",
    "DEMO000003": r"C:\cat\data\csv\QMDM000003\1232843512.csv",
    "DEMO000004": r"C:\cat\data\csv\QMDM000004\1232941118.csv",
    "DEMO000005": r"C:\cat\data\csv\QMDM000005\1232843594.csv"
}

# 선택된 DEMO 값으로 파일 경로 설정
csv_file_path = file_mapping.get(selected_demo, file_mapping["DEMO000001"])

# 파일 확인
if not os.path.exists(csv_file_path):
    print("Content-type: text/html\n")
    print(f"<h1>Error: File not found at path {csv_file_path}</h1>")
    print(f"Time range: {data['time'].iloc[0]} to {data['time'].iloc[-1]}")
    print(f"X ticks: {x_ticks}, X labels: {x_labels}")
    exit()

try:
    # CSV 파일 읽기: 첫 번째 줄(헤더) 무시
    data = pd.read_csv(csv_file_path, skiprows=1, header=None)  # 첫 줄 건너뛰고 데이터만 가져오기

    # 제거할 열의 인덱스 정의
    columns_to_remove = list(range(1, 16)) + list(range(24, 35)) + list(range(37, 56)) + list(range(57, 60))  # 지정된 열 제거
    # 유지할 열 계산
    columns_to_keep = [i for i in range(len(data.columns)) if i not in columns_to_remove]
    data = data.iloc[:, columns_to_keep]  # 선택된 열만 유지

    # 데이터 뒤집기 (행 순서 반전)
    data = data.iloc[::-1]

    # 가상 헤더 정의
    custom_header = ["time", "ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "ch7", "ch8", "temp", "humi", "bat"]

    data.columns = custom_header
    # 선택된 채널 처리 (custom_header 정의 후)
    selected_channels = form.getlist("channels")  # 체크박스에서 선택된 값 가져오기
    if not selected_channels or "all" in selected_channels:  # 선택된 값이 없거나 'all'이 선택된 경우
        selected_channels = custom_header[1:9]  # 기본값: 모든 채널
   
    # 시간 데이터 변환
    data["time"] = pd.to_datetime(data["time"], errors='coerce')  # 변환 불가능한 값은 NaT 처리
    data = data.dropna(subset=["time"])  # NaT 값 제거

    # 날짜 범위 확인 및 보정
    min_date = data["time"].min()  # 데이터의 최소 날짜
    max_date = data["time"].max()  # 데이터의 최대 날짜

    if start_date:
        start_date = pd.to_datetime(start_date, errors="coerce")
        if pd.isnull(start_date) or start_date < min_date:  # 시작 날짜가 없거나 범위보다 작은 경우
            start_date = min_date
    else:
        start_date = min_date  # 기본값: 최소 날짜

    if end_date:
        end_date = pd.to_datetime(end_date, errors="coerce")
        if pd.isnull(end_date) or end_date > max_date:  # 종료 날짜가 없거나 범위보다 큰 경우
            end_date = max_date
    else:
        end_date = max_date  # 기본값: 최대 날짜

    # 날짜 범위 필터링
    data = data[(data["time"] >= start_date) & (data["time"] <= end_date)]
    # 그래프 생성
    plt.style.use("ggplot")  # ggplot 스타일
    plt.figure(figsize=(8, 3))
    time_reversed = data["time"][::-1]  # 시간 데이터를 역순으로
    for ch in selected_channels:  # 선택된 채널만 반복
        if ch in custom_header[1:9]:  # 유효한 채널만 처리
            plt.plot(
                data["time"], 
                data[ch][::-1], 
                label=ch, 
                marker='o', 
                markersize=1, 
                linestyle=':', 
                linewidth=1
            )
    x_ticks = [0, len(data["time"]) // 2, len(data["time"]) - 1]  # 처음, 중간, 끝 인덱스
    x_labels = [data["time"].iloc[i].strftime('%Y-%m-%d %H:%M:%S') for i in x_ticks]

    with open("debug_log.txt", "w") as debug_file:
        debug_file.write(f"X Ticks: {x_ticks}\n")
        debug_file.write(f"X Labels: {x_labels}\n")
        debug_file.write(f"X Axis Range: {data['time'].iloc[0]} to {data['time'].iloc[-1]}\n")
    
    # 중복 방지를 위해 레이블을 고유하게 설정
    plt.xticks(ticks=x_ticks, labels=x_labels, rotation=30, fontsize=8)  # 레이블 회전 및 글씨 크기 조정
    plt.yticks(fontsize=7)  # Y축 눈금 글씨 크기 설정
    plt.xlim(data["time"].iloc[0], data["time"].iloc[-1])  # X축 범위를 명시적으로 설정
    plt.ylabel("Voltage (V)", fontsize=8)
    plt.legend(
        loc="upper center",            # 그래프 위쪽 중앙에 배치
        fontsize=8,                    # 글씨 크기
        ncol=len(custom_header[1:9]),  # 범례를 한 줄에 모두 배치
        bbox_to_anchor=(0.5, 1.15),    # 그래프 위쪽 밖으로 이동
        frameon=False                  # 범례 박스 테두리 제거 (선택)
    )
        # 축(Axes)의 배경을 흰색으로 설정
    ax = plt.gca()  # 현재의 축(Axes) 가져오기
    ax.set_facecolor('white')  # 축 내부 배경색을 흰색으로 설정
    plt.tight_layout()
    plt.grid()

    # 그래프 저장
    graph_path = "graph_output.png"
    plt.savefig(graph_path, dpi=150, transparent=False, facecolor='white')  # 투명 배경 설정
    plt.close()

    # 최신 값 가져오기
    latest_temp_value = round(math.ceil(data.iloc[0, -3] * 10) / 10, 1)  # temp (소수점 1자리 올림)
    latest_humi_value = round(math.ceil(data.iloc[0, -2] * 10) / 10, 1)  # humi (소수점 1자리 올림)
    latest_battery_value = round(math.ceil(data.iloc[0, -1] * 10) / 10, 1)  # bat (소수점 1자리 올림)

    # HTML 출력
    print(f"""
    <html>
    <head>
        <style>
            body {{
                font-family: 'Arial', sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f4f4f4;
                color: #333;
            }}
            .header {{
                background-color: #333;
                color: #fff;
                padding: 10px 20px;
                display: flex;
                align-items: center;
                justify-content: auto;
                position: sticky;
                top: 0;
                z-index: 1000;
                height: 40px; /* 헤더 높이 설정 */
                box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.1);
                margin-bottom: 20px;
            }}
            .header img {{
                height: 40px;
                margin-left: 10px;
                margin-right: 50px;
            }}
            .header .title {{
                font-size: 150%;
                font-weight: bold;
                margin-right: 50px;
            }}
            .header .contact {{
                display: flex;
                flex-direction: column; /* 세로 방향 정렬 */
                justify-content: flex-end;
                font-size: 50%;
                align-items: center;
                margin-right: auto; /* 중요: 버튼을 오른쪽으로 밀기 */
                gap: 10px;
            }}
            .header .contact div {{
             
                font-size: 30%;
            }}
            .header .button-container {{
                display: flex;
                justify-content: flex-end;
                margin-left: auto; /* 왼쪽 여백을 추가해 오른쪽으로 밀기 */
                margin-right: 10px; /* 중요: 버튼을 오른쪽으로 밀기 */
                gap: 10px;
            }}
            .header a button {{
                width: 80px;
                height: 30px;
                background-color: #555;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
            }}
            .header a button:hover {{
                background-color: #777;
            }}
            .container {{
                max-width: 1200px;
                margin: 20px auto;
                padding: 20px;
                background-color: #fff;
                border-radius: 8px;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
            }}
                 
            form {{
                margin-bottom: 20px;
                }}
             img {{
                max-width: 100%;
                height: auto;
                display: block;
                margin: 0 auto;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }}
            .dropdown {{
                text-align: right;
                margin-bottom: 20px;
            }}
            .dropdown select {{
                font-size: 100%;
                padding: 0.4%;
                border-radius: 4px;
                border: 1px solid #ccc;
            }}
            .graph-container {{
                flex: 1;
                height: 300px;
                background-color: #fff;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                display: flex;
                margin-top: 20px;
                align-items: center;
                justify-content: center;
                text-align: center;
            }}

            .graph-placeholder {{
                font-size: 5px;
                color: #aaa;
            }}

            .indicators {{
                display: flex;
                justify-content: flex-end;
                margin-bottom: 30px;
                gap: 1px;
            }}
            .indicator {{
                text-align: center;
                flex: 0 0 auto;
                margin: 0 10px;
            }}
            .indicator .bar-container {{
                width: 50px;
                height: 300px;
                margin: 0 auto;
                position: relative;
                background: #333;
                border-radius: 10px;
                overflow: hidden;
                display: flex;
                align-items: flex-end;
                justify-content: center;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }}
            .indicator .bar {{
                width: 100px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #fff;
                font-weight: bold;
                position: relative;
            }}
            .indicator .temp {{
                background-color: #ff6f91;
                height: {max(0, min(100, latest_temp_value * (100 / 80)))}%;
            }}
            .indicator .humi {{
                background-color: #69b7ff;
                height: {max(0, min(100, latest_humi_value))}%;
            }}
            .indicator .bat {{
                background-color: #67d27c;
                height: {max(0, min(100, latest_battery_value))}%;
            }}
            .table-container {{
                max-height: 400px; /* 테이블 컨테이너의 최대 높이 */
                overflow-y: auto; /* 세로 스크롤 활성화 */
                border: 1px solid #ddd; /* 테두리 추가 */
                border-radius: 8px; /* 테두리 둥글게 */
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            th, td {{
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #ddd;
                font-size: 14px;
            }}
            th {{
                background-color: #f9f9f9;
                font-weight: bold;
                position: sticky;
                top: 0;
                z-index: 1;
            }}
            tr:nth-child(even) {{
                background-color: #f2f2f2;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <img src="/cat/image/logo.png" alt="Company Logo">
            <div class="title">Cat-m1 Demo</div>
            <div class="contact">
                <div>Contact: 032-575-2555</div>
                <div>Email: info@qmsys.net</div>
            </div>
            <div class="default-dates">
            </div>
            <div class="button-container">
                <a href="/cat/simplemon/simplemon.py">
                    <button>simplemon</button>
                </a>
                <a href="/cat/viewer.py">
                    <button>DATAmon</button>
                </a>
            </div>
        </div>
        <div class="container">
            <div class="dropdown">
                <form method="get">
                    <label for="data-select">Select: </label>
                    <select id="data-select" name="data" onchange="this.form.submit()">
                        <option value="DEMO000001" {"selected" if selected_demo == "DEMO000001" else ""}>DEMO000001</option>
                        <option value="DEMO000002" {"selected" if selected_demo == "DEMO000002" else ""}>DEMO000002</option>
                        <option value="DEMO000003" {"selected" if selected_demo == "DEMO000003" else ""}>DEMO000003</option>
                        <option value="DEMO000004" {"selected" if selected_demo == "DEMO000004" else ""}>DEMO000004</option>
                        <option value="DEMO000005" {"selected" if selected_demo == "DEMO000005" else ""}>DEMO000005</option>
                                     </select>
                        <!-- Start Date -->
                        <label for="start" style="font-weight: bold;">Start Date:</label>
                        <input type="date" id="start_date" name="start_date" value="{start_date.strftime('%Y-%m-%d')}" 
                            style="padding: 0.5%; border: 1px solid #ccc; border-radius: 4px; background-color: #fff; font-size: 100%; cursor: pointer; box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.1);">
                        <label for="end" style="font-weight: bold;">End Date:</label>
                        <input type="date" id="end_date" name="end_date" value="{end_date.strftime('%Y-%m-%d')}" 
                            style="padding: 0.5%; border: 1px solid #ccc; border-radius: 4px; background-color: #fff; font-size: 100%; cursor: pointer; box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.1);">
                    <!-- Submit Button -->
                        <button type="submit" style="padding: 1%; background-color: #007bff; color: white; border: none; border-radius: 4px; font-size: 50%; cursor: pointer; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">
                            Search
                        </button>
                    <!-- 채널 선택 추가 -->
                    <br><br>
                <div style="display: flex; gap: 15px; flex-wrap: wrap; justify-content: flex-start; align-items: center; padding: 10px; background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">
                    <div style="display: flex; flex-direction: row-reverse; align-items: center; gap: 5px;">
                        <input type="checkbox" name="channels" value="ch1" {"checked" if "ch1" in selected_channels else ""}>
                        <span>CH1</span>
                    </div>
                    <div style="display: flex; flex-direction: row-reverse; align-items: center; gap: 5px;">
                        <input type="checkbox" name="channels" value="ch2" {"checked" if "ch2" in selected_channels else ""}>
                        <span>CH2</span>
                    </div>
                    <div style="display: flex; flex-direction: row-reverse; align-items: center; gap: 5px;">
                        <input type="checkbox" name="channels" value="ch3" {"checked" if "ch3" in selected_channels else ""}>
                        <span>CH3</span>
                    </div>
                    <div style="display: flex; flex-direction: row-reverse; align-items: center; gap: 5px;">
                        <input type="checkbox" name="channels" value="ch4" {"checked" if "ch4" in selected_channels else ""}>
                        <span>CH4</span>
                    </div>
                    <div style="display: flex; flex-direction: row-reverse; align-items: center; gap: 5px;">
                        <input type="checkbox" name="channels" value="ch5" {"checked" if "ch5" in selected_channels else ""}>
                        <span>CH5</span>
                    </div>
                    <div style="display: flex; flex-direction: row-reverse; align-items: center; gap: 5px;">
                        <input type="checkbox" name="channels" value="ch6" {"checked" if "ch6" in selected_channels else ""}>
                        <span>CH6</span>
                    </div>
                    <div style="display: flex; flex-direction: row-reverse; align-items: center; gap: 5px;">
                        <input type="checkbox" name="channels" value="ch7" {"checked" if "ch7" in selected_channels else ""}>
                        <span>CH7</span>
                    </div>
                    <div style="display: flex; flex-direction: row-reverse; align-items: center; gap: 5px;">
                        <input type="checkbox" name="channels" value="ch8" {"checked" if "ch8" in selected_channels else ""}>
                        <span>CH8</span>
                    </div>
                </div>

                </form>
            </div>
            <div class="indicators">
                <div class="graph-container">
                    <img src="{graph_path}" alt="Channel Data Over Time">
                </div>

                <div class="indicator">
                
                    <div class="bar-container">
                        <div class="bar temp"><span>{latest_temp_value}'C</span></div>
                    </div>
                    <p>Temp</p>
                </div>
                <div class="indicator">
                    <div class="bar-container">
                        <div class="bar humi"><span>{latest_humi_value}%</span></div>
                    </div>
                    <p>Humi</p>
                </div>
                <div class="indicator">
                    <div class="bar-container">
                        <div class="bar bat"><span>{latest_battery_value}%</span></div>
                    </div>
                    <p>Bat</p>
                </div>
            </div>
            <div class="table-container">
                <table>
                    <tr>
    """)

    # 가상 헤더 추가
    for header in custom_header:
        print(f"<th>{header}</th>")
    print("</tr>")

    # 데이터 추가 (뒤집어진 데이터)
    for _, row in data.iterrows():
        print("<tr>")
        for value in row:
            print(f"<td>{value}</td>")
        print("</tr>")

    print("""
                </table>
            </div>
        </div>
    </body>
    </html>
    """)

except Exception as e:
    print("Content-type: text/html\n")
    print(f"<h1>Error occurred while processing the CSV file: {e}</h1>")
