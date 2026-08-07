#!C:/Users/메인3/AppData/Local/Programs/Python/Python311/python.exe
import pandas as pd
import math
import cgi

# CGI 파라미터 읽기
form = cgi.FieldStorage()
selected_demo = form.getvalue("data", "DEMO000001")  # 기본값은 DEMO000001

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
                justify-content: space-between;
                position: sticky;
                top: 0;
                z-index: 1000;
                height: 60px; /* 헤더 높이 설정 */
                box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.1);
                margin-bottom: 20px;
            }}
            .header img {{
                height: 40px;
            }}
            .header .title {{
                font-size: 24px;
                font-weight: bold;
            }}
            .header .contact {{
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            .header .contact div {{
                font-size: 14px;
            }}
            .header .button-container {{
                display: flex;
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
            .dropdown {{
                text-align: right;
                margin-bottom: 20px;
            }}
            .dropdown select {{
                font-size: 16px;
                padding: 8px 12px;
                border-radius: 4px;
                border: 1px solid #ccc;
            }}
            .graph-container {{
                flex: 1;
                height: 300px;
                background-color: #f0f0f0;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                display: flex;
                align-items: center;
                justify-content: center;
                text-align: center;
            }}

            .graph-placeholder {{
                font-size: 18px;
                color: #aaa;
            }}

            .indicators {{
                display: flex;
                justify-content: flex-end;
                margin-bottom: 30px;
                gap: 20px;
            }}
            .indicator {{
                text-align: center;
                flex: 0 0 auto;
                margin: 0 10px;
            }}
            .indicator .bar-container {{
                width: 100px;
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
                width: 100%;
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
            <div class="title">Cat-m1 Demo Page (QM)</div>
            <div class="contact">
                <div>Contact: 032-575-2555</div>
                <div>Email: info@qmsys.net</div>
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
                    <label for="data-select">Select Data: </label>
                    <select id="data-select" name="data" onchange="this.form.submit()">
                        <option value="DEMO000001" {"selected" if selected_demo == "DEMO000001" else ""}>DEMO000001</option>
                        <option value="DEMO000002" {"selected" if selected_demo == "DEMO000002" else ""}>DEMO000002</option>
                        <option value="DEMO000003" {"selected" if selected_demo == "DEMO000003" else ""}>DEMO000003</option>
                        <option value="DEMO000004" {"selected" if selected_demo == "DEMO000004" else ""}>DEMO000004</option>
                        <option value="DEMO000005" {"selected" if selected_demo == "DEMO000005" else ""}>DEMO000005</option>
                    </select>
                </form>
            </div>
            <div class="indicators">
                <div class="graph-container">
                    <div class="graph-placeholder">Graph Placeholder</div>
                </div>

                <div class="indicator">
                
                    <div class="bar-container">
                        <div class="bar temp"><span>{latest_temp_value}'C</span></div>
                    </div>
                    <p>Temperature</p>
                </div>
                <div class="indicator">
                    <div class="bar-container">
                        <div class="bar humi"><span>{latest_humi_value}%</span></div>
                    </div>
                    <p>Humidity</p>
                </div>
                <div class="indicator">
                    <div class="bar-container">
                        <div class="bar bat"><span>{latest_battery_value}%</span></div>
                    </div>
                    <p>Battery</p>
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
    print(f"<h1>Error occurred while processing the CSV file: {e}</h1>")
