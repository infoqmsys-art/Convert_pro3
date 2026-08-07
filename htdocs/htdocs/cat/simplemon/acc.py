#!C:/Users/메인3/AppData/Local/Programs/Python/Python311/python.exe
import os
import cgi
import csv
import json
import sys

form = cgi.FieldStorage()
selected_file = form.getvalue('file', '')
start_date = form.getvalue('start_date', '')
end_date = form.getvalue('end_date', '')
download = form.getvalue('download', '')

csv_dir = r"C:\cat\data\csv\DYANPRUGI0"

# ==========================================================
# ⭐ 사용자 지정 컬럼 설정 (7, 8, 9로 고정)
# ==========================================================
COL_TIMESTAMP = 0  
COL_X = 7          # X축 진동 데이터 (파랑)
COL_Y = 8          # Y축 진동 데이터 (보라)
COL_Z = 9          # Z축 진동 데이터 (핑크)
# ==========================================================

filter_start = f"{start_date} 00:00:00" if start_date else ""
filter_end = f"{end_date} 23:59:59" if end_date else ""

def safe_float(val):
    try:
        return float(str(val).strip())
    except:
        return 0.0

# ----------------------------------------------------------
# 💾 CSV 다운로드 (표에 보이는 값 그대로 저장)
# ----------------------------------------------------------
if download == 'true' and selected_file:
    file_path = os.path.join(csv_dir, selected_file)
    if os.path.exists(file_path):
        print(f"Content-Type: text/csv; charset=cp949")
        print(f"Content-Disposition: attachment; filename=filtered_{selected_file}")
        print()
        try:
            with open(file_path, 'r', encoding='cp949', errors='ignore') as f:
                reader = csv.reader(f)
                next(reader)
                writer = csv.writer(sys.stdout, lineterminator='\n')
                writer.writerow(['Timestamp', 'Amp X', 'Amp Y', 'Amp Z'])
                rows = []
                for row in reader:
                    if not row or len(row) <= max(COL_TIMESTAMP, COL_X, COL_Y, COL_Z): continue
                    ts = row[COL_TIMESTAMP]
                    if (filter_start and ts < filter_start) or (filter_end and ts > filter_end): continue
                    # 화면과 동일하게 7, 8, 9번 열 추출
                    rows.append([row[COL_TIMESTAMP], row[COL_X], row[COL_Y], row[COL_Z]])
                for r in reversed(rows): writer.writerow(r)
            sys.exit()
        except: pass

# ----------------------------------------------------------
# 🌐 HTML 출력
# ----------------------------------------------------------
print("Content-Type: text/html; charset=utf-8\n")
print(f"""<html><head><title>진동 모니터링</title><script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
    body {{ font-family: 'Malgun Gothic', sans-serif; background: #f0f2f5; padding: 20px; }}
    .container {{ background: white; padding: 25px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); max-width: 1600px; margin: 0 auto; }}
    .main-content {{ display: flex; gap: 20px; align-items: flex-start; margin-top: 20px; }}
    .chart-wrapper {{ flex: 1; height: 500px; border: 1px solid #ddd; padding: 15px; background: #fff; }}
    .status-panel {{ width: 200px; background: #fff; padding: 15px; border: 1px solid #eee; border-radius: 10px; }}
    .panel-section {{ margin-bottom: 20px; }}
    .panel-title {{ font-size: 14px; font-weight: bold; border-bottom: 2px solid #333; padding-bottom: 5px; margin-bottom: 10px; }}
    .status-item {{ margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; font-size: 13px; }}
    .color-box {{ display: inline-block; width: 25px; height: 4px; border-radius: 2px; margin-right: 8px; }}
    .filter-box {{ background: #fff; padding: 15px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #eee; display: flex; justify-content: center; gap: 10px; }}
    .btn {{ display: inline-block; padding: 6px 10px; margin: 2px; color: white; text-decoration: none; border-radius: 4px; font-size: 11px; background: #555; }}
    .active {{ background: #e74c3c !important; }}
    .table-box {{ margin-top: 20px; max-height: 400px; overflow-y: auto; border: 1px solid #ddd; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
    th {{ background: #2c3e50; color: white; position: sticky; top: 0; padding: 8px; }}
    td {{ border: 1px solid #eee; padding: 6px; text-align: center; }}
</style></head><body><div class="container"><h2>📊 진동 데이터 정밀 모니터링</h2><div style="margin-bottom:20px; overflow-x:auto; white-space:nowrap;">""")

if os.path.exists(csv_dir):
    for f in sorted([f for f in os.listdir(csv_dir) if f.endswith('.csv')], reverse=True):
        print(f'<a href="?file={f}&start_date={start_date or ""}&end_date={end_date or ""}" class="btn {"active" if selected_file == f else ""}">{f}</a>')

