#!C:/Python311/python.exe

import os
import cgi
import json

# Content-type 설정
print("Content-Type: text/html")
print()  # Headers must be followed by a blank line

# HTML 문서 시작
print("""
<html>
<head>
    <title>Viewer</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; position: relative; text-align: center; }
        .simplemon-btn {
            position: absolute;
            top: 0px;
            left: 0px;
            font-size: 15px;
            padding: 10px 15px; /* 여백을 늘려서 버튼 크기 키움 */
            color: white;
            background-color: #808080;
            border: none;
            border-radius: 5px;
            text-decoration: none;
            text-align: center;
            cursor: pointer;
            box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.2);
        }

        .simplemon-btn:hover {
            background-color: #6e6e6e;
        }

        #current-time {
            position: absolute;
            top: 20px;
            right: 20px;
            font-size: 16px;
            color: #333;
            font-weight: bold;
        }

        .logo {
            display: block;
            margin: 0 auto 20px auto;
            width: 300px;
            height: auto;
        }

        #line-number {
            font-size: 20px;
            margin-top: 20px;
            font-weight: bold;
        }

        .dropdown-container {
            text-align: center;
            margin-bottom: 20px;
        }

        select, input[type='submit'] {
            padding: 8px;
            font-size: 16px;
            margin: 5px;
        }

        table {
            width: 80%;
            margin: 20px auto;
            border-collapse: separate;
            border-spacing: 0;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
            font-size: 16px;
        }

        th, td {
            padding: 12px 15px;
            border-bottom: 1px solid #ddd;
            text-align: left;
        }

        th {
            background-color: #FFCC00;
            color: #333333;
            font-weight: bold;
        }

        tr:nth-child(even) { background-color: #f9f9f9; }
        tr:hover { background-color: #f1f1f1; }

        tr:last-child td {
            border-bottom: none;
        }
    </style>
    <script>
        function updateTime() {
            const now = new Date();
            const formattedTime = now.getFullYear() + '-' +
                                  (now.getMonth() + 1).toString().padStart(2, '0') + '-' +
                                  now.getDate().toString().padStart(2, '0') + ' ' +
                                  now.getHours().toString().padStart(2, '0') + ':' +
                                  now.getMinutes().toString().padStart(2, '0') + ':' +
                                  now.getSeconds().toString().padStart(2, '0');
            document.getElementById('current-time').innerText = formattedTime;
        }

        setInterval(updateTime, 1000);
        window.onload = updateTime;
    </script>
</head>
<body>
    <a href="/cat/simplemon/simplemon.py" class="simplemon-btn">simplemon</a>
    <div id="current-time"></div>
    <img src="/cat/image/logo.png" alt="Logo" class="logo">
""")

# 드롭다운 메뉴 및 파일 선택
print("""
    <div class="dropdown-container">
        <form action="" method="GET">
            <select name="file_name">
""")

# 데이터 디렉토리 및 파일 목록 생성
data_dir = "C:/cat/data/temporary"
files = os.listdir(data_dir)
txt_files = [f for f in files if f.endswith('.txt')]

# 선택된 파일 유지하기 위해 GET 요청의 file_name 값을 가져옵니다
form = cgi.FieldStorage()
selected_file = form.getvalue("file_name") if "file_name" in form else ""

# 드롭다운 메뉴 옵션 생성
for file in txt_files:
    display_name = file.replace('_temp.txt', '')
    selected_attr = "selected" if file == selected_file else ""
    print(f"<option value='{file}' {selected_attr}>{display_name}</option>")

print("""
            </select>
            <input type="submit" value="View Data">
        </form>
    </div>
""")

# 선택한 파일에 대한 데이터 표시
line_number = "Select number"  # 기본값

if selected_file:
    file_path = os.path.join(data_dir, selected_file)

    if os.path.isfile(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                line_number = data.get("lineNumber", "Select number")  # JSON에서 lineNumber 가져오기

                # line_number 포맷팅 (숫자일 경우 0 추가 및 "-" 삽입)
                if isinstance(line_number, int):
                    formatted_line_number = f"0{line_number:010}"  # 0을 붙이고 12자리로 포맷팅
                    formatted_line_number = f"{formatted_line_number[:3]}-{formatted_line_number[3:7]}-{formatted_line_number[7:]}"
                else:
                    formatted_line_number = "N/A"

                # 표 출력
                print(f'<h3 id="line-number">Line-Number: {formatted_line_number}</h3>')
                print("<table>")
                print("<tr><th>Key</th><th>Value</th></tr>")
                for key, value in data.items():
                    print(f"<tr><td>{key}</td><td>{value}</td></tr>")
                print("</table>")
            except json.JSONDecodeError:
                print("<p>Error: Selected file does not contain valid JSON data.</p>")
                f.seek(0)
                print(f"<pre>{f.read()}</pre>")
    else:
        print(f"<p>No data found for file: {selected_file}</p>")
else:
    print(f'<h3 id="line-number">Line-Number: {line_number}</h3>')

print("</body></html>")
