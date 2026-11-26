# Convert Pro 3 고도화 개발 가이드

## 📋 프로젝트 목표

### 1. 계층 구조 확장
- **기존**: Company → Folder → File (3단계)
- **변경**: Company → **Site (가상)** → Folder → File (4단계)

### 2. 관리 효율화
- 미등록 파일 대기소(Buffer) 시스템
- 다중 선택 등록 기능

### 3. 성능 최적화
- 멀티스레딩 기반 대용량(180개 이상) 데이터 고속 변환
- ThreadPoolExecutor 활용

### 4. 안정성 강화
- 물리적 경로 상실 시 회색 처리(Ghosting)
- 경로 재지정 복구 기능

---

## 🏗️ 데이터 아키텍처

### 확장된 계층 구조

```
회사 (Company)
  └── 현장 (Site) - 가상 계층 (새로 추가)
        └── 폴더 (Folder) - 물리적 경로
              └── 파일 (File) - CSV 파일
                    └── 채널 설정 (CH0~CH7)
```

### config.json 구조 예시

```json
{
  "__version__": 2,
  "SAEGIL": {
    "현장A": {
      "__note__": "현장 비고",
      "SAEGL03504": {
        "__note__": "폴더 비고",
        "__absolute_path__": "C:/data/SAEGL03504",
        "__is_ghost__": false,
        "1227998453.csv": {
          "__order__": 1,
          "__fill_interval__": 10,
          "__gen_interval__": 0,
          "__note__": "파일 비고",
          "CH0": { ... },
          ...
        }
      }
    },
    "Default": {
      "__note__": "마이그레이션된 기본 현장",
      "OLD_FOLDER": { ... }
    }
  }
}
```

### 마이그레이션 규칙

**기존 config.json (version 1) 로드 시**:
1. `__version__`이 1이거나 없으면 마이그레이션 실행
2. 각 회사 아래에 "Default" 현장 생성
3. 기존 폴더들을 "Default" 현장으로 이동
4. `__version__`을 2로 업데이트
5. 모든 파일에 `__order__` 필드 추가 (기본값: 0)

**마이그레이션 코드 예시**:
```python
def migrate_v1_to_v2(self):
    if self.data.get("__version__", 1) >= 2:
        return
    
    for company, folders in list(self.data.items()):
        if company.startswith("__"):
            continue
        
        # Default 현장 생성
        if "Default" not in folders or not isinstance(folders.get("Default"), dict):
            self.data[company]["Default"] = {
                "__note__": "마이그레이션된 기본 현장"
            }
        
        # 기존 폴더들을 Default로 이동
        for folder_name, folder_data in list(folders.items()):
            if folder_name == "Default" or folder_name.startswith("__"):
                continue
            
            if isinstance(folder_data, dict) and any(
                k.endswith(".csv") for k in folder_data.keys()
            ):
                # 폴더가 파일을 포함하고 있으면 이동
                self.data[company]["Default"][folder_name] = folder_data
                del self.data[company][folder_name]
        
        # 파일에 __order__ 추가
        self._add_order_to_files(company, "Default")
    
    self.data["__version__"] = 2
    self.save()
```

---

## 🔧 핵심 기능 구현

### ① 미등록 파일 관리 시스템

#### ScannerManager 구현

**역할**: 등록된 물리 폴더 내 미등록 CSV 파일 스캔

**위치**: `core/scanner_manager.py`

