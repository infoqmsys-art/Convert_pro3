#!C:/Users/메인3/AppData/Local/Programs/Python/Python311/python.exe
# -*- coding: utf-8 -*-

from ftplib import FTP
import traceback

# FTP 서버 정보
FTP_HOST = "qms.synology.me"
FTP_USER = "qmsys"
FTP_PASS = "15242265kK!"
FTP_DIR = "/QM_MAIN/C/data/서초동"

def get_ftp_files():
    """FTP 서버에서 파일 목록 가져오기."""
    try:
        ftp = FTP(FTP_HOST)
        ftp.login(FTP_USER, FTP_PASS)
        
        # 인코딩 없이 바이너리 데이터로 처리
        ftp.encoding = 'latin-1'

        ftp.cwd(FTP_DIR)

        # FTP 명령을 바이너리로 실행하여 디코딩 처리
        lines = []
        ftp.retrlines('NLST', lines.append)
        
        # 바이너리 데이터를 UTF-8로 디코딩 (필요 시 'euc-kr' 또는 다른 코드로 변경)
        files = [line.encode('latin-1').decode('utf-8', errors='replace') for line in lines]

        ftp.quit()
        return files
    except Exception as e:
        return [f"오류 발생: {e}", traceback.format_exc()]

# CGI 출력
try:
    print("Content-Type: text/html; charset=utf-8\n")
    print(f"""
    <!doctype html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>FTP 데이터 보기</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .file-list {{ display: flex; flex-wrap: wrap; gap: 10px; }}
            .file-item {{ padding: 10px; border: 1px solid #ddd; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <h1>FTP 디렉토리: {FTP_DIR}</h1>
        <div class="file-list">
    """)

    # FTP 파일 목록 출력
    files = get_ftp_files()
    for file in files:
        print(f'<div class="file-item">{file}</div>')

    print("""
        </div>
    </body>
    </html>
    """)
except Exception as e:
    # 예외 발생 시 디버깅 정보를 HTML로 출력
    print(f"""
    Content-Type: text/html; charset=utf-8\n
    <html>
    <head>
        <title>오류 발생</title>
    </head>
    <body>
        <h1>오류 발생</h1>
        <pre>{traceback.format_exc()}</pre>
    </body>
    </html>
    """)
