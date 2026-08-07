#!C:/Python/Python313/python.exe
import matplotlib
matplotlib.use('Agg')  # non-GUI 백엔드 설정
import os

# 그래프 데이터
x = [1, 2, 3, 4, 5]
y = [10, 20, 25, 30, 35]

# 그래프 생성
plt.figure(figsize=(8, 6))
plt.plot(x, y, marker='o', linestyle='-', color='b', label='Sample Data')
plt.title('Sample Graph')
plt.xlabel('X-axis')
plt.ylabel('Y-axis')
plt.legend()
plt.grid(True)

# 저장 경로
output_dir = r"C:\Apache24\htdocs\cat\image"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

output_path = os.path.join(output_dir, 'graph.png')

# 그래프 저장
plt.savefig(output_path)
print(f"Graph saved to: {output_path}")

# 그래프 표시
plt.show()