**주요 메서드**:
```python
class ScannerManager:
    def __init__(self, config_manager, tree_manager, logger):
        self.config = config_manager
        self.tree = tree_manager
        self.logger = logger
        self.unregistered_files = []  # [(company, site, folder, filename, path, size, mtime), ...]
    
    def scan_all_folders(self):
        """모든 등록된 폴더를 스캔하여 미등록 파일 찾기"""
        self.unregistered_files = []
        
        for company, sites in self.config.data.items():
            if company.startswith("__"):
                continue
            
            for site_name, site_data in sites.items():
                if site_name.startswith("__") or not isinstance(site_data, dict):
                    continue
                
                for folder_name, folder_data in site_data.items():
                    if folder_name.startswith("__") or not isinstance(folder_data, dict):
                        continue
                    
                    abs_path = folder_data.get("__absolute_path__")
                    if not abs_path or not os.path.exists(abs_path):
                        continue
                    
                    # 폴더 내 CSV 파일 스캔
                    registered_files = set(
                        k for k in folder_data.keys() 
                        if k.endswith(".csv")
                    )
                    
                    try:
                        physical_files = [
                            f for f in os.listdir(abs_path) 
                            if f.lower().endswith(".csv")
                        ]
                        
                        for filename in physical_files:
                            if filename not in registered_files:
                                file_path = os.path.join(abs_path, filename)
                                stat = os.stat(file_path)
                                self.unregistered_files.append({
                                    "company": company,
                                    "site": site_name,
                                    "folder": folder_name,
                                    "filename": filename,
                                    "path": file_path,
                                    "size": stat.st_size,
                                    "mtime": datetime.fromtimestamp(stat.st_mtime)
                                })
                    except Exception as e:
                        self.logger.log(f"스캔 오류 {abs_path}: {e}", level="ERROR")
        
        return self.unregistered_files
    
    def add_files_to_site(self, company, site, file_list):
        """다중 파일을 특정 현장에 등록"""
        for file_info in file_list:
            folder = file_info["folder"]
            filename = file_info["filename"]
            
            # 파일 추가 (기존 로직 활용)
            self.tree.add_file(company, site, folder, filename)
            
            # __order__ 자동 할당 (현재 최대값 + 1)
            max_order = self._get_max_order(company, site, folder)
            file_cfg = self.config.data[company][site][folder][filename]
            file_cfg["__order__"] = max_order + 1
        
        self.config.save()
```

#### 미등록 파일 리스트 UI

**위치**: `ui/unregistered_files_ui.py`

**구성 요소**:
- TreeView 또는 Listbox (체크박스 포함)
- 컬럼: 선택, 파일명, 폴더, 수정일시, 크기
- 버튼: "현장 선택하여 등록", "새로고침"

**구현 예시**:
```python
class UnregisteredFilesUI:
    def __init__(self, root, app):
        self.root = root
        self.app = app
        self.scanner = ScannerManager(app.config, app.tree, app.logger)
        
        self.win = tk.Toplevel(root)
        self.win.title("미등록 파일 관리")
        
        # 체크박스 변수 저장
        self.check_vars = {}
        
        # TreeView with checkboxes
        self.tree = ttk.Treeview(
            self.win,
            columns=("selected", "filename", "folder", "mtime", "size"),
            show="tree headings"
        )
        
        # 등록 버튼
        ttk.Button(
            self.win,
            text="현장 선택하여 등록",
            command=self._on_register_selected
        ).pack()
    
    def refresh_list(self):
        """미등록 파일 목록 새로고침"""
        files = self.scanner.scan_all_folders()
        # TreeView 업데이트...
    
    def _on_register_selected(self):
        """선택된 파일들을 현장에 등록"""
        selected = [f for f, var in self.check_vars.items() if var.get()]
        if not selected:
            return
        
        # 현장 선택 다이얼로그
        site = self._select_site()
        if not site:
            return
        
        # 일괄 등록
        self.scanner.add_files_to_site(
            selected[0]["company"],
            site,
            selected
        )
```

---

### ② 경로 유효성 검사 (Ghosting)

#### Ghosting 시스템

**구현 위치**: `core/config_manager.py`, `ui/main_ui.py`

**검사 시점**:
1. 프로그램 시작 시
2. 새로고침 버튼 클릭 시
3. 폴더 추가/변경 시

