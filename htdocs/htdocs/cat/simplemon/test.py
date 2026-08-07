#!C:/Python311/python.exe

import os
import random
import matplotlib.pyplot as plt

# 환경 변수 확인 (디버깅용)
os.environ["HOME"] = os.getenv("HOME", "C:/Apache24/htdocs/cat/image")
os.environ["MPLCONFIGDIR"] = os.getenv("MPLCONFIGDIR", "C:/Apache24/htdocs/cat/image/matplotlib_config")

# Content-Type 헤더 설정
print("Content-Type: text/html\n")

# 랜덤 데이터 생성
x = range(1, 11)
y = [random.randint(1, 100) for _ in x]

# 그래프 생성
plt.figure(figsize=(10, 5))
plt.plot(x, y, marker="o")
plt.title("Random Graph", fontsize=16)
plt.xlabel("X-axis")
plt.ylabel("Y-axis")

# 그래프 저장 경로
output_file = "C:/Apache24/htdocs/cat/image/random_graph.png"
plt.savefig(output_file)
plt.close()

# HTML 출력
print(f"""
<html>
<head><title>Random Graph</title></head>
<body>
<h1>Random Graph</h1>
<img src="/cat/image/random_graph.png" alt="Random Graph">
</body>
</html>
""")
