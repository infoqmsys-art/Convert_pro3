# convert-engine

Convert Pro 3의 **변환 코어**만 분리한 패키지입니다. Tk UI·모니터링·포털은 포함하지 않습니다.

## 설치 (개발)

```bash
cd engine
pip install -e .
```

## CLI (초기)

```bash
convert-engine --help
```

## 패키지 구조

```
engine/
  src/convert_engine/
    config/     config.json 로드·저장
    fill/       누락보충·슬롯
    sensors/    센서 모드 엔진
    pipeline/   파일 변환 파이프라인
    paths.py    변환본 경로 규칙
    io/         CSV tail 읽기
    cli/        명령줄 진입점
```

CP3(`Convert_pro3.py`)는 당분간 기존 `core/`를 사용합니다. 신규 개발·이전은 이 패키지 기준으로 진행합니다.
