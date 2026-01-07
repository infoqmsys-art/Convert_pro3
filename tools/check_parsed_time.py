import pandas as pd
import re

# ==========================
# 1) 원본 CSV 파일 경로
# ==========================
SRC = r"C:\data\SAEGIL6522\1227541574.csv"   # 실제 경로로 수정


print("\n==========================================")
print("📌 STEP 1 — 원본 CSV 읽기")
print("==========================================")
df = pd.read_csv(SRC, sep=None, engine="python", encoding="utf-8")
time_col = df.columns[0]
print(f"시간 컬럼명: {time_col}")
print(f"총 행 수: {len(df)}")


# ==========================
# 2) 기본 파싱 테스트
# ==========================
print("\n==========================================")
print("📌 STEP 2 — 기본 parsed_time 변환")
print("==========================================")

raw_original = df[time_col].astype(str)
parsed_basic = pd.to_datetime(raw_original, errors="coerce")

print("기본 파싱 성공:", parsed_basic.notna().sum())
print("기본 파싱 실패:", parsed_basic.isna().sum())


# ==========================
# 3) 전처리 추가 후 파싱
# ==========================
print("\n==========================================")
print("📌 STEP 3 — strip + 제어문자 제거 후 파싱")
print("==========================================")

cleaned = (
    raw_original
    .str.strip()                               # 공백 제거
    .str.replace(r"[\x00-\x1F]+", "", regex=True)  # 제어문자 제거
)

parsed_clean = pd.to_datetime(cleaned, errors="coerce")

print("전처리 후 파싱 성공:", parsed_clean.notna().sum())
print("전처리 후 파싱 실패:", parsed_clean.isna().sum())


# ==========================
# 4) 길이 분석 (숨겨진 문자 탐지)
# ==========================
print("\n==========================================")
print("📌 STEP 4 — timestamp 문자열 길이 분석")
print("==========================================")

lengths = cleaned.str.len().value_counts().sort_index()
print(lengths)


# ==========================
# 5) 파싱 실패한 데이터 예시 출력
# ==========================
print("\n==========================================")
print("📌 STEP 5 — 파싱 실패 예시 20개")
print("==========================================")

bad_rows = df.loc[parsed_clean.isna(), time_col].head(20)
print(bad_rows.to_string(index=False))


# ==========================
# 6) 파싱 성공 예시 출력
# ==========================
print("\n==========================================")
print("📌 STEP 6 — 파싱 성공 예시 20개")
print("==========================================")

good_rows = df.loc[parsed_clean.notna(), time_col].head(20)
print(good_rows.to_string(index=False))


# ==========================
# 7) 숨겨진 문자까지 눈에 보이게 출력
# ==========================
print("\n==========================================")
print("📌 STEP 7 — 숨겨진 문자 유니코드 코드값 확인")
print("==========================================")

def visualize(s):
    return " ".join(hex(ord(c)) for c in s)

sample_bad = df.loc[parsed_clean.isna(), time_col].head(5).astype(str)

print("\n[숨겨진 문자 분석 — 파싱 실패 줄]")
for v in sample_bad:
    print(v, "  →  ", visualize(v))


print("\n완료.")