**구현 로직**:
```python
def check_path_validity(self):
    """모든 폴더의 경로 유효성 검사 및 Ghosting 처리"""
    for company, sites in self.data.items():
        if company.startswith("__"):
            continue
        
        for site_name, site_data in sites.items():
            if site_name.startswith("__") or not isinstance(site_data, dict):
                continue
            
            for folder_name, folder_data in site_data.items():
                if folder_name.startswith("__") or not isinstance(folder_data, dict):
                    continue
                
                abs_path = folder_data.get("__absolute_path__")
                is_valid = abs_path and os.path.exists(abs_path)
                
                # Ghost 상태 업데이트
                folder_data["__is_ghost__"] = not is_valid
                
                # 파일도 Ghost 상태 상속
                for key in folder_data.keys():
                    if key.endswith(".csv"):
                        folder_data[key]["__is_ghost__"] = not is_valid
    
    self.save()

def restore_path(self, company, site, folder, new_path):
    """경로 재지정"""
    if company not in self.data or site not in self.data[company]:
        return False
    
    folder_data = self.data[company][site].get(folder)
    if not folder_data:
        return False
    
    folder_data["__absolute_path__"] = new_path
    folder_data["__is_ghost__"] = False
    
    # 파일 Ghost 상태도 해제
    for key in folder_data.keys():
        if key.endswith(".csv"):
            folder_data[key]["__is_ghost__"] = False
    
    self.save()
    return True
```

**UI 렌더링** (main_ui.py):
```python
def refresh_tree(self):
    # ... 기존 코드 ...
    
    for site_name, site_data in company_dict.items():
        # Ghost 현장 표시
        is_ghost = site_data.get("__is_ghost__", False)
        site_text = f"⚠️ {site_name}" if is_ghost else site_name
        
        site_id = self.tree.insert(
            "",
            "end",
            text=site_text,
            values=(site_note, "", "site", company, site_name, "", ""),
            tags=("ghost",) if is_ghost else ()
        )
        
        # ... 폴더/파일 렌더링 ...
    
    # Ghost 스타일 적용
    self.tree.tag_configure("ghost", foreground="#999999")
```

**우클릭 메뉴 추가** (context_menu.py):
```python
def popup(self, event):
    # ... 기존 코드 ...
    
    if node_type in ("folder", "file"):
        is_ghost = self.tree.set(iid, "is_ghost") == "True"
        if is_ghost:
            self.menu.add_command(
                label="경로 재지정",
                command=self._on_restore_path
            )
```

---

### ③ 멀티스레딩 변환

#### ThreadPoolExecutor 구현

**위치**: `Convert_pro3.py`

**변경 사항**:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class ConvertPro3App:
    def __init__(self):
        # ... 기존 코드 ...
        self.convert_lock = threading.Lock()  # 로그 출력용 락
        self.max_workers = 4  # 동시 변환 스레드 수
    
    def _thread_convert(self):
        """멀티스레딩 변환"""
        try:
            self.is_converting = True
            self._ui_call(self.ui.set_buttons_enabled, False)
            
            start = datetime.now()
            all_files = list(self.iter_config_files())
            total = len(all_files)
            
            converted = 0
            skipped = 0
            fill_applied = 0
            errors = []
            
            # ThreadPoolExecutor로 병렬 처리
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 모든 파일 변환 작업 제출
                future_to_file = {
                    executor.submit(
                        self._convert_single_file_safe,
                        company, folder, filename
                    ): (company, folder, filename)
                    for company, folder, filename in all_files
                }
                
                # 완료된 작업 처리
                for future in as_completed(future_to_file):
                    company, folder, filename = future_to_file[future]
                    try:
                        result = future.result()
                        if result == "converted":
                            converted += 1
                        elif result == "fill":
                            converted += 1
                            fill_applied += 1
                        else:
                            skipped += 1
                        
                        # 진행률 업데이트
                        progress = (converted + skipped) / total
                        status_msg = f"변환 중... {converted + skipped}/{total}"
                        self._ui_call(self.ui.update_status, status_msg, progress)
                        
                    except Exception as e:
                        errors.append((company, folder, filename, str(e)))
                        self._thread_safe_log(
                            f"변환 오류: {company}/{folder}/{filename} - {e}",
                            level="ERROR"
                        )
            
            # 결과 로깅
            elapsed = (datetime.now() - start).seconds
            self.logger.log(
                f"전체 처리 완료\n"
                f"- 대상 파일: {total}\n"
                f"- 실제 변환: {converted}\n"
                f"- 누락 보정 적용: {fill_applied}\n"
                f"- 스킵: {skipped}\n"
                f"- 오류: {len(errors)}\n"
                f"- 소요 시간: {elapsed}s",
                level="INFO"
            )
            
            self._ui_call(self.ui.update_status, "변환 완료", 1.0)
            self._ui_call(self.ui.refresh_tree)
            
        except Exception as e:
            self.logger.log(f"전체 변환 중 오류: {e}", level="ERROR")
        finally:
            self.is_converting = False
            self._ui_call(self.ui.set_buttons_enabled, True)
    
    def _convert_single_file_safe(self, company, folder, filename):
        """스레드 안전한 단일 파일 변환"""
        try:
            return self.file_processor.convert_file(company, folder, filename)
        except Exception as e:
            self._thread_safe_log(
                f"파일 변환 실패 {company}/{folder}/{filename}: {e}",
                level="ERROR"
            )
            return "error"
    
    def _thread_safe_log(self, message, level="INFO"):
        """스레드 안전한 로그 출력"""
        with self.convert_lock:
            self.logger.log(message, level=level)
            self._ui_call(self.ui.append_log, f"[{level}] {message}")
