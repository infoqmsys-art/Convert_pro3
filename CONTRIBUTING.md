# 기여 가이드

코드 패치·버그 수정·기능 제안 모두 환영합니다. 아래 절차를 따라 주세요.

## 브랜치 전략

```
main        ← 안정 릴리즈 (직접 push 금지)
develop     ← 통합 개발 브랜치
feature/*   ← 새 기능 (예: feature/chart-zoom)
fix/*       ← 버그 수정 (예: fix/scheduler-duplicate)
```

## 패치 절차

1. **저장소 Fork** → 본인 GitHub 계정으로 Fork합니다.

2. **브랜치 생성**
   ```bash
   git checkout -b fix/버그설명
   ```

3. **설정 파일 준비** (처음 한 번만)
   ```bash
   copy config.example.json config.json
   copy web_auth.example.json web_auth.json
   ```

4. **코드 수정** — 아래 코딩 규칙을 따라 주세요.

5. **커밋**
   ```bash
   git commit -m "fix: 스케줄러 중복 실행 방지 조건 수정"
   ```

6. **Pull Request** — `develop` 브랜치 대상으로 PR을 열어주세요.

## 커밋 메시지 규칙

| 접두어 | 용도 |
|--------|------|
| `feat:` | 새 기능 |
| `fix:` | 버그 수정 |
| `refactor:` | 동작 변경 없는 코드 정리 |
| `docs:` | 문서만 변경 |
| `chore:` | 버전 범프, 빌드 설정 등 |

## 코딩 규칙

### 핵심 원칙
- **UI → App → Core** 단방향 의존성을 유지합니다.
  - `MainUI`는 반드시 `self.app`을 통해 요청합니다.
  - `Core` 모듈(`FileProcessor`, `TreeManager` 등)은 UI에 직접 접근하지 않습니다.

### 스레드 안전성
- 공유 상태(`config.json`, `management.json` 등) 수정 시 반드시 Lock을 사용합니다.
- Tkinter 위젯 업데이트는 반드시 메인 스레드에서, 또는 `root.after(0, fn)`으로 예약합니다.

### 파일 I/O
- JSON 파일 저장은 `temp → os.replace()` 패턴으로 원자적으로 처리합니다.
- 파일 핸들은 `with` 문으로 열어 자동 해제합니다.

### 로그
- `self.logger.log("메시지", level="INFO")` 형식을 사용합니다.
- `print()` 직접 사용은 지양합니다.

## 민감 정보 주의사항

> **절대 커밋 금지 파일**
> - `config.json` — 실제 업체·현장 데이터
> - `web_auth.json` — 로그인 비밀번호
> - `management.json` — 현장 관리 정보
> - `logs/` — 운영 로그

`.gitignore`에 이미 등록되어 있으나, PR 전에 `git status`로 반드시 확인하세요.

## 버전 관리

버전은 `version.py`에서만 수정합니다.

```python
VERSION_MAJOR = 2
VERSION_MINOR = 0
VERSION_PATCH = 59   # 패치 수정 시 이 숫자만 올림
```

- 버그 수정 → `VERSION_PATCH` +1
- 새 기능 → `VERSION_MINOR` +1, `VERSION_PATCH` = 0
- 호환성 파괴 변경 → `VERSION_MAJOR` +1

## 문의

버그 리포트나 기능 제안은 GitHub Issues를 이용해 주세요.
