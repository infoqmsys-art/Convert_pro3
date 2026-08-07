#!C:\Python\Python313\python.exe
import os
import json
import cgi

print("Content-Type: text/html")
print()

print("<html><head><title>Viewer</title></head><body>")
print("<h2>Line Number Selection</h2>")

# 데이터 디렉토리
data_dir = "C:/cat/data/temporary"

# 데이터 파일 목록 가져오기
files = os.listdir(data_dir)

print("<form action='' method='GET'>")
print("<select name='line_number'>")

# 파일 목록에서 각 파일에 대해 옵션 생성
for file in files:
    if file.endswith('.txt'):
        line_number = file.split('.')[0]  # 파일 이름에서 라인 넘버 추출
        print(f"<option value='{line_number}'>{line_number}</option>")

print("</select>")
print("<input type='submit' value='View Data'>")
print("</form>")

# 선택한 라인 넘버에 따라 데이터 표시
form = cgi.FieldStorage()
if "line_number" in form:
    line_number = form.getvalue("line_number")
    file_path = os.path.join(data_dir, f"{line_number}.txt")

    if os.path.isfile(file_path):
        with open(file_path, 'r') as f:
            data = f.read()
            print("<h3>Data for line number: {}</h3>".format(line_number))
            print("<pre>{}</pre>".format(data))
    else:
        print("<p>No data found for line number: {}</p>".format(line_number))

print("</body></html>")
