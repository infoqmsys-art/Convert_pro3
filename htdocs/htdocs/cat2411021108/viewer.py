#!C:\Python\Python313\python.exe

import os
import cgi

print("Content-Type: text/html")
print()  # Headers must be followed by a blank line

print("<html><head><title>Viewer</title></head><body>")
print("<h2>Select a File</h2>")

# 데이터 디렉토리
data_dir = "C:/cat/data/temporary"

# 데이터 파일 목록 가져오기
try:
    files = os.listdir(data_dir)
except Exception as e:
    print(f"<p>Error accessing data directory: {str(e)}</p>")
    print("</body></html>")
    exit()

# 파일 이름이 .txt로 끝나는 경우만 리스트에 포함
txt_files = [f for f in files if f.endswith('.txt')]

# 드롭다운 리스트 생성
print("<form action='' method='GET'>")
print("<select name='file_name'>")

# 파일 목록에서 각 파일에 대해 옵션 생성
for file in txt_files:
    # 파일 이름에서 '_temp.txt' 부분 제거
    display_name = file.replace('_temp.txt', '')  
    print(f"<option value='{file}'>{display_name}</option>")

print("</select>")
print("<input type='submit' value='View Data'>")
print("</form>")

# 선택한 파일에 대한 데이터 표시 (GET 요청)
form = cgi.FieldStorage()
if "file_name" in form:
    file_name = form.getvalue("file_name")
    file_path = os.path.join(data_dir, file_name)

    # 파일 경로 출력 (디버깅 용도)
    print(f"<p>Looking for file: {file_path}</p>")

    if os.path.isfile(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = f.read()
                print(f"<h3>Data for file: {file_name}</h3>")
                print(f"<pre>{data}</pre>")
        except Exception as e:
            print(f"<p>Error reading file: {str(e)}</p>")
    else:
        print(f"<p>No data found for file: {file_name}</p>")

print("</body></html>")
