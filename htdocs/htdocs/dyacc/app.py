from flask import Flask, render_template, Response
from ftplib import FTP
import matplotlib.pyplot as plt
import io
import traceback

app = Flask(__name__)

# FTP 서버 정보
FTP_HOST = "qms.synology.me"
FTP_USER = "qmsys"
FTP_PASS = "15242265kK!"
FTP_DIR = "/QM_MAIN/C/data/서초동"

def get_ftp_files(encoding="utf-8"):
    """
    FTP 서버에서 파일 목록을 가져옵니다.
    """
    try:
        ftp = FTP(FTP_HOST)
        ftp.encoding = encoding
        ftp.login(FTP_USER, FTP_PASS)
        ftp.cwd(FTP_DIR)
        files = []
        ftp.retrlines("NLST", files.append)
        ftp.quit()
        return files
    except Exception as e:
        return [f"오류 발생: {e}", traceback.format_exc()]

@app.route("/")
def index():
    """
    메인 페이지: FTP 파일 목록 표시
    """
    files = get_ftp_files(encoding="utf-8")
    is_error = any("오류 발생" in file for file in files)  # 에러 여부 확인
    return render_template("index.html", files=files, directory=FTP_DIR, is_error=is_error)

@app.route("/plot.png")
def plot_png():
    """
    그래프 생성 및 반환 (에러 발생 시 그래프 차단)
    """
    # 에러 발생 시 그래프 반환 차단
    files = get_ftp_files(encoding="utf-8")
    if any("오류 발생" in file for file in files):
        return Response("에러로 인해 그래프를 표시할 수 없습니다.", mimetype="text/plain")

    # 정상적인 경우 그래프 생성
    plt.figure(figsize=(6, 4))
    plt.plot([1, 2, 3, 4, 5], [10, 20, 25, 30, 35], marker="o", linestyle="--")
    plt.title("Sample Graph")
    plt.xlabel("X-axis")
    plt.ylabel("Y-axis")
    plt.grid(True)

    output = io.BytesIO()
    plt.savefig(output, format="png")
    plt.close()
    output.seek(0)
    return Response(output.getvalue(), mimetype="image/png")

if __name__ == "__main__":
    app.run(debug=True, port=5001)
