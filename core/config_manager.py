"""
===========================================================
[Convert_pro3] ConfigManager Module (최종 통합 구조)
-----------------------------------------------------------
📌 설계 의도 (Design Intent)

이 모듈은 Convert_pro3의 설정 파일(config.json)을
일관된 구조로 관리하는 기능 전용 Core 모듈이다.

✔ TreeManager / FileProcessor / SensorProcessor가 모두 공통으로
  사용하는 데이터 구조를 보장한다.

✔ 구조 정의:
   회사(Company, UI 그룹)
      └── 업체폴더(Folder, 실제 경로명)
            └── 로거파일(LoggerFile, CSV)
                  └── CH0~CH7 (채널 설정)

✔ config.json은 프로그램의 단일 설정 저장소이며
  이 모듈만이 읽기/저장/보정 책임을 진다.

채널 설정은 'mode + parameters' 구조를 따른다.

1. mode
- 채널이 수행할 동작을 의미한다.
- 예: PASS, OFFSET, SCALE, INITIAL, EL, CR, V, SET, COPY 등
- 하나의 채널에는 반드시 하나의 mode만 적용된다.

2. parameters
- mode 수행 시 참고하는 값들이다.
- mode에 따라 사용/미사용이 결정된다.

  - base    : 기준값 / 오프셋 값
  - scale   : 배율
  - initial : 초기 기준값
  - decimal : 출력 소수점 자리수 (후처리, mode 아님)

3. 주의사항
- 과거 config에서는 'offset'이라는 키를 mode 용도로 사용했으나,
  이는 명명 오류이며 개념적으로는 'mode'가 올바른 표현이다.
- 향후 config 구조는 'offset' 대신 'mode'를 기준으로 정리한다.

===========================================================
"""

import json
import os


DEFAULT_STRUCTURE = {
    "__version__": 1
}


class ConfigManager:
    """
    Convert_pro3의 설정 파일 관리 엔진.
    
    data 구조 예:
    {
        "__version__": 1,
        "새길이엔씨": {
            "SAEGL03504": {
                "__note__": "",
                "__absolute_path__": "C:/data/SAEGL03504",
                "1227998430.csv": {
                    "__fill_interval__": 0,
                    "__gen_interval__": 0,
                    "CH0": {...}, "CH1": {...}, ...
                }
            }
        }
    }
    """

    def __init__(self, path="config.json", logger=None):
        self.path = path
        self.logger = logger
        self.data = {}

        self.load()
        self._auto_correct_structure()
        self.save()

    # -----------------------------------------------------
    # Logging helper
    # -----------------------------------------------------
    def _log(self, msg, level="INFO"):
        if self.logger:
            self.logger.log(msg, level=level)
        else:
            print(f"[{level}] {msg}")

    # -----------------------------------------------------
    # Load / Save
    # -----------------------------------------------------
    def load(self):
        """config.json 로딩"""
        if not os.path.exists(self.path):
            self._log("config.json 없음 → 새 파일 생성.")
            self.data = DEFAULT_STRUCTURE.copy()
            self.save()
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            self._log("config.json 로딩 완료.")
        except Exception as e:
            self._log(f"config 로딩 실패: {e}", level="ERROR")
            self.data = DEFAULT_STRUCTURE.copy()

    def save(self):
        """config.json 저장"""
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            self._log("config 저장 완료.")
        except Exception as e:
            self._log(f"config 저장 실패: {e}", level="ERROR")

    # -----------------------------------------------------
    # Structure auto-fix
    # -----------------------------------------------------
    def _auto_correct_structure(self):
        """최소한의 필드 보정"""
        if "__version__" not in self.data:
            self.data["__version__"] = 1

    # -----------------------------------------------------
    # Ensure Functions
    # -----------------------------------------------------
    def ensure_company(self, company):
        """회사 노드 생성"""
        if company not in self.data:
            self.data[company] = {}
            self._log(f"[ConfigManager] 회사 생성: {company}")
        return self.data[company]

    def ensure_folder(self, company, folder, absolute_path=""):
        """업체폴더 노드 생성"""
        comp = self.ensure_company(company)

        if folder not in comp:
            comp[folder] = {
                "__note__": "",
                "__absolute_path__": absolute_path
            }
            self._log(f"[ConfigManager] 폴더 생성: {company}/{folder}")

        else:
            # absolute path 갱신
            if absolute_path and not comp[folder].get("__absolute_path__"):
                comp[folder]["__absolute_path__"] = absolute_path

        return comp[folder]

    def ensure_logger(self, company, folder, filename):
        """로거파일 노드 생성 + CH0~CH7 기본 생성"""
        folder_dict = self.ensure_folder(company, folder)

        if filename not in folder_dict:
            folder_dict[filename] = {
                "__fill_interval__": 0,
                "__gen_interval__": 0
            }

            # 정석 CH 구조 생성
            for ch in range(8):
                folder_dict[filename][f"CH{ch}"] = {
                    "offset": "PASS",
                    "base": "",
                    "scale": "",
                    "decimal": "",
                    "label": "",
                    "initial": ""
                }

            self._log(f"[ConfigManager] 파일 생성: {company}/{folder}/{filename}")

        return folder_dict[filename]

    # -----------------------------------------------------
    # Path 기반 접근
    # -----------------------------------------------------
    def get(self, path, default=None):
        """예: cfg.get('새길이엔씨.SAEGL03504.1227998430.csv.CH0')"""
        try:
            keys = path.split(".")
            d = self.data
            for k in keys:
                if k not in d:
                    return default
                d = d[k]
            return d
        except:
            return default

    def set(self, path, value):
        """예: cfg.set('새길이엔씨.SAEGL03504.__note__', '지중경사계 현장')"""
        keys = path.split(".")
        d = self.data

        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]

        d[keys[-1]] = value
        self.save()