print(f"""</div>
    <form method="GET" class="filter-box">
        <input type="hidden" name="file" value="{selected_file}">
        📅 <input type="date" name="start_date" value="{start_date or ''}"> ~ <input type="date" name="end_date" value="{end_date or ''}">
        <button type="submit" style="padding:6px 15px; cursor:pointer; background:#3498db; color:white; border:none; border-radius:4px;">조회</button>
        <button type="button" onclick="location.href=window.location.href+'&download=true'" style="padding:6px 15px; cursor:pointer; background:#27ae60; color:white; border:none; border-radius:4px;">📥 CSV 다운로드</button>
    </form>
""")

if selected_file:
    # 모든 데이터를 이 리스트 하나에 통합 관리 (불일치 방지 핵심)
    master_data = []
    file_path = os.path.join(csv_dir, selected_file)
    try:
        with open(file_path, 'r', encoding='cp949', errors='ignore') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if not row or len(row) <= max(COL_TIMESTAMP, COL_X, COL_Y, COL_Z): continue
                ts = row[COL_TIMESTAMP]
                if (filter_start and ts < filter_start) or (filter_end and ts > filter_end): continue
                
                # 7, 8, 9번 열에서 데이터를 뽑아 객체로 저장
                master_data.append({
                    'ts': ts,
                    'x': safe_float(row[COL_X]),
                    'y': safe_float(row[COL_Y]),
                    'z': safe_float(row[COL_Z])
                })

        if master_data:
            # master_data에서 그대로 뽑아 쓰기 때문에 표와 그래프가 다를 수 없음
            c_labels = [d['ts'][5:16] for d in master_data]
            c_x = [d['x'] for d in master_data]
            c_y = [d['y'] for d in master_data]
            c_z = [d['z'] for d in master_data]
            
            COLOR_X, COLOR_Y, COLOR_Z = '#2980b9', '#8e44ad', '#f06292' # 파랑, 보라, 핑크
            l1, l2, l3 = [0.1]*len(c_labels), [0.2]*len(c_labels), [0.3]*len(c_labels)

            print(f"""<div class="main-content"><div class="chart-wrapper"><canvas id="adminChart"></canvas></div>
            <div class="status-panel">
                <div class="panel-section"><h3 class="panel-title">📈 데이터 색상</h3>
                    <div class="status-item"><span class="color-box" style="background:{COLOR_X};"></span>X축 (파랑)</div>
                    <div class="status-item"><span class="color-box" style="background:{COLOR_Y};"></span>Y축 (보라)</div>
                    <div class="status-item"><span class="color-box" style="background:{COLOR_Z};"></span>Z축 (핑크)</div>
                </div>
                <div class="panel-section"><h3 class="panel-title">📋 관리기준</h3>
                    <div class="status-item"><span class="color-box" style="background:#2ecc71;"></span>1차 (0.1)</div>
                    <div class="status-item"><span class="color-box" style="background:#e67e22;"></span>2차 (0.2)</div>
                    <div class="status-item"><span class="color-box" style="background:#c0392b;"></span>3차 (0.3)</div>
                </div>
            </div></div>
            <script>new Chart(document.getElementById('adminChart'), {{ type: 'line', data: {{ labels: {json.dumps(c_labels)},
            datasets: [ {{ label: 'X', data: {json.dumps(c_x)}, borderColor: '{COLOR_X}', borderWidth: 1.2, pointRadius: 0, fill: false }},
            {{ label: 'Y', data: {json.dumps(c_y)}, borderColor: '{COLOR_Y}', borderWidth: 1.2, pointRadius: 0, fill: false }},
            {{ label: 'Z', data: {json.dumps(c_z)}, borderColor: '{COLOR_Z}', borderWidth: 1.2, pointRadius: 0, fill: false }},
            {{ label: '1차', data: {json.dumps(l1)}, borderColor: '#2ecc71', borderWidth: 1.5, borderDash: [5, 5], pointRadius: 0, fill: false }},
            {{ label: '2차', data: {json.dumps(l2)}, borderColor: '#e67e22', borderWidth: 1.5, borderDash: [5, 5], pointRadius: 0, fill: false }},
            {{ label: '3차', data: {json.dumps(l3)}, borderColor: '#c0392b', borderWidth: 1.5, borderDash: [5, 5], pointRadius: 0, fill: false }} ] }},
            options: {{ responsive: true, maintainAspectRatio: false, animation: false,
            scales: {{ x: {{ ticks: {{ autoSkip: true, maxTicksLimit: 12 }} }}, y: {{ min: 0, max: 0.35, ticks: {{ stepSize: 0.05 }} }} }},
            plugins: {{ legend: {{ display: false }} }} }} }});</script>""")

        # 표 출력 (master_data를 최신순으로 뒤집어서 출력)
        print(f"<div class='table-box'><table><thead><tr><th>Timestamp</th><th>Amp X</th><th>Amp Y</th><th>Amp Z</th></tr></thead><tbody>")
        for d in reversed(master_data):
            print(f"<tr><td>{d['ts']}</td><td>{d['x']}</td><td>{d['y']}</td><td>{d['z']}</td></tr>")
        print("</tbody></table></div>")
    except Exception as e: print(f"<p>오류: {e}</p>")

print("</div></body></html>")