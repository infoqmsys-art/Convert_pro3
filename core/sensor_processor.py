import random
import pandas as pd


class SensorProcessor:
    """
    Convert_pro2의 sensor_settings.py 내용을 기반으로,
    센서 타입별 데이터 생성 및 변환을 담당하는 엔진.
    """

    def __init__(self, logger=None):
        self.logger = logger

        # 자동 등록된 generate 함수들 저장될 dict
        self.SENSOR_GENERATORS = {}

        # 함수 등록
        self._register_builtin_generators()

    # ======================================================
    # 1) 내부 메서드: 자동 등록 데코레이터
    # ======================================================
    def register_generator(self, name):
        """센서 생성 함수를 자동 등록하는 데코레이터"""
        def decorator(func):
            self.SENSOR_GENERATORS[name.upper()] = func
            return func
        return decorator

    # ======================================================
    # 2) EL / CR / V / SET / SET_EL / BASE+RAND 등 등록
    # ======================================================
    def _register_builtin_generators(self):

        @self.register_generator("EL")
        def generate_EL(base, scale, df_old, df_new, col):
            """
            EL 센서 패턴:
            ±0.02 기본 랜덤, 드리프트 포함
            낮은 확률로 ±0.03, ±0.3 튀는 값 포함
            """
            values = []
            drift = 0.0

            for _ in range(len(df_new)):
                # 드리프트(작은 확률로 +0.001 or -0.001)
                if random.random() < 0.02:
                    drift += random.choice([0.001, -0.001])

                # 기본 랜덤 ±0.02
                noise = random.uniform(-0.02, 0.02)

                # 10% 확률 ±0.03
                if random.random() < 0.10:
                    noise += random.uniform(-0.03, 0.03)

                # 아주 낮은 확률로 ±0.3
                if random.random() < 0.01:
                    noise += random.uniform(-0.3, 0.3)

                values.append(base + drift + noise)

            return pd.Series(values, index=df_new.index)

        @self.register_generator("CR")
        def generate_CR(base, scale, df_old, df_new, col):
            """
            CR 센서: 누적 방식
            """
            values = []
            current_value = base

            pattern = [0, 0, 0, 0, 0, 0.001, 0.001, 0.002,
                       -0.001, -0.001, -0.002, 0, 0, 0, 0]

            for _ in range(len(df_new)):
                current_value += random.choice(pattern)
                values.append(current_value)

            return pd.Series(values, index=df_new.index)

        @self.register_generator("V")
        def generate_V(base, scale, df_old, df_new, col):
            """
            V 센서: 누적 X, 현재 값은 랜덤 패턴 중 하나 선택
            """
            pattern = [0, 0, 0, 0, 0, 0.011, 0.002, 0.007,
                       0.005, 0.002, 0.001, 0, 0]

            values = [base + random.choice(pattern) for _ in range(len(df_new))]

            return pd.Series(values, index=df_new.index)

        @self.register_generator("SET")
        def generate_SET(base, scale, df_old, df_new, col):
            """SET 방식: (원본값 - base)"""
            return (df_new[col] - base)

        @self.register_generator("SET_EL")
        def generate_SET_EL(base, scale, df_old, df_new, col):
            """SET_EL: SET 결과에 EL 노이즈 추가"""
            base_series = df_new[col] - base
            el_series = self.SENSOR_GENERATORS["EL"](
                base=0, scale=scale,
                df_old=df_old, df_new=df_new, col=col
            )
            return base_series + el_series

        @self.register_generator("BASE+RAND")
        def generate_BASE_RAND(base, scale, df_old, df_new, col):
            """BASE+RAND: base + 랜덤값 * scale"""
            values = []
            for _ in range(len(df_new)):
                noise = random.uniform(-scale, scale)
                values.append(base + noise)

            return pd.Series(values, index=df_new.index)

    # ======================================================
    # 3) 최종 실행 엔진
    # ======================================================
    def apply_sensor_mode(self, mode, base, scale, df_old, df_new, col):
        """
        mode: PASS, OFFSET, EL, CR, V, SET, SET_EL, ...
        base: 기준값
        scale: 노이즈 크기
        df_old: 기존 데이터프레임
        df_new: 새 변환본 데이터프레임
        col: 처리할 컬럼명
        """

        mode = (mode or "PASS").upper()

        if mode == "PASS":
            # 원본 값 그대로
            return df_new[col]

        if mode == "OFFSET":
            # (원본값 + base)
            return df_new[col] + float(base)

        # 나머지는 SENSOR_GENERATORS에 있음
        if mode in self.SENSOR_GENERATORS:
            return self.SENSOR_GENERATORS[mode](
                base=base,
                scale=scale,
                df_old=df_old,
                df_new=df_new,
                col=col
            )

        # 모르는 모드 → PASS 처리
        if self.logger:
            self.logger.log(f"Unknown sensor mode '{mode}' → PASS 처리", level="WARN")
        return df_new[col]
