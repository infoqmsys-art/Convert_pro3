# 문서 목차

이 폴더가 Convert Pro의 **단일 문서 허브**입니다. 코드 추가·리팩터 전에 관련 문서를 먼저 갱신하는 것을 원칙으로 합니다.

## 전체 파이프라인

| 프로젝트 | 경로 | 하는 일 | 서버 |
|---|---|---|---|
| **Convert_pro3 (이 저장소)** | `C:\projects\Convert_pro3` | **아날로그 센서** 원본 → 변환본 CSV (`C:/DATA/Convertfile/...`) | 메인3 |
| File_Converter | `C:\projects\File_Converter` | 485 센서 원본 → 변환본 CSV | 메인5 |
| 수집기 | `C:\projects\QmWebCollector` | 변환본 CSV → 포털 DB | 메인3·메인5 |
| 웹포털 | `C:\projects\QMWebportal` | DB 값을 그대로 표시 | 웹 서버 |

형제 문서: [File_Converter/docs](../../File_Converter/docs/README.md) · [QMWebportal/docs](../../QMWebportal/docs/README.md) · [QmWebCollector/README](../../QmWebCollector/README.md)

## 현행 문서

| 문서 | 내용 |
|------|------|
| [WORKFLOW_GUIDE.md](WORKFLOW_GUIDE.md) | 변환·운영 워크플로 |
| [FILL_SENSOR_COMPATIBILITY.md](FILL_SENSOR_COMPATIBILITY.md) | 누락보충 × 센서 모드 호환 |
| [UPDATE_GUIDE.md](UPDATE_GUIDE.md) | 자동 업데이트 사용·배포 |

## 에이전트 규칙

| 파일 | 내용 |
|------|------|
| [`.cursor/rules/project-map.mdc`](../.cursor/rules/project-map.mdc) | 원본→변환→수집→포털 전체 구성 |
| [`.cursor/rules/portal-handoff.mdc`](../.cursor/rules/portal-handoff.mdc) | Convert Pro ↔ 포털 (관수구·재변환 등) |
| [`.cursor/skills/gocheok-flowmeter-pdf-csv/SKILL.md`](../.cursor/skills/gocheok-flowmeter-pdf-csv/SKILL.md) | 고척 유량계 PDF→CSV |

## 아카이브

옛 데모·스캐폴딩·일회성 조사: [archive/](archive/README.md)

## 문서 작성 규칙

1. **한 주제 = 한 파일** — README에 장문 복붙하지 않음.
2. **경로·명령은 실제 코드와 일치** — 바뀌면 문서도 같이 수정.
3. **임시·완료된 조사 메모**는 `docs/archive/`로 옮김.
4. `config.json`은 git에 없음 — 수정 전 `config.json.bak-날짜시간` 백업.
