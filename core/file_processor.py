import os
import pandas as pd
from datetime import datetime
from typing import Optional


class FileProcessor:
    """
    단일 CSV 파일 변환을 담당하는 엔진.

    - 원본 CSV 읽기
    - timestamp 파싱
    - 기존 변환본(csv) 있으면 이어붙일 준비
    - 채널 설정(CH0~CH7)에 따라 sensor_processor 적용
    - 변환 결과를 Convertfile 폴더에 저장

    ⚠️ 1차 버전:
      - fill_interval(누락보충), gen_interval(주기 생성)은 아직 미구현 (TODO)
      - 원본 CSV에 'timestamp', 'CH0'~'CH7' 열이 있다고 가정
        → 나중에 Q~X, C~J 등 포맷 자동 인식 로직을 별도 단계에서 추가
    """

    def __init__(self, config, tree, sensor, logger, convert_root: Optional[str] = None):
        """
        config : ConfigManager 인스턴스
        tree   : TreeManager 인스턴스
        sensor : SensorProcessor 인스턴스
        logger : Logger 인스턴스
        convert_root : 변환 파일 저장 기본 폴더 (없으면 ./Convertfile 사용)
        """
        self.config = config
        self.tree = tree
        self.sensor = sensor
        self.logger = logger
        self.convert_root = convert_root or os.path.join(os.getcwd(), "Convertfile")

    # ======================================================
    #  public API
    # ======================================================
    def convert_file(self, company: str, folder: str, filename: str) -> None:
        """
        회사/폴더/파일 지정해서 변환 수행.
        """
        self.logger.log(f"[FileProcessor] 변환 시작: {company}/{folder}/{filename}")

        # 1) 설정 & 경로 확인
        file_cfg = self._get_file_config(company, folder, filename)
        if file_cfg is None:
            return

        source_path, dest_path = self._resolve_paths(company, folder, filename, file_cfg)
        if source_path is None or dest_path is None:
            return

        # 2) 원본 & 기존 변환본 읽기
        df_src = self._read_source_csv(source_path)
        if df_src is None or df_src.empty:
            self.logger.log(f"[FileProcessor] 원본 CSV가 비어있음 → 변환 중단", level="WARN")
            return

        df_src = self._ensure_parsed_time(df_src)

        df_exist = self._read_existing_csv(dest_path)
        if df_exist is not None and not df_exist.empty:
            df_exist = self._ensure_parsed_time(df_exist)
            last_time = df_exist["_parsed_time"].max()
            # 기존 변환 마지막 시간 이후 데이터만 신규로 사용
            df_new = df_src[df_src["_parsed_time"] > last_time].copy()
        else:
            df_exist = None
            df_new = df_src.copy()

        if df_new.empty:
            self.logger.log("[FileProcessor] 신규 데이터 없음 → 변환할 행이 없습니다.")
            return

        # 3) (TODO) fill_interval / gen_interval 처리 자리
        fill_interval = file_cfg.get("__fill_interval__", 0) or 0
        gen_interval = file_cfg.get("__gen_interval__", 0) or 0

        if fill_interval:
            self.logger.log(f"[FileProcessor] fill_interval={fill_interval} (아직 미구현, pass)")
            # TODO: fill_data(df_new, df_exist, fill_interval)

        if gen_interval:
            self.logger.log(f"[FileProcessor] gen_interval={gen_interval} (아직 미구현, pass)")
            # TODO: create_data(...)

        # 4) 채널(CH0~CH7) 변환 적용
        df_new = self._apply_channels(company, folder, filename, file_cfg, df_src, df_new)

        # 5) 기존 변환본과 합치기
        if df_exist is not None and not df_exist.empty:
            df_result = pd.concat([df_exist, df_new], ignore_index=True)
            # 중복 timestamp 제거 (마지막 값 우선)
            df_result = self._drop_duplicate_parsed_time(df_result)
        else:
            df_result = df_new

        # 6) 저장
        self._save_converted(df_result, dest_path)
        self.logger.log(f"[FileProcessor] 변환 완료 → {dest_path}")

    # ======================================================
    #  config / path helpers
    # ======================================================
    def _get_file_config(self, company: str, folder: str, filename: str) -> Optional[dict]:
        data = self.config.data
        try:
            file_cfg = data[company][folder][filename]
            if not isinstance(file_cfg, dict):
                raise KeyError("파일 설정이 dict 형식이 아닙니다.")
            return file_cfg
        except KeyError:
            self.logger.log(
                f"[FileProcessor] 설정 없음: {company}/{folder}/{filename}",
                level="ERROR",
            )
            return None

    def _resolve_paths(self, company: str, folder: str, filename: str, file_cfg: dict):
        folder_cfg = self.config.data.get(company, {}).get(folder, {})
        abs_path = folder_cfg.get("__absolute_path__")

        if not abs_path:
            self.logger.log(
                f"[FileProcessor] __absolute_path__ 누락 → 원본 경로 알 수 없음: {company}/{folder}",
                level="ERROR",
            )
            return None, None

        source_path = os.path.join(abs_path, filename)
        if not os.path.exists(source_path):
            self.logger.log(
                f"[FileProcessor] 원본 CSV 없음: {source_path}",
                level="ERROR",
            )
            return None, None

        dest_dir = os.path.join(self.convert_root, company, folder)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, filename)

        return source_path, dest_path

    # ======================================================
    #  CSV I/O
    # ======================================================
    def _read_source_csv(self, path: str) -> Optional[pd.DataFrame]:
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            self.logger.log(f"[FileProcessor] 원본 CSV 읽기 성공: {path}")
            return df
        except Exception as e:
            self.logger.log(f"[FileProcessor] 원본 CSV 읽기 실패: {e}", level="ERROR")
            return None

    def _read_existing_csv(self, path: str) -> Optional[pd.DataFrame]:
        if not os.path.exists(path):
            return None
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            self.logger.log(f"[FileProcessor] 기존 변환 CSV 읽기 성공: {path}")
            return df
        except Exception as e:
            self.logger.log(f"[FileProcessor] 기존 변환 CSV 읽기 실패: {e}", level="ERROR")
            return None

    # ======================================================
    #  timestamp / index helpers
    # ======================================================
    def _ensure_parsed_time(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        df에 '_parsed_time' 컬럼이 없으면,
        첫 번째 컬럼을 timestamp로 가정하고 파싱해서 만든다.
        """
        if "_parsed_time" in df.columns:
            return df

        # 첫 번째 컬럼 이름
        time_col = df.columns[0]
        try:
            parsed = pd.to_datetime(df[time_col], errors="coerce")
            df = df.copy()
            df["_parsed_time"] = parsed
            df = df[~df["_parsed_time"].isna()].reset_index(drop=True)
            self.logger.log(f"[FileProcessor] _parsed_time 생성 완료 (col='{time_col}')")
        except Exception as e:
            self.logger.log(
                f"[FileProcessor] timestamp 파싱 실패 (col='{time_col}'): {e}",
                level="ERROR",
            )
        return df

    def _drop_duplicate_parsed_time(self, df: pd.DataFrame) -> pd.DataFrame:
        if "_parsed_time" not in df.columns:
            return df
        df = df.sort_values("_parsed_time")
        df = df.drop_duplicates(subset="_parsed_time", keep="last")
        return df.reset_index(drop=True)

    # ======================================================
    #  채널 변환
    # ======================================================
    def _apply_channels(
        self,
        company: str,
        folder: str,
        filename: str,
        file_cfg: dict,
        df_src: pd.DataFrame,
        df_new: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        CH0~CH7 설정을 읽어서 sensor_processor.apply_sensor_mode 적용.
        ⚠️ 1차 버전: 원본 CSV에 'CH0'~'CH7' 열이 이미 존재한다고 가정.
        """
        df_new = df_new.copy()

        for ch in range(8):
            ch_key = f"CH{ch}"
            ch_cfg = file_cfg.get(ch_key, {})

            mode = (ch_cfg.get("offset") or "PASS").upper()  # 기존 config.json의 'offset' 키 사용
            base = ch_cfg.get("base", "")
            scale = ch_cfg.get("scale", 0)

            # base, scale 숫자 변환
            try:
                base_val = float(base) if base not in ("", None) else 0.0
            except Exception:
                base_val = 0.0

            try:
                scale_val = float(scale) if scale not in ("", None) else 0.0
            except Exception:
                scale_val = 0.0

            src_col = ch_key  # ⚠️ 현재는 'CH0'~'CH7' 열이 있다고 가정

            if src_col not in df_new.columns:
                # 원본에 열이 없으면 PASS
                self.logger.log(
                    f"[FileProcessor] 열 없음 → CH{ch}({src_col}) PASS 처리",
                    level="WARN",
                )
                continue

            self.logger.log(
                f"[FileProcessor] CH{ch} 변환 시작: mode={mode}, base={base_val}, scale={scale_val}"
            )

            try:
                new_series = self.sensor.apply_sensor_mode(
                    mode=mode,
                    base=base_val,
                    scale=scale_val,
                    df_old=df_src,
                    df_new=df_new,
                    col=src_col,
                )
                # 결과 열 이름은 CH0~CH7 그대로 사용
                df_new[src_col] = new_series
            except Exception as e:
                self.logger.log(
                    f"[FileProcessor] CH{ch} 변환 실패: {e}",
                    level="ERROR",
                )

        return df_new

    # ======================================================
    #  저장
    # ======================================================
    def _save_converted(self, df: pd.DataFrame, path: str) -> None:
        try:
            df.to_csv(path, index=False, encoding="utf-8-sig")
            self.logger.log(f"[FileProcessor] CSV 저장 완료: {path}")
        except Exception as e:
            self.logger.log(f"[FileProcessor] CSV 저장 실패: {e}", level="ERROR")