```

**ConfigManager Thread Safety**:
```python
class ConfigManager:
    def __init__(self, path="config.json", logger=None):
        # ... 기존 코드 ...
        self.save_lock = threading.Lock()
    
    def save(self):
        """Thread-safe 저장"""
        with self.save_lock:
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=4, ensure_ascii=False)
                self._log("config 저장 완료.")
            except Exception as e:
                self._log(f"config 저장 실패: {e}", level="ERROR")
```

---

### ④ 파일 점유 대응

**위치**: `core/file_processor.py`

**재시도 로직**:
```python
def convert_file(self, company, folder, filename):
    """파일 변환 (재시도 로직 포함)"""
    max_retries = 3
    retry_delay = 1  # 초
    
    for attempt in range(max_retries):
        try:
            # 변환 로직 실행
            return self._convert_file_internal(company, folder, filename)
        
        except PermissionError as e:
            if attempt < max_retries - 1:
                self.logger.log(
                    f"파일 점유 중... 재시도 {attempt + 1}/{max_retries} "
                    f"({company}/{folder}/{filename})",
                    level="WARN"
                )
                time.sleep(retry_delay)
                retry_delay *= 2  # 지수 백오프
            else:
                self.logger.log(
                    f"파일 변환 실패 (점유됨): {company}/{folder}/{filename}",
                    level="ERROR"
                )
                return "error"
        
        except Exception as e:
            self.logger.log(
                f"변환 오류: {company}/{folder}/{filename} - {e}",
                level="ERROR"
            )
            return "error"
    
    return "error"
```

---

## 🎨 UI/UX 구현

### ttkbootstrap 또는 CustomTkinter 적용

**선택 기준**:
- **ttkbootstrap**: 기존 ttk 위젯과 호환성 높음, 마이그레이션 용이
- **CustomTkinter**: 더 모던한 디자인, 하지만 대규모 리팩토링 필요

**권장**: ttkbootstrap (점진적 마이그레이션 가능)

**적용 예시**:
```python
# main_ui.py
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

class MainUI:
    def _build_ui(self):
        style = ttk.Style(theme="flatly")  # 또는 "cosmo", "litera" 등
        
        # 버튼 스타일
        convert_btn = ttk.Button(
            right_buttons,
            text="▶ 변환 실행",
            command=self.app.convert_now,
            bootstyle=PRIMARY,
            width=12
        )
```

### 시각적 피드백

**아이콘/배지 시스템**:
```python
# 트리뷰 렌더링 시
def refresh_tree(self):
    # ... 기존 코드 ...
    
    # 정상 파일
    file_id = self.tree.insert(
        folder_id,
        "end",
        text=f"✅ {filename}",
        values=(...),
        tags=("normal",)
    )
    
    # Ghost 파일
    if file_cfg.get("__is_ghost__"):
        file_id = self.tree.insert(
            folder_id,
            "end",
            text=f"⚠️ {filename}",
            values=(...),
            tags=("ghost",)
        )
    
    # 신규 파일 (미등록에서 등록된 경우)
    if file_cfg.get("__is_new__"):
        file_id = self.tree.insert(
            folder_id,
            "end",
            text=f"🔵 {filename}",
            values=(...),
            tags=("new",)
        )
    
    # 태그 스타일
    self.tree.tag_configure("normal", foreground="#2C3E50")
    self.tree.tag_configure("ghost", foreground="#999999")
    self.tree.tag_configure("new", foreground="#3498DB")
