---
name: gocheok-flowmeter-pdf-csv
description: >-
  Aligns 고척 유량계(1일1회) PDF cumulative values into hourly CSV F-4/F-5 columns.
  Use when the user provides a 유량계 PDF and a 1220262001.csv (or similar) and
  asks to match/fill flowmeter data by date, F-4, F-5, 고척, or 1일1회.
---

# 고척 유량계 PDF → CSV 맞추기

매주 유량계 PDF와 변환 CSV만 받으면 아래 스크립트를 실행한다. PDF를 직접 손으로 옮기지 않는다.

## 고정 매핑 (고척)

| 계측기 | CSV 인덱스 | 컬럼명 | PDF 값 |
|--------|------------|--------|--------|
| F-4 | 18 | AmountCH2 | 해당일 누적유량(m3) |
| F-5 | 19 | AmountCH3 | 해당일 누적유량(m3) |

- PDF는 날짜마다 00:00 1회 측정이다.
- CSV는 1시간 간격이다. **캘린더 날짜**가 같은 시각 행에 그날 PDF 누적값을 넣는다.
- 이미 맞춰진 구간은 건드리지 않는다. 마지막 일치일 D의 값을 다음날 **16:00까지** 유지한 것으로 보고, 그 시각 **이후**만 갱신한다.
  - 예: CSV가 2026-08-28 16:00까지 맞춰져 있으면 2026-08-28 17:00부터 채운다.
- PDF에 없는 이후 날짜(예: PDF 마지막 9/10, CSV가 9/11)는 마지막 PDF 누적값을 그대로 유지한다.
- F-2 / AmountCH4는 기본으로 건드리지 않는다.

## 실행

프로젝트 루트에서:

```bash
python tools/flowmeter_pdf_fill.py --pdf "<유량계 PDF>" --csv "<1220262001.csv>" --dry-run
```

드라이런 결과가 맞으면 백업 후 원본에 반영:

```bash
python tools/flowmeter_pdf_fill.py --pdf "<유량계 PDF>" --csv "<1220262001.csv>"
```

원본을 유지하고 싶으면 `--no-inplace` → `*_filled.csv` 생성.

컷오프를 직접 지정할 때:

```bash
python tools/flowmeter_pdf_fill.py --pdf "<PDF>" --csv "<CSV>" --after "2026-08-28 16:00"
```

## 확인

1. dry-run의 `cutoff`가 사용자가 말한 마지막 맞춘 시각과 같은지.
2. 다음날 17:00부터 F-4/F-5가 PDF 그날 누적으로 바뀌는지.
3. PDF 마지막 날짜의 F-4/F-5가 CSV 해당일 전 구간에 들어갔는지.
4. cutoff 이전 행은 값이 그대로인지.

## 사용자에게 보고할 내용

- cutoff 시각
- 변경 행 수와 구간
- PDF 마지막 F-4 / F-5 날짜·값
- 저장 경로와 `.bak` 경로
