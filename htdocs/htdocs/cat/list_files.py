#!C:/Users/메인3/AppData/Local/Programs/Python/Python311/python.exe
import os
import sys

print("Content-Type: application/json")
print()

directory = "C:/cat/data/temporary/"
files = [f for f in os.listdir(directory) if f.endswith('_temp.txt')]
print(json.dumps(files))