```

### __order__ 편집 기능

**ChannelSettingsUI에 추가**:
```python
# channel_settings_ui.py
def _build_file_options(self):
    # ... 기존 코드 ...
    
    # 순서 번호 입력
    order_frame = tk.Frame(self.win, bg="white")
    order_frame.pack(fill="x", padx=10, pady=5)
    
    tk.Label(order_frame, text="순서 번호:", bg="white").pack(side="left")
    self.order_var = tk.StringVar(value=str(file_cfg.get("__order__", 0)))
    order_entry = tk.Entry(order_frame, textvariable=self.order_var, width=10)
    order_entry.pack(side="left", padx=5)
    
    # 저장 시 order 업데이트
    def update_order():
        try:
            order = int(self.order_var.get())
            file_cfg["__order__"] = order
            self.tree.set_file_config(...)
            self.controller.ui.refresh_tree()  # 즉시 반영
        except ValueError:
            messagebox.showerror("오류", "순서 번호는 정수여야 합니다.")
```

---

## 📊 성능 최적화

### 대용량 처리 최적화

**180개 파일 기준 목표**:
- 전체 스캔: < 5초
- 전체 변환: < 60초 (멀티스레딩)
- UI 프리징: 없음

**최적화 전략**:
1. **비동기 스캔**: 스캔 작업을 별도 스레드에서 실행
2. **청크 단위 처리**: 파일을 배치로 나누어 처리
3. **진행률 캐싱**: 중간 결과를 메모리에 캐시

**구현 예시**:
```python
def scan_all_folders_async(self, callback):
    """비동기 스캔"""
    def scan_thread():
        files = self.scan_all_folders()
        self.root.after(0, lambda: callback(files))
    
    threading.Thread(target=scan_thread, daemon=True).start()
```

---

## ✅ 검수 기준

### 기능 검수
- [ ] 현장 레벨 추가 및 마이그레이션 정상 동작
- [ ] 미등록 파일 스캔 및 다중 등록 기능
- [ ] Ghost 상태 표시 및 경로 재지정
- [ ] 멀티스레딩 변환 (180개 파일 기준)
- [ ] 파일 점유 재시도 로직
- [ ] __order__ 정렬 및 편집

### 성능 검수
- [ ] 180개 파일 스캔 시 UI 프리징 없음
- [ ] 멀티스레딩 변환 시 로그 정상 출력
- [ ] 메모리 사용량 안정적 (< 500MB)

### 안정성 검수
- [ ] config.json 저장 시 Thread Lock 적용
- [ ] 예외 발생 시 전체 프로세스 중단 없음
- [ ] 깨진 행 발견 시 해당 행만 스킵

---

## 🚀 개발 단계별 계획

### Phase 1: 기본 구조 확장 (1-2일)
1. ConfigManager에 Site 레벨 추가
2. 마이그레이션 로직 구현
3. TreeManager 메서드 시그니처 변경

### Phase 2: UI 업데이트 (2-3일)
1. MainUI 트리뷰 4단계 구조 반영
2. 현장 추가 버튼 및 다이얼로그
3. __order__ 정렬 구현

### Phase 3: 미등록 파일 시스템 (2-3일)
1. ScannerManager 구현
2. UnregisteredFilesUI 구현
3. 다중 등록 기능

### Phase 4: Ghosting 시스템 (1-2일)
1. 경로 유효성 검사 로직
2. UI 회색 처리
3. 경로 재지정 기능

### Phase 5: 멀티스레딩 (2-3일)
1. ThreadPoolExecutor 적용
2. Thread-safe 로깅
3. 성능 테스트

### Phase 6: UI/UX 개선 (1-2일)
1. ttkbootstrap 적용
2. 아이콘/배지 시스템
3. __order__ 편집 기능

**총 예상 기간**: 9-15일

---

이 가이드는 Convert Pro 3의 고도화 개발을 위한 상세한 구현 지침을 제공합니다. 각 단계를 순차적으로 진행하며, 각 기능의 테스트와 검수를 철저히 수행해야 합니다.
