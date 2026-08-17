"""
ALPHA PROJECT - 1~2티어 프로토타입
================================================
로블록스 게임 "Industrialist(산업가)"와 Mindustry에서 영감을 받은
오리지널 3D 공장 건설 시뮬레이션 (pygame + PyOpenGL 사용)

※ 원작의 정확한 자산/수치를 복제하지 않고, 같은 장르의 핵심 구조
   (채굴 -> 제련/정제 -> 가공 -> 판매, 전력 시스템, 오염 시스템)를 참고해
   새로 설계한 오리지널 콘텐츠입니다.

조작법
------
  W / A / S / D   : 이동
  Shift            : 달리기
  마우스           : 시점 회전
  B                : 건물 메뉴 열기/닫기 (메뉴에서 마우스로 건물 클릭 선택)
  F                : (아이템 필터를 조준한 상태) 통과시킬 아이템 선택 메뉴 열기/닫기
  G                : (드론 수송기/드론 페이로드를 조준한 상태) 운반/수신할 아이템 선택 메뉴 열기/닫기
  T                : (데이터 파워 노드를 조준한 상태) 석탄 화력 발전소 출력 단계(저/표준/고) 순환
  좌클릭           : (메뉴 밖) 선택한 건물을 앞쪽 칸에 배치 / (메뉴 안) 건물 선택
  우클릭           : 앞쪽 칸의 건물 철거
  ESC              : 메뉴가 열려있으면 닫기, 아니면 종료
"""

import math
import random
import sys

import pygame
from OpenGL.GL import *

# ----------------------------------------------------------------------
# 기본 설정
# ----------------------------------------------------------------------
WIDTH, HEIGHT = 1500,900
CELL = 2.0
GRID_RANGE = 40             # -40..40 칸 (맵을 예전보다 넓힘)
PLACE_DISTANCE = 3.0
# 이 거리(격자 칸)보다 멀리 있는 건물은 그리지 않는다. 안개가 짙어 어차피 잘 안 보이는
# 구간이라 시각적 손해는 거의 없고, 공장이 커질수록 프레임이 크게 좋아진다.
DRAW_DISTANCE = 46

MOVE_SPEED = 6.0
SPRINT_MULT = 1.8
MOUSE_SENS = 0.15

ITEM_SPEED = 1.6
CAPTURE_RADIUS = CELL * 0.6    # 아이템이 가공 기계 중심에 얼마나 가까워야 "도착"으로 인정할지
                                 # (그리드 반올림 경계보다 커야 아이템이 영원히 멈추지 않음)

DIRS = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
# 방향 벡터 -> glRotatef용 Y축 회전각. E(기본 모델 방향)=0도 기준으로 시계방향 계산.
DIR_TO_ANGLE = {(1, 0): 0.0, (0, -1): 90.0, (-1, 0): 180.0, (0, 1): 270.0}

# ---- 건물 정의 (1티어 + 2티어) ------------------------------------------
BUILD_ORDER = [
    "core",
    "coal_miner", "copper_miner", "iron_miner", "lead_miner",
    "sand_miner", "wood_cutter", "blast_furnace",
    "furnace", "press", "conveyor", "wire", "pipe", "solar", "coal_gen", "depot",
    "conveyor_3way", "conveyor_4way", "pipe_3way", "pipe_4way",
    "conveyor_crossroad", "pipe_crossroad", "hybrid_crossroad",
    "water_pump", "water_treatment",
    "firebox", "boiler", "turbine",
    "oil_pump", "refinery", "chem_plant", "molder", "oil_gen",
    "oil_classifier", "diesel_refiner", "filter", "diesel_gen",
    "gas_extractor", "condenser", "gas_refiner", "gas_turbine",
    "gas_input_block", "turbine_controller_block", "turbine_crankshaft_block",
    "gas_cylinder_block", "exhaust_pump_block", "intake_pump_block",
    "silicon_refiner", "alloy_furnace", "circuit_assembler",
    "assembly_plant", "battery_plant", "coal_power_plant",
    "scrubber", "research", "thermal_plant",
    "power_meter", "transformer", "battery_cell", "hv_battery",
    "item_filter",
    "drone_transporter", "drone_payload",
    "coal_feeder", "heat_exchanger", "exhaust_stack", "data_power_node",
    "modular_turbine", "turbine_hp_stage", "turbine_ip_stage", "turbine_lp_stage",
    "turbine_generator_block",
    "lathe", "mineshaft_drill", "fragment_processor", "ore_refiner",
    "heavy_oil_separator", "oxidation_chamber", "chemical_reactor",
    "electrolyzer", "air_separator",
    "steam_cracker", "plastic_refinery",
]
# 건물 메뉴 편성 = 티어. 아래 티어는 감이 아니라 게임 데이터에서 계산해 배정했다:
#   * 복잡도 = 그 설비를 "처음 돌릴 수 있게 되는" 시점의 생산 체인 깊이
#              (원료 채취 0단계 -> 가공할수록 +1. 다목적 설비는 가장 이른 용도 기준)
#   * 가치   = 산출물 최고 판매가, 발전 설비는 발전량을 가치로 환산
#   * 가격이 비싼 대형 설비와, 본체가 있어야 의미가 없는 부품군은 본체 티어를 따라간다
# 즉 "복잡한 설비 + 값비싼 산출물 -> 높은 티어, 단순하고 값싼 것 -> 낮은 티어".
BUILD_GROUPS = [
    # 1티어 - 원료를 캐고 나르는 기초 설비 (복잡도 0, 산출 가치 최하)
    ("1티어 · 채취", ["coal_miner", "copper_miner", "iron_miner", "lead_miner",
                    "sand_miner", "wood_cutter", "water_pump", "oil_pump", "gas_extractor"]),
    ("1티어 · 운반", ["conveyor", "conveyor_3way", "conveyor_4way", "pipe", "pipe_3way", "pipe_4way",
                    "conveyor_crossroad", "pipe_crossroad", "hybrid_crossroad", "wire"]),
    ("1티어 · 기초", ["core", "depot", "solar", "coal_gen", "power_meter"]),

    # 2티어 - 캔 것을 한 번 가공하는 단계 (복잡도 1)
    ("2티어 · 1차 가공", ["furnace", "press", "water_treatment", "firebox", "boiler",
                       "refinery", "oil_classifier", "heavy_oil_separator",
                       "electrolyzer", "air_separator"]),
    ("2티어 · 전력망", ["transformer", "battery_cell", "item_filter", "scrubber"]),

    # 3티어 - 가공품을 다시 조합하는 단계 (복잡도 2~3)
    ("3티어 · 화학·정제", ["chemical_reactor", "oxidation_chamber", "condenser", "gas_refiner",
                        "diesel_refiner", "filter", "molder", "silicon_refiner", "alloy_furnace"]),
    ("3티어 · 발전", ["turbine", "oil_gen", "diesel_gen", "thermal_plant", "gas_turbine"]),
    ("3티어 · 가스터빈 부품", ["gas_input_block", "turbine_controller_block", "turbine_crankshaft_block",
                          "gas_cylinder_block", "exhaust_pump_block", "intake_pump_block"]),
    ("3티어 · 운송·연구", ["drone_transporter", "drone_payload", "research"]),

    # 4티어 - 여러 체인이 합쳐지는 산업 규모 설비 (복잡도 3~5 / 고가)
    ("4티어 · 고급 제조", ["blast_furnace", "circuit_assembler", "battery_plant",
                        "steam_cracker", "plastic_refinery", "chem_plant"]),
    ("4티어 · 석탄 화력", ["coal_power_plant", "coal_feeder", "heat_exchanger",
                        "exhaust_stack", "data_power_node"]),
    ("4티어 · 대용량 축전", ["hv_battery"]),

    # 5티어 - 체인 최심부. 최고가 산출물이거나 게임 내 최강 발전 (복잡도 4~7)
    ("5티어 · 심층 채굴", ["mineshaft_drill", "lathe", "fragment_processor", "ore_refiner"]),
    ("5티어 · 최종 조립", ["assembly_plant"]),
    ("5티어 · 모듈러 터빈", ["modular_turbine", "turbine_hp_stage", "turbine_ip_stage",
                         "turbine_lp_stage", "turbine_generator_block"]),
]
BUILD_LABEL = {
    "core": "코어",
    "coal_miner": "석탄 채굴기", "copper_miner": "구리 채굴기", "iron_miner": "철 채굴기",
    "lead_miner": "납 채굴기", "sand_miner": "모래 채굴기",
    "wood_cutter": "벌목기", "blast_furnace": "폭발로",
    "furnace": "제련로", "press": "압연기",
    "conveyor": "컨베이어", "wire": "와이어", "pipe": "파이핑",
    "solar": "태양광 패널", "coal_gen": "석탄 발전기",
    "depot": "판매소",
    "conveyor_3way": "3방향 분배기", "conveyor_4way": "4방향 분배기",
    "pipe_3way": "3방향 파이프 분배기", "pipe_4way": "4방향 파이프 분배기",
    "conveyor_crossroad": "컨베이어 교차로", "pipe_crossroad": "파이프 교차로",
    "hybrid_crossroad": "유체-고체 교차로",
    "water_pump": "물 펌프", "water_treatment": "물 처리기",
    "firebox": "파이어박스", "boiler": "보일러", "turbine": "터빈",
    "oil_pump": "오일 펌프", "refinery": "정유소", "chem_plant": "플라스틱 생산 시설",
    "molder": "사출 성형기", "oil_gen": "오일 발전기",
    "oil_classifier": "원유 분류기", "diesel_refiner": "디젤 정제기",
    "filter": "필터", "diesel_gen": "모듈 디젤 발전기",
    "gas_extractor": "가스 추출기", "condenser": "콘덴서",
    "gas_refiner": "가스 정제기", "gas_turbine": "가스 터빈",
    "gas_input_block": "가스 인풋", "turbine_controller_block": "터빈 컨트롤러",
    "turbine_crankshaft_block": "터빈 크랭크축", "gas_cylinder_block": "가스 실린더",
    "exhaust_pump_block": "매연 배기 펌프", "intake_pump_block": "공기 흡기펌프",
    "silicon_refiner": "실리콘 정제기", "alloy_furnace": "합금로",
    "circuit_assembler": "회로 조립기",
    "assembly_plant": "조립 공장", "battery_plant": "배터리 공장",
    "scrubber": "정화기", "research": "연구소", "thermal_plant": "화력발전소",
    "coal_power_plant": "석탄 화력 발전소",
    "power_meter": "전력 속도 카운터", "transformer": "변압기",
    "battery_cell": "배터리 (1MMF)", "hv_battery": "고압 배터리 (1GMMF)",
    "item_filter": "아이템 필터",
    "drone_transporter": "드론 수송기", "drone_payload": "드론 페이로드",
    "coal_feeder": "석탄 공급기", "heat_exchanger": "열교환기",
    "exhaust_stack": "배기탑", "data_power_node": "데이터 파워 노드",
    "modular_turbine": "모듈러 터빈",
    "turbine_hp_stage": "고압 터빈 단", "turbine_ip_stage": "중압 터빈 단",
    "turbine_lp_stage": "저압 터빈 단", "turbine_generator_block": "터빈 제너레이터",
    "lathe": "선반", "mineshaft_drill": "마인샤프트 드릴", "fragment_processor": "파편 분류기",
    "ore_refiner": "광석 정제기",
    "heavy_oil_separator": "중유 분리기", "oxidation_chamber": "산화실",
    "chemical_reactor": "화학 반응기",
    "electrolyzer": "전해조", "air_separator": "공기 분리기",
    "steam_cracker": "스팀 크래킹 플랜트", "plastic_refinery": "플라스틱 정제소",
}
# 건물 메뉴에서 우클릭으로 여는 상세 정보 패널에 쓰는 한 줄 설명.
BUILD_DESC = {
    "core": "모든 아이템을 받아 보관하는 중앙 저장소. 여러 개를 지어도 창고는 하나로 공유된다.",
    "coal_miner": "어디에 설치하든 자동으로 석탄을 채굴한다.",
    "copper_miner": "어디에 설치하든 자동으로 구리 원석을 채굴한다.",
    "iron_miner": "어디에 설치하든 자동으로 철 원석을 채굴한다.",
    "lead_miner": "어디에 설치하든 자동으로 납 광석을 채굴한다.",
    "sand_miner": "어디에 설치하든 자동으로 모래를 채굴한다.",
    "wood_cutter": "어디에 설치하든 자동으로 나무를 벌목한다.",
    "blast_furnace": "재료에 따라 다른 걸 만드는 다목적 용광로. "
                      "철 주괴+석탄/목탄→강철 주괴, 모래+석탄/목탄→실리콘, "
                      "납 광석+석탄/목탄→납 주괴, 나무+석탄/목탄→목탄.",
    "furnace": "원석을 녹여 주괴로 만든다.",
    "press": "주괴를 눌러 판재로 가공한다.",
    "conveyor": "아이템을 정해진 방향으로 실어 나른다.",
    "wire": "인접한 전력 건물끼리 전력망으로 연결한다.",
    "pipe": "액체/기체 아이템만 흐르게 하는 배관 (고체는 통과 못함).",
    "solar": "소모 전력 없이 전력을 꾸준히 공급한다.",
    "coal_gen": "석탄을 태워 전력을 생산한다.",
    "depot": "위에 도착한 아이템을 자동으로 판매해 돈으로 바꾼다.",
    "conveyor_3way": "들어온 아이템을 전방·좌·우 세 방향으로 번갈아 나눠 보낸다.",
    "conveyor_4way": "들어온 아이템을 사방으로 번갈아 나눠 보낸다(들어온 쪽으로는 되돌리지 않음).",
    "pipe_3way": "액체/기체를 전방·좌·우 세 방향으로 번갈아 나눠 보낸다.",
    "pipe_4way": "액체/기체를 사방으로 번갈아 나눠 보낸다(들어온 쪽으로는 되돌리지 않음).",
    "conveyor_crossroad": "서로 다른 두 컨베이어 흐름이 섞이지 않고 그대로 가로질러 지나간다.",
    "pipe_crossroad": "서로 다른 두 파이프 흐름이 섞이지 않고 그대로 가로질러 지나간다.",
    "hybrid_crossroad": "컨베이어와 파이프가 서로 간섭 없이 한 칸에서 교차한다.",
    "water_pump": "어디에 설치하든 물을 퍼올린다.",
    "water_treatment": "물을 정수로 정제한다.",
    "firebox": "물과 석탄을 넣으면 온수를 만든다.",
    "boiler": "온수를 끓여 증기로 바꾼다.",
    "turbine": "증기를 태워 전력을 생산한다.",
    "oil_pump": "어디에 설치하든 원유를 퍼올린다.",
    "refinery": "원유를 정제해 연료유로 만든다.",
    "chem_plant": "PTA와 MEG를 합쳐 플라스틱 펠릿을 만든다 (플라스틱 체인의 최종 단계).",
    "molder": "플라스틱 펠릿을 성형해 플라스틱 케이스로 만든다.",
    "oil_gen": "연료유를 태워 강한 전력을 생산한다 (오염이 큼).",
    "oil_classifier": "원유를 나프타와 디젤 원료로 분리한다.",
    "diesel_refiner": "디젤 원료를 디젤로 정제한다.",
    "filter": "디젤을 걸러 정제 디젤로 만든다.",
    "diesel_gen": "정제 디젤을 태워 전력을 생산한다.",
    "gas_extractor": "어디에 설치하든 천연가스를 뽑아낸다.",
    "condenser": "천연가스를 잔류물+물+증류가스로 분리한다.",
    "gas_refiner": "증류가스를 잔류물+정제가스로 정제한다.",
    "gas_turbine": "정제가스를 태워 전력을 생산한다. 부품을 사방으로 붙이면 강화된다.",
    "gas_input_block": "정제가스를 파이프로 받아, 인접한 가스 터빈(들)에 나눠 공급한다.",
    "turbine_controller_block": "가스 터빈에 붙이면 발전량이 늘고 오염이 준다.",
    "turbine_crankshaft_block": "가스 터빈에 붙이면 발전량이 크게 늘어난다.",
    "gas_cylinder_block": "가스 터빈에 붙이면 가스 1개당 연소 시간이 늘어난다.",
    "exhaust_pump_block": "가스 터빈에 붙이면 오염이 줄어든다.",
    "intake_pump_block": "가스 터빈에 붙이면 발전량이 늘어난다.",
    "silicon_refiner": "실리콘을 실리콘 웨이퍼로 정제한다.",
    "alloy_furnace": "철 주괴와 석탄을 합쳐 강철 주괴를 만든다.",
    "circuit_assembler": "구리판과 실리콘 웨이퍼로 회로기판을 만든다.",
    "assembly_plant": "회로기판+강철 주괴+플라스틱 케이스로 고급 모듈을 만든다.",
    "battery_plant": "구리판과 플라스틱 펠릿으로 배터리를 만든다.",
    "coal_power_plant": "석탄을 태워 대량의 전력을 생산하는 4티어 발전소. 부품을 사방으로 붙이면 강화된다.",
    "scrubber": "전력으로 오염을 꾸준히 줄인다.",
    "research": "전력으로 연구 포인트(RP)를 생산한다. RP 100마다 모든 건물의 가동률이 +5%씩 올라간다(최대 +100%).",
    "thermal_plant": "석탄을 태워 전력을 생산한다 (오염이 큼).",
    "power_meter": "연결된 전력망의 순 발전량(+)/부족량(-)을 게이지로 보여준다.",
    "transformer": "와이어 없이도 가까운 거리 이내 변압기끼리 무선으로 전력망을 이어준다.",
    "battery_cell": "남는 전력을 저장했다가 부족할 때 방출하는 소형 축전지.",
    "hv_battery": "배터리(1MMF)보다 10배 큰 용량의 대형 축전지.",
    "item_filter": "조준하고 F로 지정한 아이템만 통과시키고 나머지는 걸러낸다.",
    "drone_transporter": "조준하고 G로 지정한 아이템을, 컨베이어 없이 맵 어디서든 찾아 드론 페이로드로 실어 나른다.",
    "drone_payload": "조준하고 G로 지정한 아이템을 드론에게 받아, 컨베이어처럼 자기 방향으로 다시 흘려보낸다.",
    "coal_feeder": "석탄 화력 발전소에 사방으로 붙이면 발전량이 늘어난다.",
    "heat_exchanger": "전력만 연결되어 있으면 물을 고압 증기로 바꾼다.",
    "exhaust_stack": "석탄 화력 발전소에 사방으로 붙이면 오염이 크게 줄어든다.",
    "data_power_node": "조준하고 T로, 사방으로 붙은 석탄 화력 발전소의 출력 단계(저/표준/고)를 조절한다.",
    "modular_turbine": "터빈 인풋(고압 터빈 단)으로 받은 고압 증기를 태워 전력을 생산하는 5티어 최강 발전기.",
    "turbine_hp_stage": "모듈러 터빈의 '터빈 인풋'. 고압 증기를 파이프로 받아 모듈러 터빈에 나눠 공급한다.",
    "turbine_ip_stage": "모듈러 터빈에 사방으로 붙이면 발전량이 늘어난다.",
    "turbine_lp_stage": "모듈러 터빈에 사방으로 붙이면 발전량이 늘어난다.",
    "turbine_generator_block": "모듈러 터빈에 사방으로 붙이면 발전량이 크게 늘어난다.",
    "lathe": "주괴/분말을 깎아 마인샤프트 드릴에 넣을 드릴 헤드를 만든다 (구리<철<강철<텅스텐카바이드 순으로 내구도가 좋아짐).",
    "mineshaft_drill": "깊이(T로 조절)에 따라 다른 자원을 캐는 만능 채굴기. 드릴 헤드가 있어야 "
                        "작동하고, 캘 때마다 내구도가 닳는다. 산으로 내구도 연장, 머신오일로 증산(대신 마모 증가), "
                        "다이너마이트로 채굴 속도를 일시적으로 높일 수 있다.",
    "fragment_processor": "마인샤프트 드릴이 깊은 곳에서 캔 지구 파편을 석탄/나프타/텅스텐카바이드 분말/베릴륨으로 분리한다 (금은 안 나옴).",
    "ore_refiner": "지구 파편을 황산과 함께 정제해 금괴를 만들고, 부산물로 베릴륨도 함께 나온다. "
                    "금은 이 방법으로만 얻을 수 있다.",
    "heavy_oil_separator": "원유를 분리해 일산화 황을 뽑아낸다 (황산 제조 체인 1단계).",
    "oxidation_chamber": "산소로 일산화 황을 산화시켜 이산화 황을 만든다 (황산 제조 체인 2단계). 산소는 전해조에서 얻는다.",
    "chemical_reactor": "모든 화학 반응을 처리하는 다목적 반응기. 재료를 넣으면 그에 맞는 반응이 자동으로 일어난다.",
    "electrolyzer": "물을 전기분해해 수소와 산소를 만든다. 산화 베릴륨을 넣으면 산소만 뽑아낸다.",
    "air_separator": "어디에 설치하든 대기에서 질소를 뽑아낸다.",
    "steam_cracker": "원유를 증기로 열분해해 파라자일렌과 에틸렌을 동시에 얻는다 (플라스틱 체인 1단계).",
    "plastic_refinery": "원유+물로 에탄올을 만들고, 파라자일렌+아세트산으로 PTA를 만든다.",
}
BUILD_COST = {
    "core": 300,
    "coal_miner": 60, "copper_miner": 60, "iron_miner": 60,
    "lead_miner": 60, "sand_miner": 60, "wood_cutter": 60, "blast_furnace": 220,
    "furnace": 80, "press": 90, "conveyor": 10,
    "wire": 8, "pipe": 15,
    "solar": 70, "coal_gen": 120, "depot": 40,
    "conveyor_3way": 16, "conveyor_4way": 20, "pipe_3way": 22, "pipe_4way": 26,
    "conveyor_crossroad": 24, "pipe_crossroad": 28, "hybrid_crossroad": 34,
    "water_pump": 90, "water_treatment": 110,
    "firebox": 140, "boiler": 130, "turbine": 200,
    "oil_pump": 100, "refinery": 140, "chem_plant": 150, "molder": 130,
    "oil_gen": 220,
    "oil_classifier": 170, "diesel_refiner": 150, "filter": 130, "diesel_gen": 210,
    "gas_extractor": 110, "condenser": 190, "gas_refiner": 170, "gas_turbine": 280,
    "gas_input_block": 20, "turbine_controller_block": 35, "turbine_crankshaft_block": 40,
    "gas_cylinder_block": 30, "exhaust_pump_block": 25, "intake_pump_block": 25,
    "silicon_refiner": 160, "alloy_furnace": 180, "circuit_assembler": 260,
    "assembly_plant": 400, "battery_plant": 320,
    "scrubber": 150, "research": 200, "thermal_plant": 250,
    "coal_power_plant": 450,
    "power_meter": 60, "transformer": 180,
    "battery_cell": 140, "hv_battery": 900,
    "item_filter": 70,
    "drone_transporter": 180, "drone_payload": 90,
    "coal_feeder": 90, "heat_exchanger": 150, "exhaust_stack": 110, "data_power_node": 70,
    "modular_turbine": 350, "turbine_hp_stage": 120, "turbine_ip_stage": 120,
    "turbine_lp_stage": 120, "turbine_generator_block": 160,
    "lathe": 150, "mineshaft_drill": 950, "fragment_processor": 200, "ore_refiner": 240,
    "heavy_oil_separator": 130, "oxidation_chamber": 170, "chemical_reactor": 190,
    "electrolyzer": 180, "air_separator": 120,
    "steam_cracker": 210, "plastic_refinery": 190,
}
BUILD_COLOR = {
    "core": (0.90, 0.78, 0.30),
    "coal_miner": (0.25, 0.24, 0.24),
    "copper_miner": (0.80, 0.45, 0.20),
    "iron_miner": (0.55, 0.52, 0.50),
    "lead_miner": (0.35, 0.38, 0.42),
    "sand_miner": (0.80, 0.72, 0.48),
    "wood_cutter": (0.35, 0.55, 0.25),
    "blast_furnace": (0.55, 0.22, 0.12),
    "furnace": (0.65, 0.20, 0.15),
    "press": (0.35, 0.45, 0.60),
    "conveyor": (0.55, 0.55, 0.58),
    "wire": (0.15, 0.15, 0.16),
    "pipe": (0.30, 0.55, 0.55),
    "solar": (0.15, 0.35, 0.85),
    "coal_gen": (0.20, 0.20, 0.22),
    "depot": (0.20, 0.70, 0.30),
    "conveyor_3way": (0.55, 0.55, 0.58),
    "conveyor_4way": (0.55, 0.55, 0.58),
    "pipe_3way": (0.30, 0.55, 0.55),
    "pipe_4way": (0.30, 0.55, 0.55),
    "conveyor_crossroad": (0.60, 0.45, 0.20),
    "pipe_crossroad": (0.20, 0.45, 0.60),
    "hybrid_crossroad": (0.55, 0.35, 0.55),
    "water_pump": (0.20, 0.45, 0.75),
    "water_treatment": (0.35, 0.75, 0.85),
    "firebox": (0.55, 0.25, 0.12),
    "boiler": (0.45, 0.48, 0.52),
    "turbine": (0.35, 0.55, 0.65),
    "oil_pump": (0.28, 0.32, 0.30),
    "refinery": (0.55, 0.28, 0.12),
    "chem_plant": (0.12, 0.55, 0.50),
    "molder": (0.45, 0.25, 0.55),
    "oil_gen": (0.12, 0.10, 0.10),
    "oil_classifier": (0.42, 0.34, 0.20),
    "diesel_refiner": (0.38, 0.28, 0.12),
    "filter": (0.60, 0.62, 0.65),
    "diesel_gen": (0.22, 0.18, 0.12),
    "gas_extractor": (0.35, 0.55, 0.45),
    "condenser": (0.40, 0.60, 0.70),
    "gas_refiner": (0.45, 0.65, 0.55),
    "gas_turbine": (0.30, 0.45, 0.40),
    "gas_input_block": (0.15, 0.55, 0.45),
    "turbine_controller_block": (0.22, 0.22, 0.24),
    "turbine_crankshaft_block": (0.45, 0.48, 0.50),
    "gas_cylinder_block": (0.35, 0.55, 0.50),
    "exhaust_pump_block": (0.18, 0.16, 0.14),
    "intake_pump_block": (0.62, 0.68, 0.70),
    "silicon_refiner": (0.55, 0.58, 0.62),
    "alloy_furnace": (0.50, 0.30, 0.20),
    "circuit_assembler": (0.15, 0.62, 0.35),
    "assembly_plant": (0.78, 0.56, 0.14),
    "battery_plant": (0.82, 0.72, 0.10),
    "scrubber": (0.75, 0.90, 0.95),
    "research": (0.55, 0.20, 0.75),
    "thermal_plant": (0.30, 0.15, 0.10),
    "coal_power_plant": (0.18, 0.08, 0.07),
    "power_meter": (0.90, 0.85, 0.25),
    "transformer": (0.45, 0.30, 0.70),
    "battery_cell": (0.20, 0.70, 0.40),
    "hv_battery": (0.95, 0.55, 0.05),
    "item_filter": (0.45, 0.45, 0.48),
    "drone_transporter": (0.25, 0.55, 0.85),
    "drone_payload": (0.85, 0.55, 0.20),
    "coal_feeder": (0.35, 0.30, 0.22),
    "heat_exchanger": (0.55, 0.40, 0.30),
    "exhaust_stack": (0.30, 0.28, 0.26),
    "data_power_node": (0.20, 0.55, 0.75),
    "modular_turbine": (0.40, 0.48, 0.58),
    "turbine_hp_stage": (0.65, 0.30, 0.25),
    "turbine_ip_stage": (0.55, 0.50, 0.30),
    "turbine_lp_stage": (0.35, 0.55, 0.60),
    "turbine_generator_block": (0.85, 0.70, 0.15),
    "lathe": (0.50, 0.50, 0.55),
    "mineshaft_drill": (0.30, 0.28, 0.25),
    "fragment_processor": (0.45, 0.40, 0.35),
    "ore_refiner": (0.75, 0.65, 0.20),
    "heavy_oil_separator": (0.30, 0.26, 0.20),
    "oxidation_chamber": (0.60, 0.75, 0.85),
    "chemical_reactor": (0.55, 0.75, 0.45),
    "electrolyzer": (0.25, 0.60, 0.90),
    "air_separator": (0.72, 0.78, 0.85),
    "steam_cracker": (0.62, 0.35, 0.70),
    "plastic_refinery": (0.30, 0.65, 0.62),
}
POWER_DRAW = {
    "coal_miner": 4.0, "copper_miner": 4.0, "iron_miner": 4.0,
    "lead_miner": 4.0, "sand_miner": 4.0, "wood_cutter": 4.0, "blast_furnace": 10.0,
    "furnace": 6.0, "press": 6.0,
    "water_pump": 4.0, "water_treatment": 5.0,
    "firebox": 6.0, "boiler": 7.0,
    "oil_pump": 5.0, "refinery": 9.0, "chem_plant": 9.0, "molder": 7.0,
    "oil_classifier": 9.0, "diesel_refiner": 8.0, "filter": 6.0,
    "gas_extractor": 5.0, "condenser": 10.0, "gas_refiner": 9.0,
    "silicon_refiner": 7.0, "alloy_furnace": 8.0, "circuit_assembler": 10.0,
    "assembly_plant": 14.0, "battery_plant": 11.0,
    "scrubber": 5.0, "research": 5.0,
    "coal_power_plant": 8.0,   # 급수/순환펌프 자체 소모 전력 (발전량 대비 약 9%)
    "heat_exchanger": 8.0,     # 열교환 순환 펌프 자체 소모 전력 (다른 가공 건물들과 마찬가지로 전력 필요)
    "lathe": 9.0, "mineshaft_drill": 16.0, "fragment_processor": 9.0, "ore_refiner": 10.0,
    "heavy_oil_separator": 8.0, "oxidation_chamber": 9.0, "chemical_reactor": 9.0,
    "electrolyzer": 14.0,  # 전기분해는 전력을 많이 먹는다
    "air_separator": 6.0, "steam_cracker": 12.0, "plastic_refinery": 10.0,
}
POWER_SUPPLY = {"solar": 8.0, "coal_gen": 22.0, "oil_gen": 35.0}

# 전력을 저장했다가 부족할 때 방출하는 축전 건물. 값은 저장 용량(전력량, MF*s 단위).
# "1MMF" / "1GMMF" 표기는 모티브 게임의 전력 단위 표기를 그대로 빌려 붙인 이름이며,
# 실제 저장량은 이 게임의 발전량 스케일(수십~백 단위)에 맞춰 10배 차이로 새로 설계했다.
POWER_STORAGE = {
    "battery_cell": 600.0,    # 배터리 (1MMF) - 소형 축전지
    "hv_battery": 6000.0,     # 고압 배터리 (1GMMF) - 대형 축전지 (10배 용량)
}
# 변압기끼리는 와이어로 직접 잇지 않아도 이 거리(격자 칸) 안이면 무선으로 전력망을 이어준다.
TRANSFORMER_RANGE = 4

MINER_INTERVAL = 1.6
PROCESS_TIME = {
    "furnace": 1.4, "press": 1.2, "refinery": 1.8, "chem_plant": 2.0, "molder": 1.6,
    "silicon_refiner": 1.5, "alloy_furnace": 1.6, "circuit_assembler": 2.2,
    "assembly_plant": 3.0, "battery_plant": 2.0, "water_treatment": 1.4,
    "oil_classifier": 2.0, "diesel_refiner": 1.6, "filter": 1.3,
    "firebox": 1.6, "boiler": 1.4,
    "condenser": 2.2, "gas_refiner": 1.8,
    "heat_exchanger": 1.6,
    "blast_furnace": 2.5,
    "lathe": 2.2, "fragment_processor": 2.0, "ore_refiner": 2.5,
    "heavy_oil_separator": 1.8, "oxidation_chamber": 2.0, "chemical_reactor": 2.0,
    "electrolyzer": 2.0, "steam_cracker": 2.2, "plastic_refinery": 2.0,
}

# ---- 유틸리티 건물 수치 ----
THERMAL_POWER_SUPPLY = 40.0          # 화력발전소가 연료(석탄)를 태우는 동안 공급하는 전력
THERMAL_POLLUTION_RATE = 1.5          # 화력발전소가 연료를 태우는 동안 초당 오염 발생량 (낮춤)
THERMAL_FUEL_PER_COAL = 8.0           # 석탄 1개를 넣으면 확보되는 연료(초)
SCRUBBER_POLLUTION_REDUCTION = 2.0    # 정화기 1개, 초당 추가 오염 감소량
RESEARCH_RP_RATE = 1.0                # 연구소 1개, 초당 RP 생산량
# ---- 연구 보너스 ----------------------------------------------------------------
# 모아둔 RP는 100마다 한 단계씩 올라가고, 단계마다 "모든 건물"의 가동률에 곱해지는
# 보너스가 붙는다(가공/채굴 속도가 그만큼 빨라진다). 상한이 없으면 후반에 게임이
# 무의미해지므로 최대치를 둔다.
RP_PER_TIER = 100.0        # 이만큼 모을 때마다 한 단계
RP_BONUS_PER_TIER = 0.05   # 한 단계당 +5% 가동률
RP_BONUS_MAX = 1.00        # 보너스 상한 (+100%, 즉 최대 2배)


def research_multiplier(rp):
    """모아둔 RP로 결정되는 전 건물 공통 가동률 배수 (1.0 = 보너스 없음)."""
    tiers = int(max(0.0, rp) // RP_PER_TIER)
    return 1.0 + min(RP_BONUS_MAX, tiers * RP_BONUS_PER_TIER)
FIREBOX_POLLUTION_RATE = 0.6          # 파이어박스가 석탄을 태우는 동안 초당 오염 발생량 (낮춤)

# 연료(아이템)를 넣어야 돌아가는 발전기 공용 정의: fuel_item을 넣으면 fuel_per_item초만큼
# 연료가 쌓이고, 연료가 남아있는 동안 power만큼 전력을 공급하며 pollution만큼 오염을 낸다.
FUEL_BURNERS = {
    "thermal_plant": {"fuel_item": "coal", "power": THERMAL_POWER_SUPPLY,
                       "pollution": THERMAL_POLLUTION_RATE, "fuel_per_item": THERMAL_FUEL_PER_COAL},
    "diesel_gen": {"fuel_item": "filtered_diesel", "power": 30.0,
                   "pollution": 1.0, "fuel_per_item": 9.0},   # 오염량 낮춤
    "turbine": {"fuel_item": "steam", "power": 25.0,
                "pollution": 0.15, "fuel_per_item": 6.0},   # 증기는 상대적으로 깨끗한 발전 (오염량 낮춤)
    "gas_turbine": {"fuel_item": "refined_gas", "power": 38.0,
                            "pollution": 0.75, "fuel_per_item": 10.0},  # 강력하지만 중간 정도 오염 (낮춤)
    # 4티어 대형 발전 설비. 모티브 게임(Mindustry 석탄발전기 / Industrialist 석탄 화력 발전소) 조사 결과를
    # 참고해 수치를 새로 설계: 자체 소모 전력 대 발전량 비율(POWER_DRAW 참고, 약 9%)과
    # 소형 화력발전소 대비 압도적인 연료 효율(석탄 1개당 공급 전력량 약 4배)로 "산업 규모" 발전소를 표현.
    "coal_power_plant": {"fuel_item": "coal", "power": 90.0,
                          "pollution": 2.2, "fuel_per_item": 14.0},
    # 5티어 모듈러 터빈: 보일러의 평범한 증기가 아니라, 열교환기가 만든 고압 증기(high_pressure_steam)를
    # turbine_hp_stage("터빈 인풋")로 받아야 돌아간다. 부품(고/중/저압 단 + 제너레이터)을 전부 붙이면
    # 게임 내 최고 발전량을 내는 엔드게임 발전기. Industrialist의 "Modular Turbine"
    # (고압/중압/저압 3단 터빈 + 터빈 제너레이터 구성, 열교환기가 만든 고압 증기를 입력받는 구조)에서 참고함.
    "modular_turbine": {"fuel_item": "high_pressure_steam", "power": 70.0,
                         "pollution": 0.3, "fuel_per_item": 8.0},
}

# 입력 1종 -> 출력 1종(또는 여러 종류를 동시에 산출)인 단순 가공 건물
# 값이 문자열이면 출력 1종, 리스트면 한 번에 여러 종류를 동시에 산출한다 (예: 원유 분류기, 콘덴서).
RECIPES = {
    # 금 채굴기를 없앨 때 금 원석도 함께 사라졌으므로, 절대 작동할 수 없던
    # "금 원석 -> 금괴" 레시피도 제거했다. 금은 광석 정제기(지구 파편 + 황산)에서만 나온다.
    "furnace": {"copper_ore": "copper_ingot", "iron_ore": "iron_ingot"},
    "press": {"copper_ingot": "copper_plate", "iron_ingot": "iron_plate"},
    "refinery": {"crude_oil": "fuel"},
    "molder": {"plastic_pellet": "plastic_case"},
    "silicon_refiner": {"silicon": "silicon_wafer"},  # 실리콘(폭발로 산출물)을 웨이퍼로 정제
    "water_treatment": {"water": "purified_water"},
    "oil_classifier": {"crude_oil": ["naphtha", "diesel_raw"]},   # 원유를 나프타+디젤 원료로 분리
    "diesel_refiner": {"diesel_raw": "diesel"},
    "filter": {"diesel": "filtered_diesel"},
    "boiler": {"hot_water": "steam"},
    "condenser": {"natural_gas": ["residue", "water", "distilled_gas"]},   # 천연가스 -> 잔류물+물+증류가스
    "gas_refiner": {"distilled_gas": ["residue", "refined_gas"]},          # 증류가스 -> 잔류물+정제가스
    "heat_exchanger": {"water": "high_pressure_steam"},  # 물을 고압 증기로 바꿈 (전력만 있으면 작동)
    # 선반: 주괴/분말을 깎아 마인샤프트 드릴용 드릴 헤드를 만든다. 어떤 재료가 들어오느냐에 따라
    # 산출물이 달라지는 furnace와 같은 패턴 (재료별로 다른 등급의 헤드가 나옴).
    "lathe": {
        "copper_ingot": "copper_drill_head",
        "iron_ingot": "iron_drill_head",
        "lead_ingot": "lead_drill_head",
        "steel_ingot": "steel_drill_head",
        "tungsten_carbide_powder": "tungsten_carbide_drill_head",
    },
    # 파편 분류기: 마인샤프트 드릴이 깊은 곳에서 캐온 지구 파편을 여러 유용한 자원으로 분리한다.
    # 금은 여기서 안 나오고, 광석 정제기에서 파편+황산으로 따로 정제해야 한다.
    # 베릴륨도 여기서 소량 나온다 - 이게 없으면 "베릴륨 -> 황산 -> 광석 정제기 -> 베릴륨"이
    # 순환 고리가 되어, 황산이 하나도 없는 초기 상태에서는 체인을 영영 시작할 수 없다.
    "fragment_processor": {"earth_fragment": ["coal", "naphtha", "tungsten_carbide_powder", "beryllium"]},
    # 중유 분리기: 황산 제조 체인의 첫 단계. 원유를 분리해 일산화 황을 뽑아낸다.
    "heavy_oil_separator": {"crude_oil": "sulfur_monoxide"},
    # 전해조: 물을 전기분해해 수소와 산소를 동시에 얻는다 (화학 체인의 출발점).
    # 산화 베릴륨도 전기분해해서 산소를 뽑아낸다 (베릴륨 -> 산화실 -> 산화 베릴륨 -> 여기서 산소).
    "electrolyzer": {"water": ["hydrogen", "oxygen"], "beryllium_oxide": "oxygen"},
}
# 입력 2종 이상을 모아야 가공을 시작하는 3~4티어 건물
# inputs: {아이템타입: 필요 개수}, output: 산출물, 필요한 재료가 모두 모이면 process_timer 시작
MULTI_RECIPES = {
    "alloy_furnace": {"inputs": {"iron_ingot": 1, "coal": 1}, "output": "steel_ingot"},
    # 광석 정제기: 금은 이제 채굴로 안 나오고, 지구 파편(마인샤프트 드릴의 깊은 채굴 산출물)을
    # 황산과 함께 정제해야만 얻을 수 있다. (황산 자체를 만드는 방법은 나중에 추가 예정)
    "ore_refiner": {"inputs": {"earth_fragment": 1, "sulfuric_acid": 1}, "output": ["gold_bar", "beryllium"]},
    # 화학 반응기: 이산화 황 + 물 -> 황산 (황산 제조 체인의 마지막 단계)
    "circuit_assembler": {"inputs": {"copper_plate": 1, "silicon_wafer": 1}, "output": "circuit_board"},
    "battery_plant": {"inputs": {"copper_plate": 1, "plastic_pellet": 1}, "output": "battery"},
    "assembly_plant": {"inputs": {"circuit_board": 1, "steel_ingot": 1, "plastic_case": 1},
                        "output": "advanced_module"},
    "firebox": {"inputs": {"water": 1, "coal": 1}, "output": "hot_water"},  # 물을 석탄으로 데움
}

# 폭발로(blast_furnace) 전용: 재료(주재료 1종 + 연료 1종)에 따라 산출물이 달라지는 다목적 용광로.
# 값이 문자열이면 산출물 1종. 주재료는 서로 겹치지 않지만, 연료 칸은 석탄/목탄 둘 중 아무거나
# 받아준다 (그래서 일반 MULTI_RECIPES의 "고정된 재료 dict" 방식으로는 표현이 안 돼 따로 뺌).
BLAST_FURNACE_PRIMARY = {
    "iron_ingot": "steel_ingot",   # 철 주괴 + 석탄/목탄 -> 강철 주괴
    "sand": "silicon",             # 모래 + 석탄/목탄 -> 실리콘
    "lead_ore": "lead_ingot",      # 납 광석 + 석탄/목탄 -> 납 주괴
    "wood": "charcoal",            # 나무 + 석탄/목탄 -> 목탄
}
FUEL_LIKE_ITEMS = {"coal", "charcoal"}  # 폭발로 연료 칸에 넣을 수 있는 아이템(둘 다 허용)

# 한 건물이 여러 레시피를 재료에 따라 골라서 처리해야 하는 경우를 위한 동적 레시피 표.
# MULTI_RECIPES는 건물당 레시피가 딱 1개만 가능해서, 화학 반응기/산화실/플라스틱 정제소처럼
# 들어온 재료에 맞는 반응을 골라야 하는 건물은 여기에 목록으로 등록한다
# (World._try_capture_inputs / _move_items의 DYNAMIC_RECIPES 분기가 공통 처리).
# output이 리스트면 한 번에 여러 종류를 동시에 산출한다.
DYNAMIC_RECIPES = {
    "chemical_reactor": [
        {"inputs": {"sulfur_dioxide": 1, "water": 1}, "output": "sulfuric_acid"},  # 이산화 황 + 물 -> 황산
        {"inputs": {"nitrogen": 1, "hydrogen": 1}, "output": "ammonia"},           # 질소 + 수소 -> 암모니아
        # ---- 마인샤프트 드릴 소모품 3종 ----
        # 전에는 아이템만 있고 만들 방법이 없어서 드릴의 보조 기능(속도·내구 연장)을
        # 아예 쓸 수 없었다. 이미 있는 중간재로 조합해 만들 수 있게 한다.
        {"inputs": {"sulfuric_acid": 1, "water": 1}, "output": "acid"},            # 황산을 희석해 세정용 산
        {"inputs": {"ammonia": 1, "sulfuric_acid": 1}, "output": "dynamite"},      # 질산암모늄계 폭약
        {"inputs": {"fuel": 1, "plastic_pellet": 1}, "output": "machine_oil"},     # 연료유 + 증점제 -> 머신 오일
    ],
    # 산화실: 산화 반응 전담. 황산 체인의 이산화 황도, 플라스틱 체인의 아세트산/MEG도 여기서 만든다.
    "oxidation_chamber": [
        {"inputs": {"oxygen": 1, "sulfur_monoxide": 1}, "output": "sulfur_dioxide"},
        {"inputs": {"ethanol": 1}, "output": "acetic_acid"},   # 에탄올 산화 -> 아세트산
        {"inputs": {"ethylene": 1}, "output": "meg"},          # 에틸렌 산화 -> MEG
        {"inputs": {"beryllium": 1}, "output": "beryllium_oxide"},  # 베릴륨 산화 -> 산화 베릴륨
    ],
    # 스팀 크래킹 플랜트: 원유를 증기로 열분해해 파라자일렌과 에틸렌을 동시에 얻는다.
    "steam_cracker": [
        {"inputs": {"crude_oil": 1, "steam": 1}, "output": ["paraxylene", "ethylene"]},
    ],
    # 플라스틱 정제소: 에탄올을 만들고, 파라자일렌+아세트산으로 PTA를 만든다.
    "plastic_refinery": [
        {"inputs": {"crude_oil": 1, "water": 1}, "output": "ethanol"},
        {"inputs": {"paraxylene": 1, "acetic_acid": 1}, "output": "pta"},
    ],
    # 플라스틱 생산 시설: PTA + MEG -> 플라스틱 펠릿 (원작 위키의 최종 단계)
    "chem_plant": [
        {"inputs": {"pta": 1, "meg": 1}, "output": "plastic_pellet"},
    ],
}
# 건물별로 받아들일 수 있는 재료와 그 재료를 최대 몇 개까지 쌓아둘지
# (그 건물의 어떤 레시피에서든 필요한 최대 개수까지만 받아서, 안 쓰는 재료로 버퍼가 막히지 않게 한다)
DYNAMIC_INPUT_MAX = {}
for _btype, _recipes in DYNAMIC_RECIPES.items():
    _limits = {}
    for _recipe in _recipes:
        for _item, _count in _recipe["inputs"].items():
            _limits[_item] = max(_limits.get(_item, 0), _count)
    DYNAMIC_INPUT_MAX[_btype] = _limits

# 마인샤프트 드릴(mineshaft_drill) 전용. Industrialist 원작 위키 조사 기준으로 설계:
# 드릴 헤드(구리<철<강철<텅스텐카바이드 순으로 내구도 좋아짐) 하나를 넣어야 작동하고,
# 캘 때마다 내구도가 줄어들어 0이 되면 새 헤드가 필요하다. 깊이(T키로 조절)가 깊을수록
# 더 좋은 헤드가 필요하지만 산출물도 달라진다 - 원작에서 "1200m를 넘으면 구리 헤드가
# 못 쓰게 된다"고 한 것처럼, 헤드 등급이 깊이를 못 버티면 그냥 멈춰서 대기한다.
DRILL_HEAD_DURABILITY = {
    "copper_drill_head": 40,             # 원작: 내구도 최하 (얕은 곳 임시용)
    "lead_drill_head": 65,               # 원작에는 없는 이 게임만의 추가 등급: 구리보다 낫고 철보다 아래.
                                          # 폭발로(납 광석+석탄/목탄->납 주괴) 경로로 만드는 대안 헤드.
    "iron_drill_head": 90,               # 원작: 구리보다는 낫지만 강철보다 아래
    "steel_drill_head": 180,             # 원작: 2군데 좋은 등급, 산과 조합하면 수명 길게 유지
    "tungsten_carbide_drill_head": 720,  # 원작: 강철의 4배 내구도, 최고 등급
}
DRILL_HEAD_MIN_DEPTH = {
    "copper_drill_head": 1, "lead_drill_head": 2, "iron_drill_head": 2,
    "steel_drill_head": 3, "tungsten_carbide_drill_head": 4,
}
DRILL_DEPTH_LABEL = {1: "얕음", 2: "중간", 3: "깊음", 4: "매우 깊음"}
# 깊이 단계별 산출물 후보(아이템, 가중치) - 얕은 곳은 자갈/흙 위주(원작의 Gravel/Soil/Rich Soil),
# 중간은 광석(구리/철), 깊은 곳은 지구 파편(원작의 Deep Earth Fragment, 5200~8800m 대응)이 나온다.
DRILL_DEPTH_OUTPUTS = {
    1: [("gravel", 3), ("soil", 3), ("rich_soil", 1)],
    2: [("copper_ore", 2), ("iron_ore", 2), ("gravel", 1)],
    3: [("earth_fragment", 1)],
    4: [("earth_fragment", 1)],
}
MINESHAFT_BASE_INTERVAL = 2.0   # 기본 채굴 주기(초)
ACID_DURABILITY_BONUS = 20.0    # 산 1개 소모 -> 현재 드릴 헤드 내구도 +20 (원작: 산이 헤드 수명을 늘려줌)
OIL_BOOST_CYCLES = 10           # 머신오일 1개 = 다음 10사이클 동안 효과 지속
OIL_YIELD_BONUS = 0.10          # 머신오일: 산출량 +10% (원작 그대로)
OIL_WEAR_BONUS = 0.10           # 머신오일: 내구도 마모 +10% (원작 그대로)
DYNAMITE_BOOST_CYCLES = 5       # 다이너마이트 1개 = 다음 5사이클 동안 효과 지속

SELL_PRICE = {
    "copper_ore": 3, "iron_ore": 3, "coal": 4, "silicon": 4,
    "water": 3, "purified_water": 16, "hot_water": 5, "steam": 8,
    "copper_ingot": 8, "iron_ingot": 8, "steel_ingot": 22,
    "copper_plate": 18, "iron_plate": 18, "silicon_wafer": 14,
    "crude_oil": 5, "fuel": 14, "plastic_pellet": 12, "plastic_case": 30,
    "circuit_board": 55, "battery": 65, "advanced_module": 180,
    "gold_bar": 230,  # 게임 내 최고가 아이템
    "naphtha": 10, "diesel_raw": 6, "diesel": 16, "filtered_diesel": 24,
    "natural_gas": 6, "residue": 2, "distilled_gas": 12, "refined_gas": 20,
    "high_pressure_steam": 26,
    "wood": 2, "charcoal": 6, "lead_ore": 5, "lead_ingot": 16, "sand": 3,
    "gravel": 1, "soil": 1, "rich_soil": 2, "earth_fragment": 12, "tungsten_carbide_powder": 60,
    "dynamite": 20, "acid": 15, "machine_oil": 18, "sulfuric_acid": 25,
    "sulfur_monoxide": 8, "sulfur_dioxide": 14, "beryllium": 45, "beryllium_oxide": 52,
    "hydrogen": 10, "oxygen": 9, "nitrogen": 7, "ammonia": 34,
    "paraxylene": 16, "ethylene": 15, "ethanol": 13, "acetic_acid": 20, "pta": 30, "meg": 28,
    "copper_drill_head": 40, "iron_drill_head": 90, "lead_drill_head": 65, "steel_drill_head": 180,
    "tungsten_carbide_drill_head": 500,
}
ITEM_COLOR = {
    "copper_ore": (0.80, 0.45, 0.20),
    "iron_ore": (0.55, 0.52, 0.50),
    "coal": (0.12, 0.12, 0.13),
    "silicon": (0.62, 0.58, 0.52),
    "water": (0.20, 0.45, 0.85),
    "purified_water": (0.55, 0.88, 1.00),
    "hot_water": (0.75, 0.45, 0.40),
    "steam": (0.88, 0.88, 0.92),
    "copper_ingot": (0.95, 0.55, 0.20),
    "iron_ingot": (0.80, 0.80, 0.85),
    "steel_ingot": (0.72, 0.74, 0.78),
    "gold_bar": (1.00, 0.84, 0.00),   # 순금색 (보라색 아님)
    "copper_plate": (0.90, 0.40, 0.10),
    "iron_plate": (0.65, 0.68, 0.72),
    "silicon_wafer": (0.72, 0.80, 0.88),
    "crude_oil": (0.05, 0.05, 0.06),
    "fuel": (0.85, 0.75, 0.15),
    "plastic_pellet": (0.90, 0.88, 0.80),
    "plastic_case": (0.55, 0.75, 0.95),
    "circuit_board": (0.12, 0.55, 0.28),
    "battery": (0.85, 0.70, 0.10),
    "advanced_module": (0.90, 0.60, 0.10),
    "naphtha": (0.85, 0.80, 0.40),
    "diesel_raw": (0.28, 0.20, 0.14),
    "diesel": (0.35, 0.25, 0.10),
    "filtered_diesel": (0.60, 0.45, 0.15),
    "natural_gas": (0.55, 0.80, 0.75),
    "residue": (0.30, 0.26, 0.22),
    "distilled_gas": (0.70, 0.90, 0.85),
    "refined_gas": (0.50, 0.95, 0.80),
    "high_pressure_steam": (0.95, 0.95, 1.00),
    "wood": (0.45, 0.30, 0.15),
    "charcoal": (0.15, 0.13, 0.12),
    "lead_ore": (0.35, 0.38, 0.42),
    "lead_ingot": (0.55, 0.58, 0.62),
    "sand": (0.85, 0.78, 0.55),
    "gravel": (0.55, 0.52, 0.48),
    "soil": (0.35, 0.25, 0.15),
    "rich_soil": (0.25, 0.16, 0.08),
    "earth_fragment": (0.45, 0.35, 0.30),
    "tungsten_carbide_powder": (0.30, 0.30, 0.32),
    "dynamite": (0.80, 0.15, 0.10),
    "acid": (0.70, 0.95, 0.20),
    "sulfuric_acid": (0.90, 0.90, 0.30),
    "sulfur_monoxide": (0.75, 0.72, 0.55),
    "sulfur_dioxide": (0.85, 0.82, 0.60),
    "beryllium": (0.65, 0.85, 0.75),
    "beryllium_oxide": (0.85, 0.95, 0.90),
    "hydrogen": (0.80, 0.90, 1.00),
    "oxygen": (0.55, 0.75, 1.00),
    "nitrogen": (0.70, 0.72, 0.80),
    "ammonia": (0.60, 0.85, 0.65),
    "paraxylene": (0.85, 0.70, 0.90),
    "ethylene": (0.70, 0.90, 0.80),
    "ethanol": (0.90, 0.95, 0.85),
    "acetic_acid": (0.95, 0.85, 0.55),
    "pta": (0.95, 0.95, 0.98),
    "meg": (0.75, 0.85, 0.95),
    "machine_oil": (0.10, 0.08, 0.06),
    "copper_drill_head": (0.85, 0.50, 0.22),
    "iron_drill_head": (0.65, 0.65, 0.68),
    "lead_drill_head": (0.40, 0.42, 0.46),
    "steel_drill_head": (0.55, 0.58, 0.62),
    "tungsten_carbide_drill_head": (0.35, 0.35, 0.40),
}

# 조준 정보 패널(아이템 종류를 텍스트로 보여줄 때) 등에 쓰는 한글 표시 이름
ITEM_LABEL = {
    "copper_ore": "구리 원석", "iron_ore": "철 원석", "coal": "석탄",
    "silicon": "실리콘",
    "water": "물", "purified_water": "정수", "hot_water": "온수", "steam": "증기",
    "copper_ingot": "구리 주괴", "iron_ingot": "철 주괴", "steel_ingot": "강철 주괴",
    "gold_bar": "금괴", "copper_plate": "구리판", "iron_plate": "철판",
    "silicon_wafer": "실리콘 웨이퍼",
    "crude_oil": "원유", "fuel": "연료유", "plastic_pellet": "플라스틱 펠릿",
    "plastic_case": "플라스틱 케이스", "circuit_board": "회로기판",
    "battery": "배터리(완제품)", "advanced_module": "고급 모듈",
    "naphtha": "나프타", "diesel_raw": "디젤 원료", "diesel": "디젤",
    "filtered_diesel": "정제 디젤", "natural_gas": "천연가스", "residue": "잔류물",
    "distilled_gas": "증류가스", "refined_gas": "정제가스",
    "high_pressure_steam": "고압 증기",
    "wood": "나무", "charcoal": "목탄", "lead_ore": "납 광석",
    "lead_ingot": "납 주괴", "sand": "모래",
    "gravel": "자갈", "soil": "흙", "rich_soil": "기름진 흙",
    "earth_fragment": "지구 파편", "tungsten_carbide_powder": "텅스텐카바이드 분말",
    "dynamite": "다이너마이트", "acid": "산", "machine_oil": "머신 오일", "sulfuric_acid": "황산",
    "sulfur_monoxide": "일산화 황", "sulfur_dioxide": "이산화 황", "beryllium": "베릴륨",
    "beryllium_oxide": "산화 베릴륨",
    "hydrogen": "수소", "oxygen": "산소", "nitrogen": "질소", "ammonia": "암모니아",
    "paraxylene": "파라자일렌", "ethylene": "에틸렌", "ethanol": "에탄올",
    "acetic_acid": "아세트산", "pta": "PTA", "meg": "MEG",
    "copper_drill_head": "구리 드릴 헤드", "iron_drill_head": "철 드릴 헤드",
    "lead_drill_head": "납 드릴 헤드",
    "steel_drill_head": "강철 드릴 헤드", "tungsten_carbide_drill_head": "텅스텐카바이드 드릴 헤드",
}

# ---- 자원 채굴 건물: 어떤 광맥/수원에서 어떤 아이템을 채굴하는지 ----------------
DEPOSIT_OUTPUT = {
    "coal_miner": {"coal": "coal"},
    "copper_miner": {"copper_ore": "copper_ore"},
    "iron_miner": {"iron_ore": "iron_ore"},
    "lead_miner": {"lead_ore": "lead_ore"},
    "sand_miner": {"sand": "sand"},
    "wood_cutter": {"wood": "wood"},
    "oil_pump": {"oil": "crude_oil"},
    "water_pump": {"water_source": "water"},
    "gas_extractor": {"gas_field": "natural_gas"},
    # 공기 분리기: 대기 중에서 질소를 뽑아낸다 (질소는 광맥이 아니라 공기에서 오므로
    # 다른 추출기들처럼 어디에 설치하든 작동한다).
    "air_separator": {"air": "nitrogen"},
}
EXTRACT_INTERVAL = {
    "coal_miner": MINER_INTERVAL, "copper_miner": MINER_INTERVAL, "iron_miner": MINER_INTERVAL,
    "lead_miner": MINER_INTERVAL, "sand_miner": MINER_INTERVAL,
    "wood_cutter": MINER_INTERVAL,
    "oil_pump": 1.8, "water_pump": 1.4, "gas_extractor": 1.7, "air_separator": 1.6,
}

# 파이핑은 액체/기체성 아이템만 통과시킬 수 있음 (고체는 컨베이어를 써야 함)
LIQUID_ITEMS = {"crude_oil", "fuel", "plastic_pellet", "water", "purified_water",
                 "naphtha", "diesel_raw", "diesel", "filtered_diesel", "hot_water", "steam",
                 "natural_gas", "distilled_gas", "refined_gas", "high_pressure_steam",
                 "sulfur_monoxide", "sulfur_dioxide", "sulfuric_acid",
                 "hydrogen", "oxygen", "nitrogen", "ammonia",
                 "paraxylene", "ethylene", "ethanol", "acetic_acid", "pta", "meg"}
# 조준 정보 패널에서 내용물 수량을 표시할 때 쓰는 단위 환산치: 액체/기체는 파이프 한 칸당
# 이 리터(L)만큼 흐르는 것으로 보고 "L" 단위로, 고체는 개수를 그대로 "U"(유닛) 단위로 보여준다.
LITERS_PER_UNIT = 250.0


def format_item_amount(item_type, count=1):
    """아이템 종류/개수를 조준 정보 패널에 보여줄 문자열로 바꾼다.
    액체/기체(LIQUID_ITEMS)는 "250L"처럼 리터로, 고체는 "3U"처럼 유닛으로 표시한다."""
    label = ITEM_LABEL.get(item_type, item_type)
    if item_type in LIQUID_ITEMS:
        return f"{label} {count * LITERS_PER_UNIT:.0f}L"
    return f"{label} {count}U"

# ---- 운반 건물 분류 ----------------------------------------------------
# 컨베이어 계열: 어떤 아이템이든 자신의 dir 방향으로 흘려보냄 (3/4방향은 여러 방향에서
# 들어와도 결국 하나의 dir로 합류하는 T자/십자 분기)
CONVEYOR_LIKE = {"conveyor", "wire", "conveyor_3way", "conveyor_4way"}
# 파이프 계열: 액체/기체 아이템만 자신의 dir 방향으로 흘려보냄
PIPE_LIKE = {"pipe", "pipe_3way", "pipe_4way"}
# 분배기 계열: 들어온 아이템을 여러 출구로 번갈아 내보낸다(합류가 아니라 분배).
# 3방향은 전방/좌/우, 4방향은 사방으로 순환 배분하되, 들어온 방향으로 되돌려보내지는
# 않는다(그대로 되돌리면 앞 라인과 서로 밀어내며 막히기만 한다).
DISTRIBUTOR_TYPES = {"conveyor_3way", "conveyor_4way", "pipe_3way", "pipe_4way"}
PIPE_DISTRIBUTORS = {"pipe_3way", "pipe_4way"}   # 액체/기체만 통과


def distributor_outputs(btype, facing):
    """분배기가 내보낼 방향 목록. facing(건물 방향)을 전방으로 삼아 시계방향 순서."""
    dx, dz = facing
    fwd = (dx, dz)
    right = (-dz, dx)
    left = (dz, -dx)
    back = (-dx, -dz)
    if btype in ("conveyor_3way", "pipe_3way"):
        return (fwd, right, left)
    return (fwd, right, back, left)
# 일반 파이프가 시각적으로 이음매를 이어 붙일 대상(다른 파이프류 + 파이프가 지나가는 교차로)
PIPE_CONNECTABLE = PIPE_LIKE | {"pipe_crossroad", "hybrid_crossroad"}
# 교차로 계열: 건물 자신의 dir을 무시하고, 아이템이 원래 갖고 있던 진행 방향을 그대로 유지시켜
# 두 흐름이 서로 섞이지 않고 직선으로 가로질러 지나가게 한다
CROSSROAD_TYPES = {"conveyor_crossroad", "pipe_crossroad", "hybrid_crossroad"}

# 드론 운송: 컨베이어로 안 이어져 있어도, 드론 수송기가 지정한 종류의 화물을 맵 어디서든
# 찾아 실어다가 지정한 드론 페이로드에 떨궈준다. drone_payload는 받은 화물을 자기 dir 방향으로
# 다시 흘려보내야 하므로(컨베이어 없이도 물건이 그 위에서 움직이도록) CONVEYOR_LIKE에도 포함시킨다.
DRONE_UI_TYPES = {"drone_transporter", "drone_payload"}
CONVEYOR_LIKE = CONVEYOR_LIKE | {"drone_payload"}
DRONE_SCAN_INTERVAL = 1.5      # 드론 수송기가 새 화물을 찾아 출발시키는 주기(초)
DRONE_EMIT_INTERVAL = 0.6      # 드론 페이로드가 쌓인 화물을 한 개씩 내보내는 주기(초)
DRONE_FLIGHT_SPEED = 5.0       # 드론 비행 속도 (월드 단위/초, 컨베이어보다 훨씬 빠름)
DRONE_RANGE = 22               # 드론 수송기가 화물/페이로드를 찾는 최대 거리 (칸)
DRONE_LIFT_HEIGHT = 2.2        # 드론이 비행 중 상승하는 최고 높이

# 가스 터빈 부품군 - 서로 인접하면 파이프/케이블로 시각적으로 이어진 것처럼 표시
GAS_TURBINE_FAMILY = {"gas_turbine", "gas_input_block", "turbine_controller_block",
                       "turbine_crankshaft_block", "gas_cylinder_block",
                       "exhaust_pump_block", "intake_pump_block"}

# 가스 터빈에 인접(GAS_TURBINE_FAMILY 무리로 연결)한 부품 하나당 붙는 보너스.
# 예전에는 이 6종 부품이 전부 장식용이라 실제 발전량/효율에 아무 영향이 없었음 -> 이제는
# 부품을 실제로 붙여서 조립해야 의미가 있는 "모듈형 가스 터빈"으로 만든다.
GAS_TURBINE_PART_BONUS = {
    "gas_input_block": {"power": 6.0},             # 가스 인풋: 공급 압력 보강 -> 발전량 증가
    "turbine_controller_block": {"power": 4.0, "pollution": -0.10},  # 컨트롤러: 연소 안정화
    "turbine_crankshaft_block": {"power": 10.0},    # 크랭크축: 실제로 회전력을 전달 -> 발전량 증가
    "gas_cylinder_block": {"fuel_per_item": 6.0},   # 실린더: 여분 저장고 -> 가스 1개당 연소 시간 증가
    "exhaust_pump_block": {"pollution": -0.25},     # 배기 펌프: 매연 저감
    "intake_pump_block": {"power": 6.0},            # 흡기 펌프: 산소 공급 개선 -> 발전량 증가
}

# 석탄 화력 발전소 부품군 - Industrialist의 Coal Power Plant가 Coal Feeder(연료 공급 속도),
# Heat Exchanger(폐열 회수 발전), Exhaust Stack(배기/오염 저감), Data Power Node(제어실 연동)
# 네 가지 보조 설비를 옆에 붙여서 운용하는 것에서 구조를 참고함. coal_power_plant에 사방으로
# 인접시키면 아래 보너스가 더해진다 (수치는 원작을 그대로 베끼지 않고 이 게임 스케일에 맞게 새로 설계).
COAL_PLANT_FAMILY = {"coal_power_plant", "coal_feeder", "heat_exchanger",
                      "exhaust_stack", "data_power_node"}
COAL_PLANT_PART_BONUS = {
    "coal_feeder": {"power": 12.0},               # 석탄 공급기: 연료 공급 속도 향상 -> 발전량 증가
    "exhaust_stack": {"pollution": -1.1},          # 배기탑: 배기가스를 처리해 오염을 크게 저감
    # 열교환기는 더 이상 여기서 고정 보너스를 받지 않는다 - 대신 물을 받아 실제로
    # high_pressure_steam을 만들어내는 RECIPES 건물이 되었다 (아래 참고).
    # 데이터 파워 노드도 고정 보너스 대신, 석탄/공기/배기 공급량을 조절하는 출력 단계(T키)로
    # coal_power_plant의 power/pollution/fuel_per_item을 배율로 조절한다 (COAL_PLANT_NODE_LEVEL_MULT).
}

# 데이터 파워 노드(T키로 순환)로 조절하는 coal_power_plant 출력 단계.
# 실제 Industrialist의 "석탄 공급량 / 공기 공급량 / 배기량" 3종 슬라이더를, 하나로 묶은
# "출력 단계" 다이얼로 단순화했다: 높일수록 석탄을 더 빨리 태워(연료 소모 증가) 더 큰 발전량을
# 뽑아내지만 공기 공급/배기가 늘어나 오염도 커지고, 낮추면 그 반대로 절약 운전이 된다.
COAL_PLANT_NODE_LEVEL_MULT = {
    1: {"power": 0.65, "pollution": 0.55, "fuel_per_item": 1.4},   # 저출력: 석탄/공기 절약
    2: {"power": 1.0, "pollution": 1.0, "fuel_per_item": 1.0},     # 표준
    3: {"power": 1.4, "pollution": 1.6, "fuel_per_item": 0.6},     # 고출력: 석탄/공기 많이 -> 배기도 많음
}

# 5티어 모듈러 터빈 부품군 - Industrialist의 Modular Turbine이 High/Intermediate/Low Pressure
# Turbine 3단 + Turbine Generator로 구성되어, 붙인 단이 많을수록(붙인 만큼 회전력이 늘어) 발전량이
# 커지는 구조에서 참고함. modular_turbine에 사방으로 인접시키면 아래 보너스가 더해진다.
MODULAR_TURBINE_FAMILY = {"modular_turbine", "turbine_hp_stage", "turbine_ip_stage",
                           "turbine_lp_stage", "turbine_generator_block"}
MODULAR_TURBINE_PART_BONUS = {
    "turbine_hp_stage": {"power": 20.0},     # 고압 터빈 단: 1차로 증기를 받아 큰 낙차의 회전력 생산
    "turbine_ip_stage": {"power": 18.0},     # 중압 터빈 단: 고압 단을 거친 증기를 다시 팽창시켜 추가 발전
    "turbine_lp_stage": {"power": 16.0},     # 저압 터빈 단: 마지막으로 남은 압력까지 완전히 회수
    "turbine_generator_block": {"power": 25.0},  # 터빈 제너레이터: 모든 단의 회전력을 실제 전력으로 변환
}


def _family_cluster(world, start_pos, family, core_type):
    """start_pos에서 family(건물 타입 집합)로 사방 연결된 무리 전체를 BFS로 찾아
    (그 안의 core_type 위치 집합, {부품 종류: [그 종류인 칸 위치들]} 딕셔너리)을 돌려준다.
    start_pos 자신이 부품이면 parts에, core_type이면 cores에 포함된다. 가스 터빈/석탄 발전소/
    모듈러 터빈이 모두 "핵심 건물 + 옆에 붙이는 보조 부품들" 구조를 공유하므로 BFS 로직을 여기
    하나로 모았다. parts를 종류->위치 목록으로 주는 이유는, 데이터 파워 노드처럼 부품 하나하나가
    (종류는 같아도) 서로 다른 개별 설정값을 가질 수 있는 경우 실제 어느 칸인지 찾아야 하기 때문이다."""
    start_b = world.buildings.get(start_pos)
    if start_b is None or start_b["type"] not in family:
        return set(), {}

    seen = {start_pos}
    cores, parts = set(), {}
    if start_b["type"] == core_type:
        cores.add(start_pos)
    else:
        parts.setdefault(start_b["type"], []).append(start_pos)

    stack = [start_pos]
    while stack:
        cx, cz = stack.pop()
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            npos = (cx + dx, cz + dz)
            if npos in seen:
                continue
            nb = world.buildings.get(npos)
            if nb is not None and nb["type"] in family:
                seen.add(npos)
                if nb["type"] == core_type:
                    cores.add(npos)
                else:
                    parts.setdefault(nb["type"], []).append(npos)
                stack.append(npos)
    return cores, parts


def _gas_turbine_cluster(world, start_pos):
    return _family_cluster(world, start_pos, GAS_TURBINE_FAMILY, "gas_turbine")


def _gas_turbine_connected_parts(world, pos):
    """(gx,gz)의 가스터빈과 같은 무리에 실제로 붙어있는 부품 종류의 집합을 돌려준다
    (가스터빈 자신은 제외). 부품 하나는 여러 가스터빈이 같은 무리 안에 있으면
    그 전부에게 보너스를 준다."""
    _, parts = _gas_turbine_cluster(world, pos)
    return parts


# FUEL_BURNERS 중 "핵심 건물 + 인접 보조 부품" 구조를 쓰는 발전기들의 (부품군, 부품별 보너스) 테이블.
# 여기 없는 발전기(화력발전소/디젤발전기 등)는 FUEL_BURNERS 고정 수치를 그대로 쓴다.
FAMILY_PART_BONUS = {
    "gas_turbine": (GAS_TURBINE_FAMILY, GAS_TURBINE_PART_BONUS),
    "coal_power_plant": (COAL_PLANT_FAMILY, COAL_PLANT_PART_BONUS),
    "modular_turbine": (MODULAR_TURBINE_FAMILY, MODULAR_TURBINE_PART_BONUS),
}


def get_burner_stats(world, pos):
    """FUEL_BURNERS 발전기 한 칸의 실제 발전량/오염/연료소모 수치를 돌려준다.
    FAMILY_PART_BONUS에 등록된 발전기(가스터빈/석탄 화력 발전소/모듈러 터빈)는 사방으로 붙인
    보조 부품의 보너스를 더해서 계산하고, 그 외 발전기는 FUEL_BURNERS의 고정 수치를 그대로 돌려준다."""
    b = world.buildings.get(pos)
    if b is None:
        return None
    btype = b["type"]
    base = FUEL_BURNERS.get(btype)
    if base is None:
        return None
    family_info = FAMILY_PART_BONUS.get(btype)
    if family_info is None:
        return base
    family, bonus_table = family_info

    power, pollution, fuel_per_item = base["power"], base["pollution"], base["fuel_per_item"]
    _, parts = _family_cluster(world, pos, family, btype)
    for part in parts:
        bonus = bonus_table.get(part, {})
        power += bonus.get("power", 0.0)
        pollution += bonus.get("pollution", 0.0)
        fuel_per_item += bonus.get("fuel_per_item", 0.0)

    # 석탄 화력 발전소는 옆에 붙은 데이터 파워 노드의 출력 단계(T키로 조절)에 따라
    # 석탄/공기/배기 공급량을 한꺼번에 배율로 조절한다.
    if btype == "coal_power_plant" and "data_power_node" in parts:
        node_pos = parts["data_power_node"][0]
        level = world.buildings[node_pos].get("node_level", 2)
        mult = COAL_PLANT_NODE_LEVEL_MULT.get(level, COAL_PLANT_NODE_LEVEL_MULT[2])
        power *= mult["power"]
        pollution *= mult["pollution"]
        fuel_per_item *= mult["fuel_per_item"]
    return {"fuel_item": base["fuel_item"], "power": power,
            "pollution": max(0.0, pollution), "fuel_per_item": max(1.0, fuel_per_item)}

# 전력망 연결 판정에 포함되는 건물 타입 (발전기 / 소비 건물 / 와이어 / 연료발전기)
POWER_NODE_TYPES = (set(POWER_SUPPLY.keys()) | set(POWER_DRAW.keys()) | {"wire"}
                     | set(FUEL_BURNERS.keys()) | set(POWER_STORAGE.keys())
                     | {"transformer", "power_meter"})

COAL_POLLUTION_RATE = 0.8      # 석탄 발전기 1개, 초당 (낮춤)
OIL_GEN_POLLUTION_RATE = 1.3    # 오일 발전기 1개, 초당 (강력한 대신 오염이 큼, 낮춤)
MINER_POLLUTION_RATE = 0.18     # 채굴기/오일펌프 1개, 초당 (낮춤)
POLLUTION_DECAY = 0.5           # 자연 감소량 (약간 늘림, 전체적으로 오염이 천천히 쌓이도록)


# ----------------------------------------------------------------------
# 자원 매장 - 부지 전체가 모든 광물/액체를 다 뽑을 수 있는 땅이라, 특정 광맥 위치를
# 따로 관리할 필요가 없다. 채굴기류는 DEPOSIT_OUTPUT에 등록된 자기 고유의 자원을
# 어디에 설치하든 바로 생산한다 (World._update_extractors 참고).
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# 유틸리티
# ----------------------------------------------------------------------
def snap_dir_from_yaw(yaw):
    yaw = yaw % 360
    if 45 <= yaw < 135:
        return "S"
    if 135 <= yaw < 225:
        return "W"
    if 225 <= yaw < 315:
        return "N"
    return "E"


ROTATION_ORDER = ["N", "E", "S", "W"]  # 시계방향 순서 (R키로 이 순서를 따라 회전)


def rotate_dir(base_dir, steps):
    """base_dir을 시계방향으로 steps*90도 회전시킨 방향을 반환"""
    idx = (ROTATION_ORDER.index(base_dir) + steps) % 4
    return ROTATION_ORDER[idx]


def gl_perspective(fovy_deg, aspect, znear, zfar):
    """gluPerspective를 대체하는 순수 core-GL 구현 (일부 환경에 GLU가 없어도 동작하도록)."""
    fh = math.tan(math.radians(fovy_deg) / 2.0) * znear
    fw = fh * aspect
    glFrustum(-fw, fw, -fh, fh, znear, zfar)


def gl_look_at(eyex, eyey, eyez, centerx, centery, centerz, upx, upy, upz):
    """gluLookAt을 대체하는 순수 core-GL 구현 (일부 환경에 GLU가 없어도 동작하도록)."""
    fx, fy, fz = centerx - eyex, centery - eyey, centerz - eyez
    flen = math.sqrt(fx * fx + fy * fy + fz * fz) or 1.0
    fx, fy, fz = fx / flen, fy / flen, fz / flen

    ulen = math.sqrt(upx * upx + upy * upy + upz * upz) or 1.0
    upx, upy, upz = upx / ulen, upy / ulen, upz / ulen

    sx, sy, sz = fy * upz - fz * upy, fz * upx - fx * upz, fx * upy - fy * upx
    slen = math.sqrt(sx * sx + sy * sy + sz * sz) or 1.0
    sx, sy, sz = sx / slen, sy / slen, sz / slen

    ux, uy, uz = sy * fz - sz * fy, sz * fx - sx * fz, sx * fy - sy * fx

    matrix = (
        sx, ux, -fx, 0.0,
        sy, uy, -fy, 0.0,
        sz, uz, -fz, 0.0,
        0.0, 0.0, 0.0, 1.0,
    )
    glMultMatrixf(matrix)
    glTranslatef(-eyex, -eyey, -eyez)


def draw_cube(cx, cy, cz, sx, sy, sz, color):
    r, g, b = color
    top = (min(r * 1.25, 1.0), min(g * 1.25, 1.0), min(b * 1.25, 1.0))
    side = (r * 0.75, g * 0.75, b * 0.75)
    bottom = (r * 0.5, g * 0.5, b * 0.5)

    x0, x1 = cx - sx / 2, cx + sx / 2
    y0, y1 = cy - sy / 2, cy + sy / 2
    z0, z1 = cz - sz / 2, cz + sz / 2

    glBegin(GL_QUADS)
    glColor3f(*top)
    glVertex3f(x0, y1, z0); glVertex3f(x1, y1, z0)
    glVertex3f(x1, y1, z1); glVertex3f(x0, y1, z1)
    glColor3f(*bottom)
    glVertex3f(x0, y0, z1); glVertex3f(x1, y0, z1)
    glVertex3f(x1, y0, z0); glVertex3f(x0, y0, z0)
    glColor3f(*side)
    glVertex3f(x0, y0, z1); glVertex3f(x1, y0, z1)
    glVertex3f(x1, y1, z1); glVertex3f(x0, y1, z1)
    glVertex3f(x1, y0, z0); glVertex3f(x0, y0, z0)
    glVertex3f(x0, y1, z0); glVertex3f(x1, y1, z0)
    glVertex3f(x0, y0, z0); glVertex3f(x0, y0, z1)
    glVertex3f(x0, y1, z1); glVertex3f(x0, y1, z0)
    glVertex3f(x1, y0, z1); glVertex3f(x1, y0, z0)
    glVertex3f(x1, y1, z0); glVertex3f(x1, y1, z1)
    glEnd()


def draw_pyramid(cx, y0, cz, base_size, height, color):
    """cx,cz 중심의 정사각 밑면에서 y0 높이에서 시작해 (y0+height)의 꼭짓점으로 모이는 각뿔.
    height가 음수면 아래로 향하는 뾰족한 모양(드릴 날 등)이 된다."""
    r, g, b = color
    top_c = (min(r * 1.2, 1.0), min(g * 1.2, 1.0), min(b * 1.2, 1.0))
    side_c = (r * 0.8, g * 0.8, b * 0.8)
    hs = base_size / 2
    apex = (cx, y0 + height, cz)
    corners = [
        (cx - hs, y0, cz - hs), (cx + hs, y0, cz - hs),
        (cx + hs, y0, cz + hs), (cx - hs, y0, cz + hs),
    ]
    glBegin(GL_TRIANGLES)
    for i in range(4):
        p1, p2 = corners[i], corners[(i + 1) % 4]
        glColor3f(*(top_c if i % 2 == 0 else side_c))
        glVertex3f(*apex); glVertex3f(*p1); glVertex3f(*p2)
    glEnd()


def draw_cylinder(cx, y0, cz, radius, height, color, sides=8):
    r, g, b = color
    top_c = (min(r * 1.2, 1.0), min(g * 1.2, 1.0), min(b * 1.2, 1.0))
    side_c = (r * 0.75, g * 0.75, b * 0.75)
    bottom_c = (r * 0.5, g * 0.5, b * 0.5)

    top_pts, bot_pts = [], []
    for i in range(sides):
        a = 2 * math.pi * i / sides
        dx, dz = radius * math.cos(a), radius * math.sin(a)
        top_pts.append((cx + dx, y0 + height, cz + dz))
        bot_pts.append((cx + dx, y0, cz + dz))

    glColor3f(*side_c)
    glBegin(GL_QUADS)
    for i in range(sides):
        j = (i + 1) % sides
        glVertex3f(*bot_pts[i]); glVertex3f(*bot_pts[j])
        glVertex3f(*top_pts[j]); glVertex3f(*top_pts[i])
    glEnd()

    glColor3f(*top_c)
    glBegin(GL_TRIANGLE_FAN)
    glVertex3f(cx, y0 + height, cz)
    for p in top_pts + [top_pts[0]]:
        glVertex3f(*p)
    glEnd()

    glColor3f(*bottom_c)
    glBegin(GL_TRIANGLE_FAN)
    glVertex3f(cx, y0, cz)
    for p in list(reversed(bot_pts)) + [bot_pts[-1]]:
        glVertex3f(*p)
    glEnd()


def draw_ground_arrow(cx, cz, dx, dz, size, color):
    """바닥에 살짝 뜬 평평한 화살표 - 건물의 출력 방향(dir)을 표시"""
    px, pz = -dz, dx
    tip = (cx + dx * size, 0.03, cz + dz * size)
    b1 = (cx - dx * size * 0.35 + px * size * 0.35, 0.03, cz - dz * size * 0.35 + pz * size * 0.35)
    b2 = (cx - dx * size * 0.35 - px * size * 0.35, 0.03, cz - dz * size * 0.35 - pz * size * 0.35)
    glColor3f(*color)
    glBegin(GL_TRIANGLES)
    glVertex3f(*tip); glVertex3f(*b1); glVertex3f(*b2)
    glEnd()


# ---- Industrialist 스타일 공통 자재 색 ----------------------------------------
# 원작은 알록달록한 블록이 아니라 "콘크리트 기초 위에 올린 강철 설비"에 가까운 톤이라,
# 건물마다 제각각이던 원색을 그대로 쓰지 않고 아래 자재 색들로 전체를 묶는다.
CONCRETE = (0.60, 0.59, 0.56)
CONCRETE_DARK = (0.44, 0.43, 0.41)
STEEL_TRIM = (0.30, 0.31, 0.34)
SAFETY = (0.93, 0.72, 0.12)      # 안전 표시용 노란색

# 바닥에 깔리는 운반 설비들은 기초를 깔면 오히려 지저분해져서 제외한다.
_FLAT_TYPES = (CONVEYOR_LIKE | PIPE_LIKE | CROSSROAD_TYPES
               | {"wire", "item_filter", "drone_payload"})


def industrial_tint(c, keep=0.34):
    """건물 고유색의 채도를 낮춰 산업 설비다운 강철 톤으로 바꾼다.
    원래 색조를 keep 비율만 남기고 나머지는 밝기에 맞춘 강철색으로 섞어서,
    건물 종류는 여전히 구분되면서 전체 화면 톤은 하나로 묶이도록 한다."""
    lum = 0.30 * c[0] + 0.59 * c[1] + 0.11 * c[2]
    steel = (0.44 + lum * 0.26, 0.45 + lum * 0.26, 0.49 + lum * 0.26)
    return tuple(c[i] * keep + steel[i] * (1.0 - keep) for i in range(3))


def _draw_industrial_base(btype, accent, active, anim_t):
    """모든 건물 아래에 공통으로 깔리는 콘크리트 기초 + 금속 트림 + 안전색 액센트.
    개별 모델을 그리기 전에 호출되며, 건물마다 달랐던 실루엣을 하나의 설비 디자인
    언어로 묶어주는 역할을 한다. 컨베이어/파이프 같은 바닥 운반물은 제외."""
    if btype in _FLAT_TYPES:
        return
    # 콘크리트 패드 (본체보다 살짝 넓게)
    draw_cube(0.0, 0.04, 0.0, CELL * 0.99, 0.08, CELL * 0.99, CONCRETE)
    draw_cube(0.0, 0.09, 0.0, CELL * 0.86, 0.03, CELL * 0.86, CONCRETE_DARK)
    # 패드 네 귀퉁이의 앵커 볼트 겸 금속 트림
    for dx, dz in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        draw_cube(dx * CELL * 0.43, 0.12, dz * CELL * 0.43, 0.13, 0.14, 0.13, STEEL_TRIM)
    # 건물 종류를 구분해주는 안전색 액센트 띠 (앞쪽 모서리)
    draw_cube(0.0, 0.115, CELL * 0.45, CELL * 0.62, 0.05, 0.07, accent)


# ---- Industrialist 스타일 설비 부품 라이브러리 --------------------------------
# 원작 설비는 "단순한 상자"가 아니라 탱크에 보강 밴드가 감기고, 난간과 사다리가 붙고,
# 배관이 밖으로 뻗어 나오는 형태다. 건물마다 이런 디테일을 일일이 손으로 쌓아 올릴 수
# 있도록 자주 쓰는 부품을 여기 모아둔다.
def part_tank(x, y, z, r, h, c, sides=12, bands=2):
    """보강 밴드가 감긴 수직 탱크 (상·하단 플랜지 포함)"""
    draw_cylinder(x, y, z, r, h, c, sides=sides)
    fl = (c[0] * 0.62, c[1] * 0.62, c[2] * 0.62)
    draw_cylinder(x, y + h, z, r * 1.09, 0.06, fl, sides=sides)
    draw_cylinder(x, y, z, r * 1.09, 0.06, fl, sides=sides)
    for i in range(bands):
        by = y + h * (i + 1) / (bands + 1)
        draw_cylinder(x, by, z, r * 1.05, 0.05, STEEL_TRIM, sides=sides)


def part_frame(x, y, z, w, h, d, c, post=0.09):
    """네 귀퉁이 기둥 + 상단 보 로 이루어진 구조 프레임"""
    for dx in (-1, 1):
        for dz in (-1, 1):
            draw_cube(x + dx * w / 2, y + h / 2, z + dz * d / 2, post, h, post, c)
    draw_cube(x, y + h, z, w + post, post, post, c)
    draw_cube(x, y + h, z, post, post, d + post, c)


def part_railing(x, y, z, w, d, c=STEEL_TRIM, hgt=0.34):
    """작업 발판 둘레의 난간 (기둥 4개 + 위쪽 가로대)"""
    for dx, dz in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        draw_cube(x + dx * w / 2, y + hgt / 2, z + dz * d / 2, 0.06, hgt, 0.06, c)
    for dz in (-1, 1):
        draw_cube(x, y + hgt, z + dz * d / 2, w, 0.045, 0.045, c)
    for dx in (-1, 1):
        draw_cube(x + dx * w / 2, y + hgt, z, 0.045, 0.045, d, c)


def part_ladder(x, y, z, h, c=STEEL_TRIM):
    """설비 옆면에 붙는 점검용 사다리"""
    draw_cube(x - 0.10, y + h / 2, z, 0.035, h, 0.035, c)
    draw_cube(x + 0.10, y + h / 2, z, 0.035, h, 0.035, c)
    n = max(2, int(h / 0.22))
    for i in range(n):
        draw_cube(x, y + h * (i + 0.5) / n, z, 0.22, 0.03, 0.03, c)


def part_pipe(x, y, z, dx, dy, dz, length, r=0.09, c=None):
    """설비에서 뻗어 나오는 배관 한 구간 (축 방향으로만)"""
    c = c or (0.52, 0.54, 0.57)
    if dy:
        draw_cylinder(x, y, z, r, length * dy, c, sides=8)
    else:
        draw_cube(x + dx * length / 2, y, z + dz * length / 2,
                  length if dx else r * 2, r * 2, length if dz else r * 2, c)


def part_panel(x, y, z, c, blink=False, w=0.38):
    """표시등이 달린 제어 패널"""
    draw_cube(x, y, z, w, w * 0.72, 0.07, (0.17, 0.18, 0.20))
    lamp = (0.25, 0.95, 0.35) if blink else (0.12, 0.34, 0.16)
    draw_cube(x - w * 0.24, y + w * 0.16, z + 0.05, 0.07, 0.07, 0.04, lamp)
    draw_cube(x, y + w * 0.16, z + 0.05, 0.07, 0.07, 0.04, SAFETY)
    draw_cube(x + w * 0.24, y + w * 0.16, z + 0.05, 0.07, 0.07, 0.04, (0.30, 0.55, 0.85))
    draw_cube(x, y - w * 0.14, z + 0.05, w * 0.62, 0.10, 0.03, (0.35, 0.37, 0.40))


def part_vent(x, y, z, r, c=STEEL_TRIM, h=0.5):
    """지붕 위 배기 후드/환기구"""
    draw_cylinder(x, y, z, r, h, c, sides=8)
    draw_cylinder(x, y + h, z, r * 1.3, 0.07, (c[0] * 1.2, c[1] * 1.2, c[2] * 1.2), sides=8)


def part_stack(x, y, z, r, h, c=(0.24, 0.23, 0.22), banded=True):
    """굴뚝 - 위로 갈수록 살짝 좁아지고 상단에 경고 밴드"""
    draw_cylinder(x, y, z, r, h, c, sides=10)
    if banded:
        draw_cylinder(x, y + h * 0.72, z, r * 1.12, 0.09, SAFETY, sides=10)
        draw_cylinder(x, y + h, z, r * 1.15, 0.06, (0.15, 0.15, 0.15), sides=10)


def part_smoke(x, y, z, anim_t, active, scale=1.0):
    """굴뚝 위로 피어오르는 연기 (활성일 때만)"""
    if not active:
        return
    for i in range(3):
        p = (anim_t * 0.55 + i / 3.0) % 1.0
        s = (0.13 + p * 0.26) * scale
        g = 0.72 - p * 0.30
        draw_cube(x + math.sin(p * 5.0 + i) * 0.12, y + p * 1.5, z, s, s, s, (g, g, g * 1.02))


def draw_building_model(btype, wx, wz, color, facing_deg=0.0, anim_t=0.0, active=True,
                         gauge=None, connects=None, filter_color=None):
    """건물 타입별로 기본 도형(큐브/원기둥/각뿔)을 조합해 서로 다른 실루엣을 만든다.
    facing_deg만큼 건물의 수직축(Y)을 기준으로 회전시켜서, R키로 돌린 방향이
    실제 모델 모양에도 반영되도록 한다. active=True일 때만 동작 애니메이션이 재생된다.
    gauge는 전력 속도 카운터/배터리처럼 수치(0~1 또는 부호 있는 흐름값)를 게이지로
    보여줘야 하는 건물에 한해 World.draw()가 넘겨주는 부가 값이다.
    connects는 일반 파이프 전용으로, 이 칸과 실제로 이어 붙여야 할 이웃 방향들을
    월드 좌표계 단위벡터 (dx, dz) 목록으로 받는다(예: [(1,0), (0,-1)]).
    filter_color는 item_filter 전용으로, F로 선택해둔 아이템의 색(없으면 None)을 받아
    게이트 부분에 그 색을 입혀서 지금 무엇을 거르고 있는지 한눈에 보이게 한다.

    Industrialist의 설비 디자인 언어를 따르기 위해, 개별 실루엣을 그리기 전에
    공통으로 콘크리트 기초 + 금속 트림 + 안전색 액센트를 깔고(_draw_industrial_base),
    본체 색은 채도를 낮춘 강철 톤(industrial_tint)으로 바꿔서 전체 톤을 통일한다."""
    accent = color                      # 원래 색은 건물 종류 구분용 액센트로만 남긴다
    color = industrial_tint(color)      # 본체는 채도 낮은 산업용 강철 톤
    glPushMatrix()
    glTranslatef(wx, 0.0, wz)
    glRotatef(facing_deg, 0.0, 1.0, 0.0)
    _draw_model_geometry(btype, color, accent, anim_t, active, gauge, connects,
                          filter_color, facing_deg)
    glPopMatrix()


def _draw_model_geometry(btype, color, accent, anim_t, active, gauge, connects,
                          filter_color, facing_deg):
    """건물 모델의 실제 형상만 그린다(위치/회전은 호출부가 이미 걸어둔 상태).
    위치 변환과 분리해 둔 덕분에 draw_buildings_batched()가 같은 종류·같은 상태의
    건물을 디스플레이 리스트 하나로 묶어 재사용할 수 있다."""
    _draw_industrial_base(btype, accent, active, anim_t)

    if btype == "conveyor":
        # 강철 프레임 벨트: 측면 새시 + 하부 지지 다리 + 롤러 + 흐르는 벨트 무늬
        frame = (0.34, 0.35, 0.38)
        draw_cube(0.0, 0.09, 0.0, CELL * 0.94, 0.10, CELL * 0.62, frame)      # 하부 새시
        draw_cube(0.0, 0.20, 0.0, CELL * 0.94, 0.12, CELL * 0.56, (0.17, 0.17, 0.18))  # 벨트면
        for dz in (-1, 1):                                                     # 측면 가드
            draw_cube(0.0, 0.22, dz * CELL * 0.31, CELL * 0.94, 0.14, 0.06, color)
        for dx in (-1, 1):                                                     # 지지 다리
            draw_cube(dx * CELL * 0.36, 0.04, 0.0, 0.09, 0.09, CELL * 0.5, frame)
        for dx in (-1, 1):                                                     # 양 끝 롤러
            draw_cylinder(dx * CELL * 0.44, 0.20, 0.0, 0.075, CELL * 0.5, (0.55, 0.56, 0.58), sides=8)
        for i in range(4):                                                     # 벨트 클리트
            phase = ((anim_t * 1.4 + i / 4.0) % 1.0) - 0.5
            draw_cube(phase * CELL * 0.88, 0.27, 0.0, 0.07, 0.035, CELL * 0.5, (0.30, 0.31, 0.33))

    elif btype == "item_filter":
        # 벨트 위에 얹은 광학 선별 게이트: 문틀 + 스캐너 헤드 + 선택 아이템 색 커튼
        frame = (0.34, 0.35, 0.38)
        draw_cube(0.0, 0.09, 0.0, CELL * 0.94, 0.10, CELL * 0.62, frame)
        draw_cube(0.0, 0.20, 0.0, CELL * 0.94, 0.12, CELL * 0.56, (0.17, 0.17, 0.18))
        gate_color = filter_color if filter_color is not None else (0.72, 0.74, 0.78)
        for dz in (-1, 1):                                                     # 게이트 기둥
            draw_cube(0.0, 0.55, dz * CELL * 0.33, 0.13, 0.66, 0.13, color)
        draw_cube(0.0, 0.90, 0.0, 0.16, 0.13, CELL * 0.78, STEEL_TRIM)         # 상단 보
        scan = (0.85 + 0.15 * abs(math.sin(anim_t * 3.0))) if active else 1.0
        draw_cube(0.0, 0.52, 0.0, 0.05, 0.48 * scan, CELL * 0.62, gate_color)  # 선별 커튼
        draw_cube(0.0, 0.90, CELL * 0.20, 0.14, 0.10, 0.14, gate_color)        # 스캐너 헤드

    elif btype == "drone_transporter":
        # 관제탑형 이착륙장: 콘크리트 위 관제동 + 격자 마스트 + 회전 레이더 + 비콘
        draw_cube(0.0, 0.32, -CELL * 0.22, CELL * 0.66, 0.5, CELL * 0.42, color)   # 관제동
        part_panel(0.0, 0.40, -CELL * 0.44, color, blink=active and int(anim_t * 2) % 2 == 0)
        draw_cube(0.0, 0.16, CELL * 0.26, CELL * 0.8, 0.1, CELL * 0.42, (0.28, 0.29, 0.31))  # 패드
        draw_cube(0.0, 0.22, CELL * 0.26, CELL * 0.5, 0.03, 0.07, SAFETY)           # 패드 마킹
        draw_cube(0.0, 0.22, CELL * 0.26, 0.07, 0.03, CELL * 0.3, SAFETY)
        part_frame(0.0, 0.55, -CELL * 0.22, 0.34, 0.85, 0.34, STEEL_TRIM, post=0.06)  # 마스트
        glPushMatrix()                                                              # 회전 레이더
        glTranslatef(0.0, 1.45, -CELL * 0.22)
        glRotatef(anim_t * 70.0 if active else 0.0, 0.0, 1.0, 0.0)
        draw_cube(0.16, 0.0, 0.0, 0.30, 0.20, 0.04, (0.80, 0.82, 0.85))
        glPopMatrix()
        pulse = (0.6 + 0.4 * abs(math.sin(anim_t * 4.0))) if active else 0.3
        beacon_color = filter_color if filter_color is not None else (0.5, 0.5, 0.55)
        draw_cube(0.0, 1.62, -CELL * 0.22, 0.17, 0.17 * pulse, 0.17, beacon_color)  # 화물 비콘

    elif btype == "drone_payload":
        # 드론 착륙 패드: 콘크리트 패드 + H 마킹 + 유도등 4개 + 화물 배출 롤러
        draw_cube(0.0, 0.07, 0.0, CELL * 0.96, 0.14, CELL * 0.96, (0.34, 0.35, 0.37))
        mark = filter_color if filter_color is not None else (0.85, 0.85, 0.88)
        draw_cube(0.0, 0.15, -CELL * 0.16, CELL * 0.4, 0.03, 0.08, mark)
        draw_cube(0.0, 0.15, CELL * 0.16, CELL * 0.4, 0.03, 0.08, mark)
        draw_cube(0.0, 0.15, 0.0, 0.09, 0.03, CELL * 0.32, mark)
        blink = active and int(anim_t * 3.0) % 2 == 0
        for dx, dz in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            draw_cube(dx * CELL * 0.42, 0.18, dz * CELL * 0.42, 0.1, 0.06, 0.1,
                      SAFETY if blink else (0.4, 0.34, 0.12))
        for dx in (-1, 1):
            draw_cylinder(dx * CELL * 0.42, 0.16, 0.0, 0.05, CELL * 0.4, (0.55, 0.56, 0.6), sides=6)

    elif btype == "wire":
        # 배전 철탑: H형 콘크리트 기둥 + 애자 3련 + 늘어진 전선 + 접지선
        for dx in (-1, 1):
            draw_cube(dx * 0.16, 0.5, 0.0, 0.09, 1.0, 0.09, (0.55, 0.54, 0.5))
        draw_cube(0.0, 0.92, 0.0, 0.46, 0.08, 0.08, (0.55, 0.54, 0.5))
        for dx in (-1, 0, 1):
            draw_cylinder(dx * 0.2, 0.96, 0.0, 0.035, 0.12, (0.72, 0.72, 0.66), sides=6)
        for dx in (-1, 0, 1):
            draw_cube(dx * 0.2, 1.09, 0.0, CELL * 0.98, 0.03, 0.03, (0.16, 0.16, 0.17))
        draw_cube(0.0, 0.66, 0.0, CELL * 0.98, 0.022, 0.022, (0.2, 0.2, 0.21))

    elif btype == "pipe":
        # 배관: 파이프 랙 받침 위에 올린 배관 + 볼트 플랜지 + 이웃 방향 연결관
        draw_cube(0.0, 0.06, 0.0, CELL * 0.34, 0.12, CELL * 0.34, (0.42, 0.41, 0.39))
        for dz in (-1, 1):
            draw_cube(0.0, 0.16, dz * 0.14, 0.1, 0.2, 0.06, STEEL_TRIM)
        draw_cylinder(0.0, 0.26, 0.0, 0.15, 0.2, color, sides=12)
        draw_cylinder(0.0, 0.46, 0.0, 0.19, 0.05, STEEL_TRIM, sides=12)
        if connects:
            glPushMatrix()
            glRotatef(-facing_deg, 0.0, 1.0, 0.0)
            for dx, dz in connects:
                draw_cube(dx * CELL * 0.32, 0.36, dz * CELL * 0.32,
                          CELL * 0.44 if dx else 0.22, 0.22,
                          CELL * 0.44 if dz else 0.22, color)
                draw_cube(dx * CELL * 0.16, 0.36, dz * CELL * 0.16, 0.26, 0.26, 0.26, STEEL_TRIM)
            glPopMatrix()

    elif btype == "conveyor_3way":
        # 3방향 합류 벨트: 본선 + 측면 합류 슈트 + 합류부 가이드
        frame = (0.34, 0.35, 0.38)
        draw_cube(0.0, 0.09, 0.0, CELL * 0.94, 0.1, CELL * 0.62, frame)
        draw_cube(0.0, 0.2, 0.0, CELL * 0.94, 0.12, CELL * 0.56, (0.17, 0.17, 0.18))
        draw_cube(0.0, 0.2, CELL * 0.34, CELL * 0.4, 0.12, CELL * 0.46, (0.17, 0.17, 0.18))
        draw_cube(0.0, 0.09, CELL * 0.34, CELL * 0.42, 0.1, CELL * 0.46, frame)
        draw_cube(0.0, 0.28, -CELL * 0.3, CELL * 0.94, 0.16, 0.06, color)
        for dx in (-1, 1):
            draw_cube(dx * CELL * 0.24, 0.28, CELL * 0.12, 0.06, 0.16, CELL * 0.3, color)
        for i in range(4):
            p = ((anim_t * 1.4 + i / 4.0) % 1.0) - 0.5
            draw_cube(p * CELL * 0.88, 0.27, 0.0, 0.07, 0.035, CELL * 0.5, (0.30, 0.31, 0.33))

    elif btype == "conveyor_4way":
        # 4방향 합류 벨트: 십자 데크 + 중앙 회전 디버터 + 사방 가이드
        frame = (0.34, 0.35, 0.38)
        draw_cube(0.0, 0.09, 0.0, CELL * 0.94, 0.1, CELL * 0.5, frame)
        draw_cube(0.0, 0.09, 0.0, CELL * 0.5, 0.1, CELL * 0.94, frame)
        draw_cube(0.0, 0.2, 0.0, CELL * 0.94, 0.12, CELL * 0.44, (0.17, 0.17, 0.18))
        draw_cube(0.0, 0.2, 0.0, CELL * 0.44, 0.12, CELL * 0.94, (0.17, 0.17, 0.18))
        glPushMatrix()
        glTranslatef(0.0, 0.3, 0.0)
        glRotatef(anim_t * 90.0, 0.0, 1.0, 0.0)
        draw_cube(0.0, 0.0, 0.0, 0.44, 0.06, 0.1, color)
        glPopMatrix()
        for dx, dz in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            draw_cube(dx * CELL * 0.36, 0.26, dz * CELL * 0.36, 0.16, 0.14, 0.16, STEEL_TRIM)

    elif btype == "pipe_3way":
        # 3방향 티 분기관: 본관 + 티 피팅 + 분기 밸브
        draw_cube(0.0, 0.06, 0.0, CELL * 0.34, 0.12, CELL * 0.34, (0.42, 0.41, 0.39))
        draw_cylinder(0.0, 0.26, 0.0, 0.15, 0.2, color, sides=12)
        draw_cube(0.0, 0.36, 0.0, CELL * 0.9, 0.2, 0.2, color)
        draw_cube(0.0, 0.36, CELL * 0.3, 0.2, 0.2, CELL * 0.5, color)
        draw_cube(0.0, 0.36, CELL * 0.18, 0.26, 0.26, 0.1, STEEL_TRIM)
        draw_cylinder(0.0, 0.5, CELL * 0.34, 0.05, 0.16, STEEL_TRIM, sides=6)
        draw_cube(0.0, 0.68, CELL * 0.34, 0.22, 0.04, 0.05, (0.78, 0.78, 0.8))

    elif btype == "pipe_4way":
        # 4방향 십자 분기관: 십자 헤더 + 네 방향 플랜지 + 중앙 점검구
        draw_cube(0.0, 0.06, 0.0, CELL * 0.4, 0.12, CELL * 0.4, (0.42, 0.41, 0.39))
        draw_cube(0.0, 0.36, 0.0, CELL * 0.9, 0.2, 0.2, color)
        draw_cube(0.0, 0.36, 0.0, 0.2, 0.2, CELL * 0.9, color)
        draw_cylinder(0.0, 0.26, 0.0, 0.17, 0.24, color, sides=12)
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            draw_cube(dx * CELL * 0.3, 0.36, dz * CELL * 0.3, 0.26, 0.26, 0.26, STEEL_TRIM)
        draw_cylinder(0.0, 0.5, 0.0, 0.1, 0.06, STEEL_TRIM, sides=8)

    elif btype == "conveyor_crossroad":
        # 벨트 교차로: 두 벨트가 높이를 달리해 교차 (위/아래로 지나감) + 위험 표시
        frame = (0.34, 0.35, 0.38)
        draw_cube(0.0, 0.09, 0.0, CELL * 0.96, 0.1, CELL * 0.34, frame)
        draw_cube(0.0, 0.2, 0.0, CELL * 0.96, 0.1, CELL * 0.3, (0.17, 0.17, 0.18))
        draw_cube(0.0, 0.32, 0.0, CELL * 0.34, 0.1, CELL * 0.96, frame)
        draw_cube(0.0, 0.42, 0.0, CELL * 0.3, 0.1, CELL * 0.96, (0.17, 0.17, 0.18))
        for dx, dz in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            draw_cube(dx * CELL * 0.34, 0.2, dz * CELL * 0.34, 0.1, 0.4, 0.1, STEEL_TRIM)
        for i in range(3):
            draw_cube((i - 1) * 0.18, 0.49, 0.0, 0.12, 0.02, CELL * 0.9,
                      SAFETY if i % 2 == 0 else (0.15, 0.15, 0.16))

    elif btype == "pipe_crossroad":
        # 파이프 교차로: 두 배관이 높이를 달리해 서로 넘어가는 크로스오버
        draw_cube(0.0, 0.06, 0.0, CELL * 0.4, 0.12, CELL * 0.4, (0.42, 0.41, 0.39))
        draw_cube(0.0, 0.3, 0.0, CELL * 0.94, 0.18, 0.18, color)
        draw_cube(0.0, 0.56, 0.0, 0.18, 0.18, CELL * 0.94, color)
        for dx in (-1, 1):
            draw_cylinder(dx * CELL * 0.2, 0.3, 0.0, 0.12, 0.28, color, sides=10)
        for dx, dz in ((1, 0), (-1, 0)):
            draw_cube(dx * CELL * 0.34, 0.3, 0.0, 0.24, 0.24, 0.24, STEEL_TRIM)
        for dz in (1, -1):
            draw_cube(0.0, 0.56, dz * CELL * 0.34, 0.24, 0.24, 0.24, STEEL_TRIM)

    elif btype == "hybrid_crossroad":
        # 유체-고체 교차로: 아래로 벨트, 위로 배관이 간섭 없이 지나가는 복합 교차부
        frame = (0.34, 0.35, 0.38)
        draw_cube(0.0, 0.09, 0.0, CELL * 0.96, 0.1, CELL * 0.36, frame)
        draw_cube(0.0, 0.2, 0.0, CELL * 0.96, 0.1, CELL * 0.32, (0.17, 0.17, 0.18))
        for dx in (-1, 1):
            draw_cube(dx * CELL * 0.32, 0.42, 0.0, 0.1, 0.48, 0.1, STEEL_TRIM)
        draw_cube(0.0, 0.68, 0.0, 0.2, 0.2, CELL * 0.96, (0.34, 0.56, 0.56))
        for dz in (1, -1):
            draw_cube(0.0, 0.68, dz * CELL * 0.34, 0.26, 0.26, 0.26, STEEL_TRIM)
        draw_cube(0.0, 0.3, 0.0, 0.2, 0.04, CELL * 0.3, SAFETY)

    elif btype in ("coal_miner", "copper_miner", "iron_miner",
                   "lead_miner", "sand_miner", "wood_cutter"):
        # 채굴기: 구동부 하우징 + 드릴 마스트 프레임 + 상하 운동하는 드릴 스트링 +
        # 캐낸 광석이 빠져나가는 배출 슈트. 캐는 자원은 액센트 색으로만 구분된다.
        bob = math.sin(anim_t * 5.0) * 0.14 if active else 0.0
        draw_cube(0.0, 0.42, -CELL * 0.14, CELL * 0.78, 0.64, CELL * 0.6, color)   # 구동부
        draw_cube(0.0, 0.76, -CELL * 0.14, CELL * 0.62, 0.06, CELL * 0.48, STEEL_TRIM)
        part_frame(0.0, 0.74, -CELL * 0.14, CELL * 0.5, 0.62, CELL * 0.36, STEEL_TRIM, post=0.07)
        draw_cylinder(0.0, 0.9 + bob, -CELL * 0.14, 0.13, 0.5, (0.62, 0.63, 0.66), sides=8)
        draw_cylinder(0.0, 0.2 + bob, -CELL * 0.14, 0.10, 0.75, (0.30, 0.30, 0.32), sides=8)
        draw_pyramid(0.0, 0.18 + bob, -CELL * 0.14, 0.44, -0.6, (0.23, 0.21, 0.19))  # 드릴 비트
        draw_cube(0.0, 0.30, CELL * 0.34, CELL * 0.42, 0.26, CELL * 0.28, STEEL_TRIM)  # 배출 슈트
        draw_cube(0.0, 0.20, CELL * 0.46, CELL * 0.34, 0.16, 0.07, accent)
        part_ladder(CELL * 0.42, 0.1, -CELL * 0.14, 0.66)

    elif btype == "blast_furnace":
        # 폭발로: 내화벽돌 노체에 강철 밴드를 두르고, 하부 출탕구에서 쇳물이 빛나며,
        # 열풍관과 굴뚝이 옆으로 뻗어 나가는 고로 형태.
        glow = (0.55 + 0.45 * abs(math.sin(anim_t * 2.2))) if active else 0.2
        ember = (1.0 * glow, 0.45 * glow, 0.10 * glow)
        part_tank(0.0, 0.12, 0.0, CELL * 0.36, 1.35, color, sides=12, bands=3)     # 노체
        draw_pyramid(0.0, 1.47, 0.0, CELL * 0.62, 0.34, (color[0] * 0.7, color[1] * 0.7, color[2] * 0.7))
        part_stack(CELL * 0.34, 1.5, -CELL * 0.26, 0.15, 1.0)                      # 굴뚝
        part_smoke(CELL * 0.34, 2.5, -CELL * 0.26, anim_t, active, 0.8)
        draw_cube(0.0, 0.42, CELL * 0.40, 0.5, 0.34, 0.14, ember)                  # 출탕구 불빛
        part_pipe(-CELL * 0.36, 0.85, 0.0, -1, 0, 0, CELL * 0.3, 0.10, (0.55, 0.42, 0.34))  # 열풍관
        part_railing(0.0, 1.2, 0.0, CELL * 0.86, CELL * 0.86)
        part_ladder(-CELL * 0.42, 0.1, 0.0, 1.1)

    elif btype == "lathe":
        # 선반: 주축대 + 심압대 사이에 물린 공작물이 회전하고, 공구대가 옆에 붙은 공작기계
        draw_cube(0.0, 0.30, 0.0, CELL * 0.92, 0.42, CELL * 0.5, color)            # 베드
        draw_cube(-CELL * 0.34, 0.62, 0.0, 0.34, 0.44, CELL * 0.44, STEEL_TRIM)    # 주축대
        draw_cube(CELL * 0.36, 0.58, 0.0, 0.24, 0.32, CELL * 0.36, STEEL_TRIM)     # 심압대
        spin = (anim_t * 400.0) if active else 0.0
        glPushMatrix()
        glTranslatef(0.0, 0.66, 0.0)
        glRotatef(90.0, 0.0, 0.0, 1.0)
        glRotatef(spin, 0.0, 1.0, 0.0)
        draw_cylinder(0.0, -0.34, 0.0, 0.11, 0.68, (0.78, 0.79, 0.82), sides=6)    # 공작물
        glPopMatrix()
        draw_cube(0.05, 0.60, CELL * 0.26, 0.2, 0.16, 0.2, accent)                 # 공구대
        part_panel(-CELL * 0.30, 0.62, CELL * 0.30, color,
                   blink=active and int(anim_t * 3) % 2 == 0, w=0.3)
        if active:                                                                  # 절삭 칩
            for i in range(3):
                p = (anim_t * 2.0 + i / 3.0) % 1.0
                draw_cube(0.05 + p * 0.2, 0.72 + p * 0.1, CELL * 0.26,
                          0.04, 0.04, 0.04, (0.85, 0.80, 0.6))

    elif btype == "mineshaft_drill":
        # 마인샤프트 드릴: 격자 데릭 + 크라운 블록 + 케이싱 헤드 + 회전 드릴 스트링.
        # gauge(1~4)는 굴착 깊이, filter_color는 장착된 드릴 헤드 색(없으면 회색).
        depth_level = int(gauge) if gauge is not None else 1
        head_color = filter_color if filter_color is not None else (0.35, 0.35, 0.38)
        draw_cube(0.0, 0.16, 0.0, CELL * 0.96, 0.24, CELL * 0.96, color)               # 리그 플랫폼
        # 위로 갈수록 좁아지는 데릭 4각 트러스
        for i in range(4):
            y0, y1 = 0.28 + i * 0.5, 0.78 + i * 0.5
            w0 = CELL * (0.4 - i * 0.07)
            for dx, dz in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                draw_cube(dx * w0, (y0 + y1) / 2, dz * w0, 0.09, 0.5, 0.09, STEEL_TRIM)
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                draw_cube(dx * w0, y1, dz * w0, 0.06 if dz else w0 * 2,
                          0.05, 0.06 if dx else w0 * 2, STEEL_TRIM)
        draw_cube(0.0, 2.32, 0.0, CELL * 0.3, 0.14, CELL * 0.3, STEEL_TRIM)            # 크라운 블록
        draw_cylinder(0.0, 2.12, 0.0, 0.07, 0.2, (0.6, 0.61, 0.64), sides=6)           # 트래블링 블록
        draw_cylinder(0.0, 0.4, 0.0, 0.2, 0.16, STEEL_TRIM, sides=10)                  # 케이싱 헤드
        spin = (anim_t * 260.0) if (active and filter_color is not None) else 0.0
        shaft_len = 0.6 + depth_level * 0.35
        glPushMatrix()
        glTranslatef(0.0, 0.3, 0.0)
        glRotatef(spin, 0.0, 1.0, 0.0)
        draw_cylinder(0.0, -shaft_len, 0.0, 0.11, shaft_len, head_color, sides=6)
        draw_pyramid(0.0, -shaft_len, 0.0, 0.28, -0.34, head_color)
        glPopMatrix()
        draw_cube(-CELL * 0.36, 0.42, CELL * 0.3, 0.22, 0.28, 0.24, accent)            # 머드 펌프
        for i in range(depth_level):                                                    # 깊이 표시등
            draw_cube(CELL * 0.4, 0.34 + i * 0.12, -CELL * 0.34, 0.08, 0.06, 0.08, SAFETY)

    elif btype == "fragment_processor":
        # 파편 분류기: 경사진 진동 스크린 데크 2단 + 편심 구동 모터 + 하부 배출 호퍼
        shake = (math.sin(anim_t * 8.0) * 0.045) if active else 0.0
        draw_cube(0.0, 0.30, 0.0, CELL * 0.86, 0.4, CELL * 0.7, color)              # 본체
        mesh = (0.58, 0.59, 0.62)
        for i, y in enumerate((0.62, 0.86)):                                        # 2단 스크린
            draw_cube(shake, y, 0.0, CELL * 0.88, 0.05, CELL * 0.66, mesh)
            for j in range(4):                                                       # 메시 살
                draw_cube(shake, y + 0.03, (j - 1.5) * CELL * 0.17,
                          CELL * 0.88, 0.02, 0.03, STEEL_TRIM)
        glPushMatrix()                                                               # 편심 구동
        glTranslatef(-CELL * 0.44, 0.74, 0.0)
        glRotatef(anim_t * 420.0 if active else 0.0, 1.0, 0.0, 0.0)
        draw_cube(0.0, 0.0, 0.09, 0.16, 0.16, 0.1, accent)
        glPopMatrix()
        draw_cube(0.0, 0.10, CELL * 0.42, CELL * 0.5, 0.2, 0.16, STEEL_TRIM)         # 배출구
        part_railing(0.0, 1.0, 0.0, CELL * 0.9, CELL * 0.7)

    elif btype == "ore_refiner":
        # 광석 정제기: 침출조 + 교반 모터 + 산 공급 배관 + 금 회수 슈트
        part_tank(0.0, 0.12, 0.0, CELL * 0.38, 0.95, color, sides=12, bands=2)
        bubble = (0.5 + 0.5 * abs(math.sin(anim_t * 4.0))) if active else 0.15
        draw_cylinder(0.0, 1.05, 0.0, CELL * 0.32, 0.10,
                      (0.85 * bubble, 0.85 * bubble, 0.22 * bubble), sides=12)       # 침출액 표면
        draw_cube(0.0, 1.30, 0.0, 0.22, 0.3, 0.22, STEEL_TRIM)                       # 교반 모터
        glPushMatrix()
        glTranslatef(0.0, 1.15, 0.0)
        glRotatef(anim_t * 160.0 if active else 0.0, 0.0, 1.0, 0.0)
        draw_cube(0.0, 0.0, 0.0, 0.5, 0.04, 0.07, (0.72, 0.74, 0.77))                # 교반 날개
        glPopMatrix()
        part_pipe(-CELL * 0.40, 0.85, 0.0, -1, 0, 0, CELL * 0.28, 0.08, (0.80, 0.82, 0.35))
        draw_cube(0.0, 0.34, CELL * 0.44, 0.3, 0.2, 0.12,
                  (0.95 * bubble, 0.75 * bubble, 0.08))                              # 금 회수구
        part_ladder(CELL * 0.42, 0.1, 0.0, 0.95)

    elif btype == "heavy_oil_separator":
        # 중유 분리기: 트레이가 층층이 쌓인 증류탑 + 측면 리보일러 + 상단 환류관
        part_tank(0.0, 0.1, 0.0, CELL * 0.32, 1.55, color, sides=12, bands=4)
        draw_pyramid(0.0, 1.65, 0.0, CELL * 0.5, 0.22, (color[0] * 0.7, color[1] * 0.7, color[2] * 0.7))
        for i in range(4):                                                            # 트레이 노즐
            draw_cube(CELL * 0.34, 0.35 + i * 0.33, 0.0, 0.14, 0.09, 0.14, STEEL_TRIM)
        draw_cylinder(-CELL * 0.34, 0.25, 0.0, 0.16, 0.75, (0.42, 0.40, 0.38), sides=8)  # 리보일러
        part_pipe(0.0, 1.72, 0.0, 0, 0, 1, CELL * 0.42, 0.08, (0.52, 0.54, 0.57))     # 환류관
        part_ladder(0.0, 0.1, -CELL * 0.36, 1.5)
        part_railing(0.0, 1.6, 0.0, CELL * 0.78, CELL * 0.78)

    elif btype == "oxidation_chamber":
        # 산화실: 내압 구형 반응조 + 산소 주입 노즐 + 안전 밸브. 반응 중이면 내부가 밝게 달아오름
        pulse = (0.5 + 0.5 * abs(math.sin(anim_t * 3.5))) if active else 0.2
        core_c = (0.40 * pulse + 0.20, 0.85 * pulse + 0.15, 1.0 * pulse * 0.6 + 0.2)
        draw_cylinder(0.0, 0.12, 0.0, CELL * 0.44, 0.22, color, sides=12)             # 받침 스커트
        part_tank(0.0, 0.34, 0.0, CELL * 0.34, 0.86, core_c, sides=14, bands=2)       # 반응조
        draw_pyramid(0.0, 1.20, 0.0, CELL * 0.5, 0.26, (color[0] * 0.75, color[1] * 0.75, color[2] * 0.75))
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):                             # 산소 주입 노즐
            draw_cube(dx * CELL * 0.36, 0.62, dz * CELL * 0.36, 0.12, 0.12, 0.12, (0.45, 0.68, 0.9))
        draw_cylinder(CELL * 0.2, 1.42, 0.0, 0.055, 0.3, STEEL_TRIM, sides=6)         # 안전 밸브
        draw_cube(CELL * 0.2, 1.75, 0.0, 0.14, 0.08, 0.14, SAFETY)
        part_ladder(-CELL * 0.40, 0.1, 0.0, 1.1)

    elif btype == "chemical_reactor":
        # 화학 반응기: 자켓형 교반 반응조 + 상단 구동 모터 + 원료 노즐 + 환류 응축기
        draw_cylinder(0.0, 0.12, 0.0, CELL * 0.4, 0.16, STEEL_TRIM, sides=12)          # 스커트
        part_tank(0.0, 0.28, 0.0, CELL * 0.34, 0.9, color, sides=14, bands=2)
        draw_pyramid(0.0, 1.18, 0.0, CELL * 0.52, 0.2,
                     (color[0] * 0.72, color[1] * 0.72, color[2] * 0.72))
        draw_cube(0.0, 1.5, 0.0, 0.26, 0.34, 0.26, STEEL_TRIM)                          # 구동 모터
        draw_cylinder(0.0, 1.3, 0.0, 0.06, 0.2, (0.6, 0.62, 0.66), sides=6)
        glPushMatrix()                                                                   # 교반 임펠러
        glTranslatef(0.0, 0.62, 0.0)
        glRotatef(anim_t * 180.0 if active else 0.0, 0.0, 1.0, 0.0)
        draw_cylinder(0.0, 0.0, 0.0, 0.035, 0.7, (0.66, 0.68, 0.72), sides=6)
        for a in range(3):
            glPushMatrix(); glRotatef(a * 120.0, 0.0, 1.0, 0.0)
            draw_cube(0.16, 0.05, 0.0, 0.26, 0.05, 0.09, (0.72, 0.74, 0.78))
            glPopMatrix()
        glPopMatrix()
        for dx, dz in ((1, 0), (-1, 0)):                                                 # 원료 노즐
            part_pipe(dx * CELL * 0.36, 0.95, dz, dx, 0, 0, CELL * 0.2, 0.07, (0.55, 0.57, 0.6))
        draw_cylinder(CELL * 0.36, 1.15, CELL * 0.24, 0.1, 0.42, (0.5, 0.58, 0.62), sides=10)
        pulse = (0.5 + 0.5 * abs(math.sin(anim_t * 3.5))) if active else 0.15
        draw_cylinder(0.0, 0.36, CELL * 0.3, 0.06, 0.05,
                      (0.9, 0.4 + 0.5 * pulse, 0.2), sides=8)                            # 온도계
        part_ladder(-CELL * 0.42, 0.12, 0.0, 1.05)

    elif btype == "electrolyzer":
        # 전해조: 전해액 셀 스택 + 좌우 기체 포집 드럼(수소/산소) + 상부 구리 버스바
        draw_cube(0.0, 0.28, 0.0, CELL * 0.9, 0.4, CELL * 0.72, color)               # 셀 하우징
        bubble = (0.5 + 0.5 * abs(math.sin(anim_t * 6.0))) if active else 0.15
        for i in range(5):                                                            # 전극 셀 스택
            draw_cube((i - 2) * CELL * 0.16, 0.62, 0.0, 0.1, 0.44, CELL * 0.56,
                      (0.30, 0.32, 0.36) if i % 2 else (0.52, 0.54, 0.58))
        h2 = (0.80 * bubble, 0.90 * bubble, 1.0 * bubble)
        o2 = (0.35 * bubble, 0.65 * bubble, 1.0 * bubble)
        part_tank(-CELL * 0.40, 0.5, CELL * 0.30, 0.16, 0.6, h2, sides=10, bands=1)   # 수소 드럼
        part_tank(CELL * 0.40, 0.5, CELL * 0.30, 0.16, 0.6, o2, sides=10, bands=1)    # 산소 드럼
        draw_cube(0.0, 0.92, 0.0, CELL * 0.86, 0.07, 0.09, (0.72, 0.55, 0.22))        # 구리 버스바
        draw_cube(0.0, 1.02, 0.0, CELL * 0.86, 0.07, 0.09, (0.30, 0.31, 0.34))
        part_panel(0.0, 0.55, -CELL * 0.42, color,
                   blink=active and int(anim_t * 4) % 2 == 0, w=0.32)

    elif btype == "air_separator":
        # 공기 분리기: 보냉재를 감은 저온 분리탑 + 4엽 흡기 팬 + 압축기 + 질소 취출관
        part_tank(0.0, 0.12, 0.0, CELL * 0.30, 1.45, color, sides=12, bands=3)
        draw_pyramid(0.0, 1.57, 0.0, CELL * 0.46, 0.2,
                     (color[0] * 0.7, color[1] * 0.7, color[2] * 0.7))
        draw_cylinder(0.0, 1.62, 0.0, 0.1, 0.22, STEEL_TRIM, sides=8)                 # 팬 지지대
        glPushMatrix()                                                                 # 흡기 팬
        glTranslatef(0.0, 1.86, 0.0)
        glRotatef(anim_t * 300.0 if active else 0.0, 0.0, 1.0, 0.0)
        for a in range(4):
            glPushMatrix(); glRotatef(a * 90.0, 0.0, 1.0, 0.0)
            draw_cube(0.24, 0.0, 0.0, 0.42, 0.04, 0.14, (0.86, 0.88, 0.91))
            glPopMatrix()
        glPopMatrix()
        part_pipe(CELL * 0.34, 0.75, 0.0, 1, 0, 0, CELL * 0.28, 0.09, (0.66, 0.68, 0.74))
        draw_cube(-CELL * 0.36, 0.45, 0.0, 0.2, 0.5, 0.24, STEEL_TRIM)                 # 압축기
        part_ladder(0.0, 0.1, CELL * 0.34, 1.4)

    elif btype == "steam_cracker":
        # 스팀 크래킹 플랜트: 분해로 본체 + 높이가 다른 분해탑 2기 + 배기 스택 + 방출 증기
        draw_cube(0.0, 0.24, 0.0, CELL * 0.92, 0.42, CELL * 0.86, color)              # 로 본체
        glow = (0.55 + 0.45 * abs(math.sin(anim_t * 2.6))) if active else 0.18
        draw_cube(0.0, 0.30, CELL * 0.44, 0.42, 0.24, 0.1,
                  (glow, glow * 0.42, 0.08))                                           # 버너 창
        part_tank(-CELL * 0.30, 0.45, 0.0, 0.19, 1.45, color, sides=10, bands=3)       # 분해탑 1
        part_tank(CELL * 0.30, 0.45, 0.0, 0.17, 1.1, color, sides=10, bands=2)         # 분해탑 2
        part_pipe(0.0, 1.55, 0.0, 1, 0, 0, CELL * 0.6, 0.07, (0.52, 0.54, 0.57))       # 연결 배관
        part_stack(0.0, 0.66, -CELL * 0.36, 0.12, 0.95)                                # 배기 스택
        part_smoke(0.0, 1.61, -CELL * 0.36, anim_t, active, 0.7)
        if active:
            puff = 0.14 + 0.06 * abs(math.sin(anim_t * 3.0))
            draw_cube(-CELL * 0.30, 2.02, 0.0, puff, puff, puff, (0.92, 0.92, 0.96))
        part_railing(0.0, 0.46, 0.0, CELL * 0.92, CELL * 0.86)

    elif btype == "plastic_refinery":
        # 플라스틱 정제소: 반응조 + 나선 응축 코일 + 원료 계량 탱크 2기 + 제어 패널
        draw_cube(0.0, 0.4, -CELL * 0.10, CELL * 0.86, 0.64, CELL * 0.6, color)        # 반응조
        coil = (0.70, 0.74, 0.78)
        bob = (math.sin(anim_t * 3.0) * 0.04) if active else 0.0
        for i in range(5):                                                              # 응축 코일
            draw_cylinder(0.0, 0.78 + i * 0.13 + bob, -CELL * 0.10, 0.24, 0.055, coil, sides=12)
        draw_cylinder(0.0, 1.45, -CELL * 0.10, 0.09, 0.24, STEEL_TRIM, sides=8)
        part_tank(-CELL * 0.34, 0.12, CELL * 0.36, 0.14, 0.52, accent, sides=10, bands=1)
        part_tank(CELL * 0.34, 0.12, CELL * 0.36, 0.14, 0.52, accent, sides=10, bands=1)
        part_panel(0.0, 0.5, CELL * 0.42, color,
                   blink=active and int(anim_t * 3) % 2 == 0, w=0.3)
        part_ladder(-CELL * 0.44, 0.1, -CELL * 0.10, 0.75)

    elif btype == "furnace":
        # 제련로: 내화벽돌 노체 + 보강 밴드 + 장입 호퍼 + 굴뚝 + 출탕 슈트
        glow = (0.6 + 0.4 * abs(math.sin(anim_t * 3.0))) if active else 0.25
        draw_cube(0.0, 0.55, 0.0, CELL * 0.82, 1.02, CELL * 0.78, color)
        for i in range(3):
            draw_cube(0.0, 0.28 + i * 0.34, 0.0, CELL * 0.86, 0.05, CELL * 0.82, STEEL_TRIM)
        draw_pyramid(0.0, 1.06, 0.0, CELL * 0.62, 0.3,
                     (color[0] * 0.72, color[1] * 0.72, color[2] * 0.72))
        part_stack(CELL * 0.32, 1.3, -CELL * 0.24, 0.13, 0.8)
        part_smoke(CELL * 0.32, 2.1, -CELL * 0.24, anim_t, active, 0.6)
        fire = (1.0 * glow, 0.55 * glow, 0.15 * glow)
        draw_cube(0.0, 0.38, CELL * 0.41, 0.36, 0.28, 0.1, fire)                        # 관찰창
        draw_cube(0.0, 0.16, CELL * 0.44, 0.44, 0.14, 0.14, STEEL_TRIM)                 # 출탕 슈트
        part_ladder(-CELL * 0.42, 0.1, 0.0, 1.0)

    elif btype == "press":
        # 압연기: 문형 프레임 + 유압 실린더 + 내리찍는 램 + 앤빌 + 배출 롤러
        bob = (math.sin(anim_t * 4.0) * 0.5 + 0.5) if active else 0.0
        draw_cube(0.0, 0.26, 0.0, CELL * 0.86, 0.4, CELL * 0.78, color)                 # 베드
        draw_cube(0.0, 0.5, 0.0, CELL * 0.62, 0.12, CELL * 0.56, (0.30, 0.31, 0.34))    # 앤빌
        for dz in (-1, 1):
            draw_cube(0.0, 1.0, dz * CELL * 0.36, 0.16, 1.2, 0.16, STEEL_TRIM)          # 기둥
        draw_cube(0.0, 1.66, 0.0, CELL * 0.5, 0.16, CELL * 0.82, STEEL_TRIM)            # 상부 보
        draw_cylinder(0.0, 1.12 - bob * 0.16, 0.0, 0.2, 0.5, (0.62, 0.63, 0.67), sides=10)
        draw_cube(0.0, 0.94 - bob * 0.2, 0.0, CELL * 0.52, 0.2, CELL * 0.5,
                  (0.48, 0.49, 0.53))                                                    # 램
        for dx in (-1, 1):
            draw_cylinder(dx * CELL * 0.44, 0.56, 0.0, 0.07, CELL * 0.44,
                          (0.55, 0.56, 0.6), sides=8)                                    # 배출 롤러
        part_panel(CELL * 0.30, 0.62, -CELL * 0.42, color, blink=active and bob > 0.5, w=0.28)

    elif btype == "core":
        # 코어: 콘크리트 기단 + 컨테이너 창고동 + 관제 타워 + 회전 궤도 링 + 착륙 마킹
        base = (color[0] * 0.5, color[1] * 0.5, color[2] * 0.5)
        draw_cube(0.0, 0.14, 0.0, CELL * 1.0, 0.28, CELL * 1.0, base)
        for dx, dz in ((1, 1), (1, -1), (-1, 1), (-1, -1)):                                # 코너 마킹
            draw_cube(dx * CELL * 0.4, 0.29, dz * CELL * 0.4, 0.2, 0.02, 0.2, SAFETY)
        draw_cube(0.0, 0.58, 0.0, CELL * 0.78, 0.6, CELL * 0.78, color)                    # 창고동
        for i in range(3):                                                                  # 컨테이너 리브
            draw_cube(0.0, 0.58, (i - 1) * CELL * 0.26, CELL * 0.82, 0.5, 0.05, STEEL_TRIM)
        draw_cube(0.0, 0.9, 0.0, CELL * 0.84, 0.08, CELL * 0.84, STEEL_TRIM)
        draw_cube(0.0, 1.32, 0.0, CELL * 0.42, 0.76, CELL * 0.42, color)                   # 관제 타워
        draw_cube(0.0, 1.5, 0.0, CELL * 0.46, 0.24, CELL * 0.46, (0.2, 0.28, 0.36))        # 유리창
        glow = (0.6 + 0.4 * abs(math.sin(anim_t * 1.6))) if active else 0.35
        draw_cylinder(0.0, 1.72, 0.0, 0.22, 0.26,
                      (1.0 * glow, 0.92 * glow, 0.45 * glow), sides=12)                     # 코어 광원
        glPushMatrix()                                                                       # 궤도 링
        glTranslatef(0.0, 2.05, 0.0)
        glRotatef(anim_t * 40.0, 0.0, 1.0, 0.0)
        for a in range(6):
            glPushMatrix(); glRotatef(a * 60.0, 0.0, 1.0, 0.0)
            draw_cube(0.5, 0.0, 0.0, 0.2, 0.07, 0.1, (0.95, 0.85, 0.35))
            glPopMatrix()
        glPopMatrix()
        part_railing(0.0, 0.94, 0.0, CELL * 0.86, CELL * 0.86)
        part_ladder(CELL * 0.36, 0.94, -CELL * 0.24, 0.7)

    elif btype == "depot":
        # 판매소: 창고동 + 금속 지붕 + 하역 도크(도크 레벨러/셔터) + 매출 표시등
        draw_cube(0.0, 0.72, 0.0, CELL * 0.86, 1.24, CELL * 0.82, color)
        roof = (color[0] * 0.68, color[1] * 0.68, color[2] * 0.68)
        draw_cube(0.0, 1.38, 0.0, CELL * 0.94, 0.1, CELL * 0.9, roof)
        draw_pyramid(0.0, 1.43, 0.0, CELL * 0.92, 0.4, roof)
        draw_cube(0.0, 0.5, CELL * 0.42, CELL * 0.5, 0.7, 0.07, (0.28, 0.29, 0.32))        # 셔터
        for i in range(4):
            draw_cube(0.0, 0.28 + i * 0.16, CELL * 0.45, CELL * 0.5, 0.05, 0.03, STEEL_TRIM)
        draw_cube(CELL * 0.5, 0.22, 0.0, 0.3, 0.36, CELL * 0.5, STEEL_TRIM)                 # 하역 도크
        draw_cube(CELL * 0.5, 0.42, 0.0, 0.3, 0.05, CELL * 0.44, SAFETY)
        blink = active and int(anim_t * 2.0) % 2 == 0
        draw_cube(0.0, 1.5, CELL * 0.3, 0.13, 0.1, 0.1,
                  (0.3, 0.95, 0.45) if blink else (0.12, 0.35, 0.18))                       # 매출 표시등

    elif btype == "solar":
        # 태양광: 경사 브래킷 위 패널 + 셀 격자 + 후면 트러스 + 접속반
        draw_cube(0.0, 0.32, 0.0, 0.13, 0.64, 0.13, STEEL_TRIM)                          # 지주
        draw_cube(0.0, 0.62, 0.0, 0.4, 0.1, CELL * 0.5, STEEL_TRIM)                      # 브래킷
        draw_cube(0.0, 0.80, 0.0, CELL * 0.9, 0.055, CELL * 0.64, (0.12, 0.14, 0.2))     # 프레임
        for i in range(3):
            for j in range(2):
                draw_cube((i - 1) * CELL * 0.28, 0.835, (j - 0.5) * CELL * 0.30,
                          CELL * 0.24, 0.012, CELL * 0.26, color)                        # 셀
        draw_cube(0.0, 0.74, -CELL * 0.34, CELL * 0.86, 0.05, 0.06, STEEL_TRIM)          # 트러스
        draw_cube(CELL * 0.30, 0.30, -CELL * 0.30, 0.2, 0.24, 0.12, (0.28, 0.29, 0.32))  # 접속반

    elif btype in ("coal_gen", "oil_gen", "diesel_gen", "thermal_plant"):
        # 연료 발전기: 기관실 + 쌍둥이 굴뚝 + 연료 투입구 + 라디에이터 + 발전기 유닛
        tall = 1.7 if btype in ("coal_gen", "oil_gen") else 1.5
        draw_cube(0.0, tall / 2 + 0.1, -CELL * 0.08, CELL * 0.84, tall, CELL * 0.66, color)
        draw_cube(0.0, tall + 0.14, -CELL * 0.08, CELL * 0.88, 0.08, CELL * 0.7, STEEL_TRIM)
        h1 = 1.0 if btype == "coal_gen" else 1.2
        part_stack(-CELL * 0.26, tall + 0.18, -CELL * 0.26, 0.14, h1)
        part_stack(CELL * 0.26, tall + 0.18, -CELL * 0.26, 0.14, h1 * 0.8)
        part_smoke(-CELL * 0.26, tall + 0.18 + h1, -CELL * 0.26, anim_t, active, 0.75)
        glow = (0.55 + 0.45 * abs(math.sin(anim_t * 3.0))) if active else 0.15
        draw_cube(0.0, 0.42, CELL * 0.28, 0.4, 0.28, 0.1, (glow, glow * 0.4, 0.07))    # 연소창
        draw_cube(0.0, 0.16, CELL * 0.4, CELL * 0.5, 0.22, 0.18, STEEL_TRIM)           # 연료 투입구
        for i in range(4):                                                              # 라디에이터
            draw_cube(-CELL * 0.44, 0.55 + i * 0.2, -CELL * 0.08, 0.06, 0.14, CELL * 0.5, STEEL_TRIM)
        draw_cylinder(CELL * 0.36, 0.3, CELL * 0.3, 0.15, 0.5, accent, sides=10)        # 발전기

    elif btype == "oil_pump":
        # 펌프잭: 삼각 새머슨 기둥 + 시소 워킹빔 + 반대 위상 카운터웨이트 + 말머리/폴리시드 로드
        bob = math.sin(anim_t * 2.2) * 0.16 if active else 0.0
        draw_cube(0.0, 0.2, 0.0, CELL * 0.72, 0.34, CELL * 0.62, color)                # 스키드 베이스
        for dz in (-1, 1):                                                              # A형 기둥
            draw_cube(-0.06, 0.95, dz * 0.16, 0.1, 1.2, 0.1, STEEL_TRIM)
        draw_cube(0.0, 1.58, 0.0, 0.2, 0.14, 0.42, STEEL_TRIM)                          # 새들 베어링
        draw_cube(0.0, 1.66 + bob, 0.0, CELL * 0.94, 0.13, 0.13, (0.40, 0.41, 0.44))    # 워킹빔
        draw_cube(-CELL * 0.42, 1.52 - bob, 0.0, 0.28, 0.3, 0.24, (0.20, 0.20, 0.21))   # 카운터웨이트
        draw_cube(CELL * 0.42, 1.6 + bob, 0.0, 0.14, 0.3, 0.16, (0.34, 0.35, 0.38))     # 말머리
        draw_cylinder(CELL * 0.42, 0.35, 0.0, 0.05, 1.1 + bob, (0.6, 0.61, 0.64), sides=6)
        draw_cylinder(CELL * 0.42, 0.16, 0.0, 0.13, 0.24, STEEL_TRIM, sides=8)          # 웰헤드
        draw_cylinder(-CELL * 0.30, 0.3, CELL * 0.3, 0.13, 0.36, accent, sides=8)       # 구동 모터

    elif btype == "water_pump":
        # 취수 펌프: 펌프 하우징 + 볼류트 케이싱 + 구동 모터 + 토출 배관 + 압력계
        bob = math.sin(anim_t * 3.0) * 0.06 if active else 0.0
        draw_cube(0.0, 0.22, 0.0, CELL * 0.78, 0.4, CELL * 0.62, color)                 # 베이스
        draw_cylinder(0.0, 0.42, 0.0, 0.26, 0.34, (0.42, 0.52, 0.62), sides=12)         # 볼류트
        draw_cylinder(0.0, 0.42, 0.0, 0.3, 0.06, STEEL_TRIM, sides=12)
        draw_cylinder(-CELL * 0.32, 0.46, 0.0, 0.16, 0.42, accent, sides=10)            # 구동 모터
        part_pipe(0.0, 0.9, 0.0, 0, 1, 0, 0.55 + bob, 0.11, (0.45, 0.6, 0.78))          # 토출관
        draw_cylinder(0.0, 1.02 + bob, 0.0, 0.15, 0.1, (0.55, 0.72, 0.88), sides=10)
        part_pipe(0.0, 0.5, CELL * 0.36, 0, 0, 1, CELL * 0.24, 0.1, (0.45, 0.6, 0.78))  # 흡입관
        draw_cylinder(CELL * 0.26, 0.72, -CELL * 0.2, 0.07, 0.05, SAFETY, sides=8)      # 압력계

    elif btype == "water_treatment":
        # 물 처리기: 원형 침전조 + 회전 스크레이퍼 브리지 + 월류 웨어 + 약품 투입 탱크
        part_tank(0.0, 0.12, 0.0, CELL * 0.42, 0.72, color, sides=14, bands=1)
        bubble = (0.35 + 0.25 * abs(math.sin(anim_t * 3.5))) if active else 0.0
        draw_cylinder(0.0, 0.82, 0.0, CELL * 0.37, 0.05,
                      (0.72 + 0.2 * bubble, 0.90, 1.0), sides=14)                        # 수면
        glPushMatrix()                                                                    # 스크레이퍼
        glTranslatef(0.0, 0.92, 0.0)
        glRotatef(anim_t * 26.0 if active else 0.0, 0.0, 1.0, 0.0)
        draw_cube(0.0, 0.0, 0.0, CELL * 0.84, 0.07, 0.11, STEEL_TRIM)
        draw_cube(CELL * 0.3, -0.08, 0.0, 0.1, 0.12, 0.1, STEEL_TRIM)
        glPopMatrix()
        draw_cylinder(0.0, 0.9, 0.0, 0.1, 0.22, STEEL_TRIM, sides=8)                     # 중앙 구동
        part_tank(CELL * 0.4, 0.12, CELL * 0.36, 0.11, 0.5, accent, sides=8, bands=1)    # 약품 탱크
        part_railing(0.0, 0.86, 0.0, CELL * 0.9, CELL * 0.9)

    elif btype == "firebox":
        # 파이어박스: 연소실 + 여닫는 화구 도어 + 급수관 + 재받이 + 짧은 굴뚝
        draw_cube(0.0, 0.5, 0.0, CELL * 0.82, 0.86, CELL * 0.72, color)
        draw_cube(0.0, 0.95, 0.0, CELL * 0.86, 0.07, CELL * 0.76, STEEL_TRIM)
        glow = (0.6 + 0.4 * abs(math.sin(anim_t * 3.0))) if active else 0.2
        draw_cylinder(0.0, 0.5, CELL * 0.37, 0.19, 0.06, STEEL_TRIM, sides=10)           # 화구 테두리
        draw_cube(0.0, 0.5, CELL * 0.41, 0.3, 0.26, 0.06, (glow, glow * 0.42, 0.08))     # 화구 불빛
        draw_cube(0.0, 0.16, CELL * 0.38, CELL * 0.46, 0.16, 0.14, (0.28, 0.27, 0.26))   # 재받이
        part_stack(-CELL * 0.28, 1.0, -CELL * 0.22, 0.12, 0.62)
        part_smoke(-CELL * 0.28, 1.62, -CELL * 0.22, anim_t, active, 0.55)
        part_pipe(CELL * 0.32, 0.72, 0.0, 1, 0, 0, CELL * 0.3, 0.08, (0.42, 0.58, 0.76)) # 급수관

    elif btype == "boiler":
        # 보일러: 가로로 눕힌 원통 드럼 + 안장 받침 + 증기 헤더 + 안전밸브 + 압력계
        glPushMatrix()
        glTranslatef(0.0, 0.72, 0.0)
        glRotatef(90.0, 0.0, 0.0, 1.0)
        draw_cylinder(0.0, -CELL * 0.4, 0.0, 0.36, CELL * 0.8, color, sides=14)          # 드럼
        glPopMatrix()
        for dx in (-1, 1):                                                                # 안장 받침
            draw_cube(dx * CELL * 0.28, 0.28, 0.0, 0.16, 0.4, CELL * 0.6, STEEL_TRIM)
        draw_cylinder(-CELL * 0.42, 0.72, 0.0, 0.38, 0.05, STEEL_TRIM, sides=14)         # 앞쪽 경판
        draw_cylinder(CELL * 0.40, 0.72, 0.0, 0.38, 0.05, STEEL_TRIM, sides=14)
        part_pipe(0.0, 1.1, 0.0, 0, 1, 0, 0.4, 0.09, (0.6, 0.62, 0.66))                  # 증기 헤더
        draw_cube(0.0, 1.52, 0.0, CELL * 0.5, 0.09, 0.11, (0.6, 0.62, 0.66))
        pulse = (0.5 + 0.5 * abs(math.sin(anim_t * 4.0))) if active else 0.0
        draw_cylinder(CELL * 0.22, 1.14, 0.0, 0.055, 0.2, STEEL_TRIM, sides=6)           # 안전밸브
        draw_cylinder(-CELL * 0.22, 1.0, CELL * 0.2, 0.09, 0.06,
                      (0.85, 0.25 + 0.5 * pulse, 0.2), sides=10)                          # 압력계
        if active:
            p = 0.1 + 0.05 * abs(math.sin(anim_t * 5.0))
            draw_cube(CELL * 0.22, 1.42, 0.0, p, p, p, (0.92, 0.92, 0.95))

    elif btype == "turbine":
        # 증기 터빈: 케이싱 + 회전 로터 + 축으로 연결된 발전기 + 증기 입출 배관
        draw_cube(0.0, 0.28, 0.0, CELL * 0.88, 0.4, CELL * 0.6, color)                   # 스키드
        draw_cylinder(0.0, 0.48, 0.0, 0.34, 0.62, (0.46, 0.48, 0.52), sides=14)          # 케이싱
        draw_cylinder(0.0, 1.1, 0.0, 0.36, 0.06, STEEL_TRIM, sides=14)
        spin = (anim_t * 220.0) if active else 0.0
        glPushMatrix()
        glTranslatef(0.0, 1.2, 0.0)
        glRotatef(spin, 0.0, 1.0, 0.0)
        for a in range(4):
            glPushMatrix(); glRotatef(a * 90.0, 0.0, 1.0, 0.0)
            draw_cube(0.22, 0.0, 0.0, 0.4, 0.05, 0.1, (0.78, 0.80, 0.84))
            glPopMatrix()
        glPopMatrix()
        draw_cylinder(CELL * 0.34, 0.5, 0.0, 0.17, 0.44, accent, sides=10)               # 발전기
        part_pipe(-CELL * 0.36, 0.7, 0.0, -1, 0, 0, CELL * 0.28, 0.09, (0.66, 0.68, 0.72))
        part_panel(0.0, 0.5, CELL * 0.36, color, blink=active and int(anim_t * 4) % 2 == 0, w=0.28)

    elif btype == "refinery":
        # 정유소: 높이가 다른 증류탑 2기 + 크로스오버 배관 + 점검 난간 + 사다리
        part_tank(-CELL * 0.26, 0.12, 0.0, 0.27, 1.45, color, sides=12, bands=3)
        part_tank(CELL * 0.30, 0.12, 0.0, 0.21, 1.05,
                  (color[0] * 0.86, color[1] * 0.86, color[2] * 0.86), sides=12, bands=2)
        draw_pyramid(-CELL * 0.26, 1.57, 0.0, 0.44, 0.18, STEEL_TRIM)
        part_pipe(0.0, 1.25, 0.0, 1, 0, 0, CELL * 0.56, 0.075, (0.52, 0.54, 0.57))
        part_pipe(0.0, 0.6, 0.0, 1, 0, 0, CELL * 0.56, 0.065, (0.52, 0.54, 0.57))
        part_railing(-CELL * 0.26, 1.5, 0.0, 0.66, 0.66)
        part_ladder(-CELL * 0.26, 0.12, CELL * 0.3, 1.4)

    elif btype == "chem_plant":
        # 플라스틱 생산 시설: 중합 반응조 2기 + 펠릿 압출기 + 냉각 컨베이어 배출부
        part_tank(0.0, 0.12, -CELL * 0.28, 0.25, 1.2, color, sides=12, bands=2)
        part_tank(0.0, 0.12, CELL * 0.28, 0.25, 1.45,
                  (color[0] * 0.86, color[1] * 0.86, color[2] * 0.86), sides=12, bands=3)
        part_pipe(0.0, 1.0, 0.0, 0, 0, 1, CELL * 0.56, 0.07, (0.52, 0.54, 0.57))
        draw_cube(CELL * 0.34, 0.4, 0.0, 0.3, 0.5, CELL * 0.5, STEEL_TRIM)                # 압출기
        if active:                                                                         # 펠릿 배출
            for i in range(3):
                p = (anim_t * 1.6 + i / 3.0) % 1.0
                draw_cube(CELL * 0.34 + 0.18, 0.5, (p - 0.5) * CELL * 0.5,
                          0.07, 0.07, 0.07, accent)
        part_railing(0.0, 1.32, CELL * 0.28, 0.6, 0.6)

    elif btype == "molder":
        # 사출 성형기: 원료 호퍼 + 가열 배럴 + 형체 유닛(주기적으로 닫힘) + 배출 슈트
        draw_cube(0.0, 0.36, 0.0, CELL * 0.88, 0.52, CELL * 0.58, color)                  # 베드
        draw_pyramid(-CELL * 0.26, 0.68, 0.0, 0.46, 0.46,
                     (min(color[0] * 1.15, 1.0), min(color[1] * 1.15, 1.0), min(color[2] * 1.15, 1.0)))
        draw_cylinder(-CELL * 0.26, 1.14, 0.0, 0.1, 0.14, STEEL_TRIM, sides=8)
        glPushMatrix()                                                                     # 가열 배럴
        glTranslatef(0.0, 0.72, 0.0); glRotatef(90.0, 0.0, 0.0, 1.0)
        draw_cylinder(0.0, -CELL * 0.3, 0.0, 0.13, CELL * 0.6, (0.55, 0.45, 0.38), sides=10)
        glPopMatrix()
        for i in range(3):                                                                 # 히터 밴드
            draw_cylinder(-0.1 + i * 0.2, 0.72, 0.0, 0.15, 0.05, SAFETY, sides=10)
        clamp = (math.sin(anim_t * 3.0) * 0.5 + 0.5) if active else 0.0
        draw_cube(CELL * 0.3 - clamp * 0.08, 0.7, 0.0, 0.2, 0.5, CELL * 0.5, STEEL_TRIM)   # 형체
        draw_cube(CELL * 0.44 + clamp * 0.05, 0.7, 0.0, 0.14, 0.44, CELL * 0.44, (0.42, 0.43, 0.46))
        draw_cube(CELL * 0.34, 0.18, CELL * 0.34, 0.24, 0.16, 0.2, STEEL_TRIM)             # 배출 슈트

    elif btype == "oil_classifier":
        # 원유 분류기: 트레이 증류탑 + 높이별 측류 인출관 + 상단 응축기 + 점검 난간
        part_tank(0.0, 0.12, 0.0, 0.3, 1.75, color, sides=14, bands=5)
        draw_pyramid(0.0, 1.87, 0.0, 0.48, 0.2, STEEL_TRIM)
        branch = (0.55, 0.56, 0.6)
        for y in (0.55, 1.0, 1.45):                                                        # 측류 인출관
            part_pipe(CELL * 0.32, y, 0.0, 1, 0, 0, CELL * 0.24, 0.06, branch)
            draw_cube(CELL * 0.34, y, 0.0, 0.1, 0.1, 0.1, accent)
        draw_cylinder(-CELL * 0.36, 1.35, 0.0, 0.14, 0.4, (0.5, 0.55, 0.6), sides=10)      # 응축기
        part_pipe(0.0, 1.95, 0.0, -1, 0, 0, CELL * 0.36, 0.06, branch)
        part_railing(0.0, 1.15, 0.0, 0.82, 0.82)
        part_ladder(0.0, 0.12, -CELL * 0.34, 1.7)

    elif btype == "diesel_refiner":
        # 디젤 정제기: 수소첨가 반응탑 + 상단 공랭식 응축기 + 원료 예열기 + 제품 드럼
        part_tank(0.0, 0.12, 0.0, 0.29, 1.15, color, sides=12, bands=3)
        draw_pyramid(0.0, 1.27, 0.0, 0.44, 0.16, STEEL_TRIM)
        draw_cylinder(0.0, 1.43, 0.0, 0.2, 0.26,
                      (color[0] * 0.72, color[1] * 0.72, color[2] * 0.72), sides=12)     # 응축기
        glPushMatrix()                                                                    # 공랭 팬
        glTranslatef(0.0, 1.74, 0.0)
        glRotatef(anim_t * 240.0 if active else 0.0, 0.0, 1.0, 0.0)
        for a in range(3):
            glPushMatrix(); glRotatef(a * 120.0, 0.0, 1.0, 0.0)
            draw_cube(0.14, 0.0, 0.0, 0.24, 0.035, 0.09, (0.84, 0.86, 0.89))
            glPopMatrix()
        glPopMatrix()
        draw_cylinder(-CELL * 0.36, 0.25, 0.0, 0.13, 0.5, (0.5, 0.44, 0.36), sides=10)   # 예열기
        part_pipe(0.0, 0.85, CELL * 0.32, 0, 0, 1, CELL * 0.22, 0.07, (0.55, 0.5, 0.42))
        part_tank(CELL * 0.36, 0.12, CELL * 0.3, 0.13, 0.42, accent, sides=10, bands=1)  # 제품 드럼
        part_ladder(0.0, 0.12, -CELL * 0.34, 1.1)

    elif btype == "filter":
        # 필터: 카트리지 필터 하우징 + 클램프 밴드 + 차압계 + 드레인 밸브
        draw_cylinder(0.0, 0.14, 0.0, 0.3, 0.72, color, sides=12)                        # 하우징
        draw_cylinder(0.0, 0.86, 0.0, 0.33, 0.07, STEEL_TRIM, sides=12)                  # 클램프 밴드
        draw_cylinder(0.0, 0.93, 0.0, 0.26, 0.3,
                      (color[0] * 0.72, color[1] * 0.72, color[2] * 0.72), sides=12)     # 상부 보닛
        draw_pyramid(0.0, 1.23, 0.0, 0.4, 0.14, STEEL_TRIM)
        for i in range(3):                                                                # 카트리지 주름
            draw_cylinder(0.0, 0.3 + i * 0.18, 0.0, 0.32, 0.04, (0.82, 0.84, 0.86), sides=12)
        part_pipe(-CELL * 0.34, 0.5, 0.0, -1, 0, 0, CELL * 0.24, 0.08, (0.55, 0.57, 0.6))
        part_pipe(CELL * 0.34, 0.5, 0.0, 1, 0, 0, CELL * 0.24, 0.08, (0.55, 0.57, 0.6))
        clog = (0.5 + 0.5 * abs(math.sin(anim_t * 2.0))) if active else 0.2
        draw_cylinder(CELL * 0.2, 1.06, CELL * 0.16, 0.07, 0.05,
                      (0.9, 0.35 + 0.5 * clog, 0.18), sides=8)                            # 차압계
        draw_cylinder(0.0, 0.1, CELL * 0.28, 0.05, 0.12, STEEL_TRIM, sides=6)            # 드레인

    elif btype == "gas_extractor":
        # 가스 추출기: 웰헤드 크리스마스트리 밸브 + 분리기 드럼 + 플레어 스택
        draw_cube(0.0, 0.24, 0.0, CELL * 0.72, 0.36, CELL * 0.6, color)
        draw_cylinder(0.0, 0.42, -CELL * 0.14, 0.11, 0.5, STEEL_TRIM, sides=8)
        for i, y in enumerate((0.58, 0.76)):
            draw_cube(0.0, y, -CELL * 0.14, 0.36, 0.07, 0.09, (0.62, 0.63, 0.66))
            draw_cylinder(0.18, y, -CELL * 0.14, 0.05, 0.07, SAFETY, sides=6)
        draw_cube(0.0, 0.98, -CELL * 0.14, 0.16, 0.14, 0.16, STEEL_TRIM)
        part_tank(CELL * 0.32, 0.12, CELL * 0.28, 0.16, 0.6, color, sides=10, bands=1)
        part_stack(-CELL * 0.34, 0.42, CELL * 0.3, 0.08, 0.9, banded=False)
        if active:
            f = 0.10 + 0.05 * abs(math.sin(anim_t * 7.0))
            draw_cube(-CELL * 0.34, 1.36, CELL * 0.3, f, f * 1.6, f, (1.0, 0.55, 0.15))

    elif btype == "condenser":
        # 콘덴서: 쉘앤튜브 열교환기 + 냉각수 헤더 + 응축액 받이 드럼
        glPushMatrix()
        glTranslatef(0.0, 0.72, 0.0); glRotatef(90.0, 0.0, 0.0, 1.0)
        draw_cylinder(0.0, -CELL * 0.36, 0.0, 0.28, CELL * 0.72, color, sides=14)
        glPopMatrix()
        for dx in (-1, 1):
            draw_cylinder(dx * CELL * 0.38, 0.72, 0.0, 0.31, 0.06, STEEL_TRIM, sides=14)
            draw_cube(dx * CELL * 0.46, 0.72, 0.0, 0.1, 0.34, 0.34, (0.42, 0.5, 0.58))
        for dx in (-1, 0, 1):
            draw_cube(dx * CELL * 0.24, 0.34, 0.0, 0.14, 0.42, CELL * 0.5, STEEL_TRIM)
        part_pipe(0.0, 1.05, 0.0, 0, 0, 1, CELL * 0.36, 0.08, (0.45, 0.6, 0.75))
        part_tank(0.0, 0.12, CELL * 0.36, 0.14, 0.4, color, sides=10, bands=1)
        pulse = (0.5 + 0.5 * abs(math.sin(anim_t * 3.0))) if active else 0.2
        draw_cylinder(CELL * 0.3, 0.98, 0.0, 0.06, 0.05, (0.4, 0.7 * pulse + 0.2, 0.9), sides=8)

    elif btype == "gas_refiner":
        # 가스 정제기: 흡수탑 + 재생탑 2기 + 상호 순환 배관 + 잔류물 배출구
        part_tank(-CELL * 0.26, 0.12, 0.0, 0.22, 1.35, color, sides=12, bands=3)
        part_tank(CELL * 0.28, 0.12, 0.0, 0.18, 0.95,
                  (color[0] * 0.85, color[1] * 0.85, color[2] * 0.85), sides=12, bands=2)
        draw_pyramid(-CELL * 0.26, 1.47, 0.0, 0.36, 0.16, STEEL_TRIM)
        part_pipe(0.0, 1.15, 0.0, 1, 0, 0, CELL * 0.54, 0.065, (0.52, 0.54, 0.57))
        part_pipe(0.0, 0.5, 0.0, 1, 0, 0, CELL * 0.54, 0.06, (0.52, 0.54, 0.57))
        draw_cube(0.0, 0.2, CELL * 0.4, CELL * 0.36, 0.18, 0.14, STEEL_TRIM)
        pulse = (0.5 + 0.5 * abs(math.sin(anim_t * 4.0))) if active else 0.15
        draw_cylinder(-CELL * 0.26, 1.55, 0.0, 0.05, 0.12,
                      (0.5, 0.9 * pulse + 0.15, 0.75), sides=6)
        part_ladder(-CELL * 0.26, 0.12, -CELL * 0.28, 1.3)

    elif btype == "gas_turbine":
        # 가스 터빈: 흡기 플리넘 + 연소기 케이싱 + 축류 로터 + 배기 디퓨저
        draw_cube(0.0, 0.24, 0.0, CELL * 0.86, 0.36, CELL * 0.66, color)                    # 스키드
        draw_cylinder(0.0, 0.42, 0.0, 0.3, 0.62, (0.46, 0.5, 0.48), sides=14)               # 연소기
        draw_cylinder(0.0, 0.42, 0.0, 0.33, 0.05, STEEL_TRIM, sides=14)
        draw_cylinder(0.0, 0.99, 0.0, 0.33, 0.05, STEEL_TRIM, sides=14)
        for a in range(6):                                                                   # 연소기 캔
            glPushMatrix(); glRotatef(a * 60.0, 0.0, 1.0, 0.0)
            draw_cylinder(0.3, 0.5, 0.0, 0.055, 0.42, (0.38, 0.42, 0.4), sides=6)
            glPopMatrix()
        draw_cube(-CELL * 0.42, 0.5, 0.0, 0.16, 0.44, CELL * 0.44, STEEL_TRIM)              # 흡기 플리넘
        draw_cylinder(CELL * 0.4, 0.62, 0.0, 0.16, 0.3, (0.3, 0.29, 0.28), sides=10)        # 배기 디퓨저
        spin = (anim_t * 260.0) if active else 0.0
        blade = (min(color[0] * 1.4, 1.0), min(color[1] * 1.4, 1.0), min(color[2] * 1.4, 1.0))
        draw_cylinder(0.0, 1.04, 0.0, 0.14, 0.3, (0.4, 0.4, 0.42))
        glPushMatrix()
        glTranslatef(0.0, 1.35, 0.0)
        glRotatef(spin, 0.0, 1.0, 0.0)
        draw_cube(0.0, 0.0, 0.0, 0.35, 0.05, 0.06, blade)
        draw_cube(0.0, 0.0, 0.0, 0.06, 0.05, 0.35, blade)
        glPopMatrix()

    elif btype == "gas_input_block":
        # 가스 인풋: 매니폴드 + 유량계 + 핸드휠 밸브 + 터빈으로 뻗는 공급관
        g = (0.4 + 0.6 * abs(math.sin(anim_t * 5.0))) if active else 0.15
        draw_cube(0.0, 0.22, 0.0, CELL * 0.66, 0.34, CELL * 0.6, color)
        draw_cylinder(0.0, 0.38, 0.0, 0.15, 0.5, (0.15, 0.55 * g + 0.25, 0.35 * g + 0.15), sides=10)
        draw_cylinder(0.0, 0.88, 0.0, 0.17, 0.06, STEEL_TRIM, sides=10)                  # 플랜지
        glPushMatrix()                                                                    # 핸드휠
        glTranslatef(0.0, 0.99, 0.0)
        glRotatef(anim_t * 55.0 if active else 0.0, 0.0, 1.0, 0.0)
        draw_cube(0.0, 0.0, 0.0, 0.34, 0.045, 0.05, (0.78, 0.78, 0.8))
        draw_cube(0.0, 0.0, 0.0, 0.05, 0.045, 0.34, (0.78, 0.78, 0.8))
        glPopMatrix()
        draw_cylinder(CELL * 0.26, 0.55, 0.0, 0.07, 0.05, SAFETY, sides=8)               # 유량계
        part_pipe(0.0, 0.5, CELL * 0.34, 0, 0, 1, CELL * 0.28, 0.08, (0.35, 0.6, 0.5))

    elif btype == "turbine_controller_block":
        # 터빈 컨트롤러: 제어반 캐비닛 + 계기 패널 + 케이블 트레이 + 상단 경광등
        blink = (int(anim_t * 2.0) % 2 == 0) if active else True
        draw_cube(0.0, 0.5, 0.0, CELL * 0.7, 0.88, CELL * 0.5, color)
        draw_cube(0.0, 0.96, 0.0, CELL * 0.74, 0.07, CELL * 0.54, STEEL_TRIM)
        part_panel(0.0, 0.62, CELL * 0.27, color, blink=active and blink, w=0.42)
        for i in range(3):                                                                # 환기 슬릿
            draw_cube(0.0, 0.3 + i * 0.07, -CELL * 0.26, CELL * 0.44, 0.03, 0.03, STEEL_TRIM)
        draw_cube(0.0, 1.06, 0.0, 0.12, 0.14, 0.12, STEEL_TRIM)
        draw_cylinder(0.0, 1.13, 0.0, 0.08, 0.1,
                      (0.2, 1.0, 0.3) if blink else (0.1, 0.35, 0.12), sides=8)           # 경광등
        part_pipe(-CELL * 0.36, 0.2, 0.0, -1, 0, 0, CELL * 0.24, 0.05, (0.25, 0.26, 0.3))

    elif btype == "turbine_crankshaft_block":
        # 터빈 크랭크축: 베어링 하우징 2기를 관통하는 회전축 + 편심 크랭크 웨이트 + 커플링
        spin = (anim_t * 300.0) if active else 0.0
        draw_cube(0.0, 0.24, 0.0, CELL * 0.8, 0.36, CELL * 0.52, color)                   # 베드
        for dx in (-1, 1):                                                                 # 베어링 하우징
            draw_cube(dx * CELL * 0.3, 0.58, 0.0, 0.24, 0.44, CELL * 0.34, STEEL_TRIM)
        glPushMatrix()
        glTranslatef(0.0, 0.62, 0.0)
        glRotatef(90.0, 0.0, 0.0, 1.0)
        glRotatef(spin, 0.0, 1.0, 0.0)
        draw_cylinder(0.0, -CELL * 0.46, 0.0, 0.075, CELL * 0.92, (0.72, 0.73, 0.76), sides=10)
        draw_cube(0.0, 0.0, 0.16, 0.24, 0.24, 0.1, accent)                                 # 크랭크 웨이트
        glPopMatrix()
        draw_cylinder(CELL * 0.44, 0.62, 0.0, 0.12, 0.08, (0.55, 0.56, 0.6), sides=10)     # 커플링
        part_panel(0.0, 0.4, CELL * 0.32, color, blink=active and int(anim_t * 5) % 2 == 0, w=0.26)

    elif btype == "gas_cylinder_block":
        # 가스 실린더: 고압 저장 실린더 2본 + 공용 매니폴드 + 안전밸브 + 경고 밴드
        for dz in (-1, 1):
            part_tank(0.0, 0.12, dz * CELL * 0.2, 0.19, 1.3, color, sides=12, bands=3)
            draw_pyramid(0.0, 1.42, dz * CELL * 0.2, 0.3, 0.16, STEEL_TRIM)
            draw_cylinder(0.0, 1.56, dz * CELL * 0.2, 0.05, 0.14, STEEL_TRIM, sides=6)
        draw_cube(0.0, 1.66, 0.0, 0.1, 0.07, CELL * 0.5, (0.58, 0.6, 0.64))                # 매니폴드
        draw_cube(0.0, 0.5, 0.0, 0.09, 0.09, CELL * 0.42, STEEL_TRIM)                      # 고정 밴드
        draw_cube(0.0, 0.95, 0.0, 0.09, 0.09, CELL * 0.42, STEEL_TRIM)
        part_pipe(CELL * 0.3, 1.66, 0.0, 1, 0, 0, CELL * 0.22, 0.06, (0.58, 0.6, 0.64))

    elif btype == "exhaust_pump_block":
        # 매연 배기 펌프: 흡입 후드 + 송풍기 케이싱 + 그을린 배기관 + 매연 토출
        draw_cube(0.0, 0.24, 0.0, CELL * 0.66, 0.38, CELL * 0.6, (0.26, 0.25, 0.23))
        draw_cylinder(0.0, 0.44, 0.0, 0.24, 0.3, (0.3, 0.29, 0.27), sides=12)              # 송풍 케이싱
        glPushMatrix()                                                                      # 임펠러
        glTranslatef(0.0, 0.59, 0.0)
        glRotatef(anim_t * 340.0 if active else 0.0, 0.0, 1.0, 0.0)
        for a in range(3):
            glPushMatrix(); glRotatef(a * 120.0, 0.0, 1.0, 0.0)
            draw_cube(0.12, 0.0, 0.0, 0.2, 0.04, 0.07, (0.5, 0.49, 0.47))
            glPopMatrix()
        glPopMatrix()
        draw_cylinder(0.0, 0.74, 0.0, 0.17, 0.75, color, sides=10)                          # 배기관
        draw_cylinder(0.0, 1.49, 0.0, 0.22, 0.1, (0.10, 0.09, 0.08), sides=10)
        part_smoke(0.0, 1.6, 0.0, anim_t, active, 0.6)
        part_pipe(-CELL * 0.34, 0.4, 0.0, -1, 0, 0, CELL * 0.24, 0.08, (0.28, 0.27, 0.25))

    elif btype == "intake_pump_block":
        # 공기 흡기펌프: 벨마우스 흡입구 + 회전 축류팬 + 필터 카트리지 + 토출관
        draw_cube(0.0, 0.22, 0.0, CELL * 0.66, 0.34, CELL * 0.6, color)
        draw_cylinder(0.0, 0.38, 0.0, 0.26, 0.34, (0.62, 0.66, 0.7), sides=14)
        draw_cylinder(0.0, 0.72, 0.0, 0.3, 0.06, STEEL_TRIM, sides=14)
        glPushMatrix()
        glTranslatef(0.0, 0.56, 0.0)
        glRotatef(anim_t * 340.0 if active else 0.0, 0.0, 1.0, 0.0)
        for a in range(5):
            glPushMatrix(); glRotatef(a * 72.0, 0.0, 1.0, 0.0)
            draw_cube(0.14, 0.0, 0.0, 0.24, 0.035, 0.1, (0.88, 0.9, 0.93))
            glPopMatrix()
        glPopMatrix()
        for i in range(3):
            draw_cylinder(0.0, 0.8 + i * 0.07, 0.0, 0.22 - i * 0.03, 0.05,
                          (0.78, 0.79, 0.8), sides=12)
        part_pipe(0.0, 0.4, -CELL * 0.36, 0, 0, -1, CELL * 0.24, 0.09, (0.6, 0.64, 0.7))

    elif btype == "scrubber":
        # 정화기: 습식 스크러버 - 충전탑 + 세정수 순환 펌프 + 데미스터 + 정화 배출구
        part_tank(0.0, 0.12, 0.0, CELL * 0.34, 1.2, color, sides=14, bands=3)
        draw_pyramid(0.0, 1.32, 0.0, CELL * 0.5, 0.2, STEEL_TRIM)
        draw_cylinder(0.0, 1.5, 0.0, 0.13, 0.4, (0.72, 0.78, 0.82), sides=10)
        spray = (0.5 + 0.5 * abs(math.sin(anim_t * 5.0))) if active else 0.15
        draw_cylinder(0.0, 1.0, 0.0, CELL * 0.28, 0.06,
                      (0.6 + 0.3 * spray, 0.85, 0.95), sides=14)
        part_pipe(-CELL * 0.34, 0.7, 0.0, -1, 0, 0, CELL * 0.24, 0.07, (0.5, 0.72, 0.8))
        draw_cylinder(-CELL * 0.42, 0.18, CELL * 0.24, 0.12, 0.32, accent, sides=10)
        part_pipe(0.0, 0.35, CELL * 0.36, 0, 0, 1, CELL * 0.22, 0.09, (0.45, 0.5, 0.55))
        if active:
            p = 0.1 + 0.05 * abs(math.sin(anim_t * 2.0))
            draw_cube(0.0, 1.98, 0.0, p, p, p, (0.9, 0.95, 0.97))
        part_ladder(CELL * 0.4, 0.12, 0.0, 1.15)

    elif btype == "research":
        # 연구소: 유리 파사드 연구동 + 파라볼라 안테나 + 데이터 서버랙 + 상태 표시등
        draw_cube(0.0, 0.55, 0.0, CELL * 0.86, 0.9, CELL * 0.72, color)
        for i in range(2):
            draw_cube(0.0, 0.4 + i * 0.36, CELL * 0.38, CELL * 0.7, 0.22, 0.05,
                      (0.24, 0.34, 0.44))
        draw_cube(0.0, 1.03, 0.0, CELL * 0.9, 0.07, CELL * 0.76, STEEL_TRIM)
        draw_cube(-CELL * 0.26, 1.3, 0.0, 0.3, 0.44, CELL * 0.4, STEEL_TRIM)
        blink = active and int(anim_t * 4.0) % 2 == 0
        for i in range(3):
            draw_cube(-CELL * 0.26, 1.2 + i * 0.12, CELL * 0.2, 0.2, 0.04, 0.04,
                      (0.3, 0.95, 0.5) if blink else (0.12, 0.3, 0.18))
        glPushMatrix()
        glTranslatef(CELL * 0.28, 1.35, 0.0)
        glRotatef(anim_t * 30.0 if active else 0.0, 0.0, 1.0, 0.0)
        glRotatef(-35.0, 0.0, 0.0, 1.0)
        draw_cylinder(0.0, 0.0, 0.0, 0.26, 0.07, (0.86, 0.88, 0.9), sides=12)
        draw_cylinder(0.0, 0.07, 0.0, 0.04, 0.16, STEEL_TRIM, sides=6)
        glPopMatrix()

    elif btype == "silicon_refiner":
        # 실리콘 정제기: 초크랄스키 인상로 - 도가니 챔버 + 인상축 + 성장하는 잉곳
        draw_cube(0.0, 0.3, 0.0, CELL * 0.82, 0.44, CELL * 0.7, color)
        draw_cylinder(0.0, 0.52, 0.0, 0.3, 0.55, (0.5, 0.52, 0.56), sides=14)
        draw_cylinder(0.0, 1.07, 0.0, 0.33, 0.06, STEEL_TRIM, sides=14)
        glow = (0.55 + 0.45 * abs(math.sin(anim_t * 2.4))) if active else 0.15
        draw_cube(0.0, 0.66, CELL * 0.3, 0.2, 0.16, 0.06, (glow, glow * 0.5, 0.1))
        pull = (math.sin(anim_t * 0.9) * 0.5 + 0.5) if active else 0.4
        draw_cylinder(0.0, 1.13, 0.0, 0.045, 0.5, STEEL_TRIM, sides=6)
        draw_cylinder(0.0, 1.13 - pull * 0.22, 0.0, 0.11, 0.3 + pull * 0.2,
                      (0.74, 0.78, 0.84), sides=10)
        part_panel(0.0, 0.42, -CELL * 0.4, color, blink=active and int(anim_t * 3) % 2 == 0, w=0.3)

    elif btype == "alloy_furnace":
        # 합금로: 전기 아크로 - 경동 가능한 노체 + 3상 전극 + 배기 후드 + 출강구
        draw_cylinder(0.0, 0.12, 0.0, CELL * 0.38, 0.62, color, sides=14)
        draw_cylinder(0.0, 0.74, 0.0, CELL * 0.4, 0.08, STEEL_TRIM, sides=14)
        arc = (0.6 + 0.4 * abs(math.sin(anim_t * 9.0))) if active else 0.12
        for a in range(3):
            ax = math.cos(a * 2.094) * 0.16
            az = math.sin(a * 2.094) * 0.16
            draw_cylinder(ax, 0.82, az, 0.055, 0.62, (0.22, 0.21, 0.2), sides=6)
            draw_cube(ax, 0.78, az, 0.1, 0.08, 0.1, (arc, arc * 0.75, arc * 0.4))
        draw_cube(0.0, 1.5, 0.0, CELL * 0.6, 0.12, CELL * 0.6, STEEL_TRIM)
        part_stack(CELL * 0.34, 1.56, -CELL * 0.24, 0.11, 0.7)
        part_smoke(CELL * 0.34, 2.26, -CELL * 0.24, anim_t, active, 0.6)
        draw_cube(0.0, 0.3, CELL * 0.42, 0.24, 0.16, 0.14,
                  (arc, arc * 0.4, 0.06))
        part_ladder(-CELL * 0.42, 0.12, 0.0, 0.7)

    elif btype == "circuit_assembler":
        # 회로 조립기: 클린룸 인클로저 + SMT 픽앤플레이스 갠트리 + 기판 컨베이어
        draw_cube(0.0, 0.28, 0.0, CELL * 0.88, 0.4, CELL * 0.66, color)
        draw_cube(0.0, 0.5, 0.0, CELL * 0.8, 0.06, CELL * 0.5, (0.2, 0.22, 0.24))
        for dz in (-1, 1):
            draw_cube(0.0, 0.86, dz * CELL * 0.3, 0.09, 0.66, 0.09, STEEL_TRIM)
        draw_cube(0.0, 1.2, 0.0, 0.12, 0.1, CELL * 0.66, STEEL_TRIM)
        gx = math.sin(anim_t * 2.2) * CELL * 0.28 if active else 0.0
        draw_cube(gx, 1.08, 0.0, 0.18, 0.2, 0.18, accent)
        draw_cube(gx, 0.62, 0.0, 0.1, 0.14, 0.1, (0.7, 0.72, 0.75))
        for i in range(3):
            draw_cube((i - 1) * CELL * 0.22, 0.55, 0.0, 0.2, 0.03, 0.16, (0.12, 0.5, 0.28))
        draw_cube(0.0, 0.9, -CELL * 0.36, CELL * 0.7, 0.5, 0.05, (0.62, 0.72, 0.78))
        part_panel(CELL * 0.34, 0.5, CELL * 0.36, color,
                   blink=active and int(anim_t * 4) % 2 == 0, w=0.26)

    elif btype == "assembly_plant":
        # 조립 공장: 톱니 지붕 공장동 + 로봇 암 + 조립 라인 + 출하 도크
        draw_cube(0.0, 0.6, 0.0, CELL * 0.92, 1.0, CELL * 0.8, color)
        for i in range(3):
            draw_pyramid((i - 1) * CELL * 0.3, 1.1, 0.0, CELL * 0.3, 0.26,
                         (color[0] * 0.72, color[1] * 0.72, color[2] * 0.72))
        draw_cube(0.0, 1.12, 0.0, CELL * 0.96, 0.06, CELL * 0.84, STEEL_TRIM)
        glPushMatrix()
        glTranslatef(0.0, 1.2, 0.0)
        glRotatef(math.sin(anim_t * 1.5) * 45.0 if active else 0.0, 0.0, 1.0, 0.0)
        draw_cylinder(0.0, 0.0, 0.0, 0.1, 0.28, STEEL_TRIM, sides=8)
        draw_cube(0.2, 0.3, 0.0, 0.44, 0.08, 0.1, accent)
        draw_cube(0.4, 0.2, 0.0, 0.08, 0.24, 0.08, accent)
        glPopMatrix()
        draw_cube(0.0, 0.42, CELL * 0.44, CELL * 0.5, 0.6, 0.06, (0.26, 0.27, 0.3))
        draw_cube(CELL * 0.5, 0.2, 0.0, 0.24, 0.32, CELL * 0.44, STEEL_TRIM)
        draw_cube(CELL * 0.5, 0.38, 0.0, 0.24, 0.04, CELL * 0.4, SAFETY)

    elif btype == "battery_plant":
        # 배터리 공장: 전극 코팅 롤투롤 라인 + 건조 오븐 + 화성 공정 랙
        draw_cube(0.0, 0.34, 0.0, CELL * 0.9, 0.5, CELL * 0.7, color)
        for dx in (-1, 1):
            glPushMatrix()
            glTranslatef(dx * CELL * 0.3, 0.74, 0.0); glRotatef(90.0, 0.0, 0.0, 1.0)
            glRotatef(anim_t * 220.0 if active else 0.0, 0.0, 1.0, 0.0)
            draw_cylinder(0.0, -CELL * 0.2, 0.0, 0.16, CELL * 0.4, (0.6, 0.62, 0.66), sides=10)
            glPopMatrix()
        draw_cube(0.0, 0.74, 0.0, CELL * 0.62, 0.05, CELL * 0.34, accent)
        draw_cube(0.0, 1.02, 0.0, CELL * 0.5, 0.34, CELL * 0.44, STEEL_TRIM)
        for i in range(3):
            for j in range(2):
                draw_cube((i - 1) * 0.2, 0.5, CELL * 0.42, 0.13, 0.2 + j * 0.0, 0.09,
                          accent if (i + j) % 2 == 0 else (0.4, 0.42, 0.46))
        part_panel(-CELL * 0.36, 0.5, -CELL * 0.4, color,
                   blink=active and int(anim_t * 3) % 2 == 0, w=0.28)

    elif btype == "coal_power_plant":
        # 석탄 화력 발전소: 보일러동 + 쌍둥이 굴뚝 + 쌍곡선 냉각탑 + 석탄 벙커 + 점검 난간
        draw_cube(0.0, 1.0, -CELL * 0.06, CELL * 0.9, 1.95, CELL * 0.72, color)
        for i in range(4):                                                                  # 외벽 리브
            draw_cube(0.0, 0.35 + i * 0.5, -CELL * 0.06, CELL * 0.94, 0.06, CELL * 0.76, STEEL_TRIM)
        part_stack(-CELL * 0.28, 2.0, -CELL * 0.3, 0.2, 1.55)
        part_stack(CELL * 0.28, 2.0, -CELL * 0.3, 0.17, 1.25)
        part_smoke(-CELL * 0.28, 3.55, -CELL * 0.3, anim_t, active, 1.1)
        glow = (0.55 + 0.35 * abs(math.sin(anim_t * 2.5))) if active else 0.15
        draw_cube(0.0, 0.55, CELL * 0.32, 0.52, 0.36, 0.1,
                  (glow, glow * 0.34, 0.07))                                                # 연소실 창
        # 쌍곡선 냉각탑 (아래·위가 넓고 허리가 좁은 형태)
        cool = (0.60, 0.62, 0.66)
        draw_cylinder(CELL * 0.36, 0.12, CELL * 0.34, 0.30, 0.4, cool, sides=14)
        draw_cylinder(CELL * 0.36, 0.52, CELL * 0.34, 0.21, 0.55, cool, sides=14)
        draw_cylinder(CELL * 0.36, 1.07, CELL * 0.34, 0.27, 0.22, cool, sides=14)
        part_smoke(CELL * 0.36, 1.3, CELL * 0.34, anim_t, active, 0.85)
        draw_cube(-CELL * 0.4, 0.4, CELL * 0.34, 0.28, 0.66, 0.32, STEEL_TRIM)              # 석탄 벙커
        draw_pyramid(-CELL * 0.4, 0.73, CELL * 0.34, 0.38, 0.24, (0.2, 0.19, 0.18))
        part_railing(0.0, 1.98, -CELL * 0.06, CELL * 0.92, CELL * 0.74)
        part_ladder(-CELL * 0.46, 0.12, -CELL * 0.06, 1.9)

    elif btype == "coal_feeder":
        # 석탄 공급기: 저장 벙커 + 진동 피더 + 계량 벨트 + 발전소로 뻗는 슈트
        draw_cube(0.0, 0.24, 0.0, CELL * 0.78, 0.36, CELL * 0.62, color)
        draw_cube(0.0, 0.78, -CELL * 0.1, CELL * 0.56, 0.36, CELL * 0.44,
                  (color[0] * 0.8, color[1] * 0.8, color[2] * 0.8))                      # 벙커
        draw_pyramid(0.0, 0.6, -CELL * 0.1, CELL * 0.5, -0.28, (0.3, 0.29, 0.28))       # 깔때기
        draw_cube(0.0, 1.0, -CELL * 0.1, CELL * 0.6, 0.06, CELL * 0.48, STEEL_TRIM)
        shake = (math.sin(anim_t * 9.0) * 0.03) if active else 0.0
        draw_cube(shake, 0.46, CELL * 0.16, CELL * 0.5, 0.07, CELL * 0.3,
                  (0.2, 0.2, 0.21))                                                       # 계량 벨트
        for i in range(3):                                                                # 석탄 덩이
            p = ((anim_t * 1.2 + i / 3.0) % 1.0) - 0.5
            draw_cube(p * CELL * 0.44 + shake, 0.53, CELL * 0.16, 0.09, 0.07, 0.09,
                      (0.12, 0.12, 0.13))
        draw_cube(0.0, 0.34, CELL * 0.42, CELL * 0.3, 0.2, 0.16, STEEL_TRIM)             # 배출 슈트
        part_panel(-CELL * 0.34, 0.46, CELL * 0.34, color,
                   blink=active and int(anim_t * 4) % 2 == 0, w=0.24)

    elif btype == "heat_exchanger":
        # 열교환기: 쉘앤튜브 본체 + 양단 튜브시트 보닛 + 입출 노즐 + 응축수 트랩
        glPushMatrix()
        glTranslatef(0.0, 0.62, 0.0); glRotatef(90.0, 0.0, 0.0, 1.0)
        draw_cylinder(0.0, -CELL * 0.34, 0.0, 0.24, CELL * 0.68, color, sides=14)
        glPopMatrix()
        for dx in (-1, 1):                                                                # 보닛
            draw_cylinder(dx * CELL * 0.36, 0.62, 0.0, 0.27, 0.05, STEEL_TRIM, sides=14)
            draw_cube(dx * CELL * 0.44, 0.62, 0.0, 0.12, 0.34, 0.34,
                      (color[0] * 0.78, color[1] * 0.78, color[2] * 0.78))
        glow = (0.5 + 0.5 * abs(math.sin(anim_t * 3.0))) if active else 0.2
        for i in (-1, 0, 1):                                                              # 열 표시 배관
            draw_cylinder(i * 0.22, 0.9, 0.0, 0.06, 0.16,
                          (0.85 * glow, 0.45 * glow, 0.2 * glow), sides=8)
        part_pipe(0.0, 1.02, 0.0, 1, 0, 0, CELL * 0.5, 0.07, (0.6, 0.62, 0.66))
        for dx in (-1, 1):                                                                # 안장 받침
            draw_cube(dx * CELL * 0.2, 0.24, 0.0, 0.14, 0.34, CELL * 0.46, STEEL_TRIM)
        draw_cylinder(0.0, 0.18, CELL * 0.34, 0.08, 0.14, STEEL_TRIM, sides=8)           # 스팀 트랩

    elif btype == "exhaust_stack":
        # 배기탑: 콘크리트 기초 + 가이와이어로 지지되는 고연돌 + 항공장애등 + 필터 하우징
        draw_cube(0.0, 0.18, 0.0, CELL * 0.6, 0.28, CELL * 0.6, (0.5, 0.49, 0.47))
        part_stack(0.0, 0.32, 0.0, 0.26, 2.1)
        for a in range(3):                                                                # 가이 와이어
            ax = math.cos(a * 2.094) * CELL * 0.44
            az = math.sin(a * 2.094) * CELL * 0.44
            draw_cube(ax * 0.5, 0.95, az * 0.5, 0.03, 1.3, 0.03, (0.35, 0.35, 0.37))
            draw_cube(ax, 0.2, az, 0.1, 0.14, 0.1, STEEL_TRIM)
        blink = active and int(anim_t * 1.5) % 2 == 0
        draw_cube(0.0, 2.5, 0.0, 0.12, 0.08, 0.12,
                  (0.95, 0.2, 0.15) if blink else (0.35, 0.12, 0.1))                      # 항공장애등
        draw_cube(CELL * 0.36, 0.5, 0.0, 0.24, 0.5, 0.28, color)                          # 필터 하우징
        draw_cube(CELL * 0.36, 0.78, 0.0, 0.28, 0.05, 0.32, STEEL_TRIM)
        part_smoke(0.0, 2.42, 0.0, anim_t, active, 1.0)

    elif btype == "data_power_node":
        # 데이터 파워 노드: 계장 캐비닛 + 안테나 마스트 + 출력 단계 표시등(gauge 1~3)
        draw_cube(0.0, 0.42, 0.0, CELL * 0.6, 0.72, CELL * 0.5, color)
        draw_cube(0.0, 0.8, 0.0, CELL * 0.64, 0.06, CELL * 0.54, STEEL_TRIM)
        part_panel(0.0, 0.5, CELL * 0.27, color,
                   blink=active and int(anim_t * 2.5) % 2 == 0, w=0.36)
        for i in range(3):                                                                # 환기 슬릿
            draw_cube(0.0, 0.28 + i * 0.08, -CELL * 0.26, CELL * 0.38, 0.03, 0.03, STEEL_TRIM)
        draw_cylinder(0.0, 0.86, 0.0, 0.045, 0.5, STEEL_TRIM, sides=6)                    # 마스트
        level = int(gauge) if gauge is not None else 2
        on = (int(anim_t * 2.5) % 2 == 0) if active else True
        for i in range(3):                                                                 # 출력 단계등
            lamp = ((0.25, 0.75, 1.0) if on else (0.1, 0.3, 0.4)) if i < level else (0.2, 0.2, 0.22)
            draw_cube(0.0, 1.42 + i * 0.15, 0.0, 0.13, 0.09, 0.13, lamp)
        draw_cube(0.0, 1.9, 0.0, 0.05, 0.16, 0.05, STEEL_TRIM)

    elif btype == "modular_turbine":
        # 모듈러 터빈: 분할 케이싱 본체 + 볼트 플랜지 + 로터 + 증기 입구 노즐 + 계기반
        draw_cube(0.0, 0.26, 0.0, CELL * 0.9, 0.4, CELL * 0.7, color)                       # 스키드
        glPushMatrix()                                                                       # 가로 케이싱
        glTranslatef(0.0, 0.78, 0.0); glRotatef(90.0, 0.0, 0.0, 1.0)
        draw_cylinder(0.0, -CELL * 0.36, 0.0, 0.32, CELL * 0.72, (0.48, 0.5, 0.54), sides=14)
        glPopMatrix()
        draw_cube(0.0, 0.78, 0.0, CELL * 0.76, 0.07, CELL * 0.68, STEEL_TRIM)               # 분할면 플랜지
        for dx in (-1, 1):
            draw_cylinder(dx * CELL * 0.38, 0.78, 0.0, 0.33, 0.05, STEEL_TRIM, sides=14)
        spin = (anim_t * 240.0) if active else 0.0
        glPushMatrix()
        glTranslatef(0.0, 1.18, 0.0)
        glRotatef(spin, 0.0, 1.0, 0.0)
        for a in range(4):
            glPushMatrix(); glRotatef(a * 90.0, 0.0, 1.0, 0.0)
            draw_cube(0.24, 0.0, 0.0, 0.44, 0.06, 0.11,
                      (min(color[0] * 1.4, 1.0), min(color[1] * 1.4, 1.0), min(color[2] * 1.4, 1.0)))
            glPopMatrix()
        glPopMatrix()
        part_pipe(0.0, 0.5, -CELL * 0.4, 0, 0, -1, CELL * 0.24, 0.11, (0.7, 0.72, 0.76))    # 증기 입구
        part_panel(0.0, 0.5, CELL * 0.4, color, blink=active and int(anim_t * 4) % 2 == 0, w=0.32)
        part_railing(0.0, 1.02, 0.0, CELL * 0.92, CELL * 0.74)

    elif btype in ("turbine_hp_stage", "turbine_ip_stage", "turbine_lp_stage"):
        # 터빈 압력단: 단마다 케이싱 직경과 블레이드 크기가 다른 다단 터빈 모듈.
        # 고압 -> 저압으로 갈수록 케이싱이 굵어지고 회전이 느려진다.
        stage = {"turbine_hp_stage": 0, "turbine_ip_stage": 1, "turbine_lp_stage": 2}[btype]
        rad = 0.20 + stage * 0.055
        rpm = (340.0 - stage * 45.0) if active else 0.0
        draw_cube(0.0, 0.22, 0.0, CELL * 0.82, 0.32, CELL * 0.56, color)                  # 스키드
        glPushMatrix()                                                                     # 케이싱
        glTranslatef(0.0, 0.66, 0.0); glRotatef(90.0, 0.0, 0.0, 1.0)
        draw_cylinder(0.0, -CELL * 0.26, 0.0, rad, CELL * 0.52, (0.46, 0.48, 0.52), sides=14)
        glPopMatrix()
        for dx in (-1, 1):                                                                 # 단 플랜지
            draw_cylinder(dx * CELL * 0.27, 0.66, 0.0, rad + 0.03, 0.05, STEEL_TRIM, sides=14)
        draw_cube(0.0, 0.66, 0.0, CELL * 0.56, 0.05, rad * 2.1, STEEL_TRIM)               # 분할면
        glPushMatrix()                                                                     # 로터
        glTranslatef(0.0, 0.66, 0.0)
        glRotatef(90.0, 0.0, 0.0, 1.0)
        glRotatef(anim_t * rpm, 0.0, 1.0, 0.0)
        draw_cylinder(0.0, -CELL * 0.34, 0.0, 0.05, CELL * 0.68, (0.72, 0.73, 0.76), sides=8)
        for a in range(4):
            glPushMatrix(); glRotatef(a * 90.0, 0.0, 1.0, 0.0)
            draw_cube(0.0, 0.0, rad * 0.55, 0.06, rad * 0.9, 0.05, accent)
            glPopMatrix()
        glPopMatrix()
        for i in range(stage + 1):                                                         # 단 표시등
            draw_cube(0.0, 0.42, CELL * 0.3 - i * 0.12, 0.07, 0.05, 0.07, SAFETY)

    elif btype == "turbine_generator_block":
        # 터빈 제너레이터: 고정자 하우징 + 회전자 + 냉각 팬 + 출력 부싱 3상 + 여자기
        draw_cube(0.0, 0.24, 0.0, CELL * 0.88, 0.36, CELL * 0.66, color)
        glPushMatrix()                                                                     # 고정자
        glTranslatef(0.0, 0.74, 0.0); glRotatef(90.0, 0.0, 0.0, 1.0)
        draw_cylinder(0.0, -CELL * 0.3, 0.0, 0.3, CELL * 0.6, (0.5, 0.52, 0.56), sides=14)
        glPopMatrix()
        for i in range(4):                                                                 # 냉각 핀
            draw_cube(0.0, 0.74, (i - 1.5) * CELL * 0.16, CELL * 0.64, 0.62, 0.04, STEEL_TRIM)
        glPushMatrix()                                                                      # 회전자 축
        glTranslatef(0.0, 0.74, 0.0); glRotatef(90.0, 0.0, 0.0, 1.0)
        glRotatef(anim_t * 300.0 if active else 0.0, 0.0, 1.0, 0.0)
        draw_cylinder(0.0, -CELL * 0.42, 0.0, 0.06, CELL * 0.84, (0.74, 0.75, 0.78), sides=8)
        draw_cube(0.0, CELL * 0.36, 0.0, 0.3, 0.05, 0.1, (0.86, 0.88, 0.9))
        glPopMatrix()
        pulse = (0.5 + 0.5 * abs(math.sin(anim_t * 5.0))) if active else 0.2
        for dx in (-1, 0, 1):                                                              # 3상 부싱
            draw_cylinder(dx * 0.22, 1.06, 0.0, 0.05, 0.26, (0.78, 0.78, 0.72), sides=6)
            draw_cube(dx * 0.22, 1.34, 0.0, 0.1, 0.06, 0.1,
                      (0.9 * pulse, 0.75 * pulse, 0.15 * pulse))
        draw_cylinder(-CELL * 0.42, 0.5, 0.0, 0.13, 0.3, accent, sides=10)                 # 여자기

    elif btype == "power_meter":
        # 전력 속도 카운터: 계기 캐비닛 + 순 발전량 막대 게이지(+초록/-빨강) + 눈금 + 표시등.
        # gauge에는 소속 전력망의 순 발전량(공급-수요)이 들어온다.
        flow = gauge if gauge is not None else 0.0
        level = max(0.08, min(1.0, abs(flow) / 40.0))
        bar_color = (0.20, 0.85, 0.30) if flow >= 0.0 else (0.90, 0.20, 0.20)
        draw_cube(0.0, 0.26, 0.0, CELL * 0.56, 0.44, CELL * 0.44, color)                 # 캐비닛
        draw_cube(0.0, 0.5, 0.0, CELL * 0.6, 0.06, CELL * 0.48, STEEL_TRIM)
        draw_cube(0.0, 0.34, CELL * 0.23, CELL * 0.4, 0.24, 0.05, (0.15, 0.16, 0.18))    # 계기창
        draw_cube(0.0, 0.34, CELL * 0.26, CELL * 0.34 * level, 0.12, 0.03, bar_color)    # 막대 표시
        for dz in (-1, 1):                                                                # 게이지 기둥
            draw_cube(dz * 0.13, 0.95, 0.0, 0.07, 0.86, 0.07, STEEL_TRIM)
        draw_cylinder(0.0, 0.56, 0.0, 0.14, 0.05, (0.15, 0.15, 0.16), sides=10)          # 눈금판
        draw_cylinder(0.0, 0.61, 0.0, 0.09, 1.0 * level, bar_color, sides=10)            # 흐름 게이지
        for i in range(5):                                                                # 눈금 표시
            draw_cube(0.16, 0.66 + i * 0.2, 0.0, 0.08, 0.02, 0.02, STEEL_TRIM)
        blink = active and int(anim_t * 3.0) % 2 == 0
        draw_cube(0.0, 1.66, 0.0, 0.11, 0.08, 0.11,
                  bar_color if blink else (0.2, 0.2, 0.22))                               # 상단 표시등

    elif btype == "transformer":
        # 변압기: 유입식 본체 + 방열핀 뱅크 + 자기 부싱 3상 + 콘서베이터 + 방유턱
        draw_cube(0.0, 0.1, 0.0, CELL * 0.9, 0.14, CELL * 0.8, (0.42, 0.41, 0.39))       # 방유턱
        draw_cube(0.0, 0.5, 0.0, CELL * 0.6, 0.66, CELL * 0.56, color)                    # 본체
        draw_cube(0.0, 0.85, 0.0, CELL * 0.64, 0.06, CELL * 0.6, STEEL_TRIM)
        for dz in (-1, 1):                                                                 # 방열핀
            for i in range(5):
                draw_cube((i - 2) * CELL * 0.13, 0.5, dz * CELL * 0.34,
                          0.05, 0.56, CELL * 0.14, (0.5, 0.51, 0.54))
        draw_cylinder(0.0, 0.9, -CELL * 0.3, 0.1, 0.3, (0.55, 0.56, 0.6), sides=10)       # 콘서베이터
        pulse = (0.7 + 0.3 * abs(math.sin(anim_t * 9.0))) if active else 0.3
        for dx in (-1, 0, 1):                                                              # 자기 부싱
            draw_cylinder(dx * 0.24, 0.88, CELL * 0.12, 0.05, 0.34, (0.78, 0.76, 0.7), sides=6)
            for k in range(3):
                draw_cylinder(dx * 0.24, 0.94 + k * 0.1, CELL * 0.12, 0.08, 0.03,
                              (0.72, 0.7, 0.64), sides=6)
            draw_cube(dx * 0.24, 1.26, CELL * 0.12, 0.09, 0.05, 0.09,
                      (0.9 * pulse, 0.85 * pulse, 0.4 * pulse))

    elif btype == "battery_cell":
        # 배터리(1MMF): 랙에 꽂힌 셀 모듈 + 충전 상태 게이지(gauge 0~1) + 인버터 캐비닛
        draw_cube(0.0, 0.44, 0.0, CELL * 0.72, 0.76, CELL * 0.56, color)
        draw_cube(0.0, 0.84, 0.0, CELL * 0.76, 0.06, CELL * 0.6, STEEL_TRIM)
        frac = max(0.0, min(1.0, gauge if gauge is not None else 0.0))
        for i in range(4):                                                                 # 셀 모듈 4단
            lit = frac > (i + 0.5) / 4.0
            draw_cube(0.0, 0.2 + i * 0.17, CELL * 0.29, CELL * 0.56, 0.12, 0.05,
                      (0.25, 0.9, 0.45) if lit else (0.22, 0.24, 0.26))
        draw_cube(CELL * 0.42, 0.4, 0.0, 0.16, 0.5, CELL * 0.34, STEEL_TRIM)              # 인버터
        blink = active and int(anim_t * 3.0) % 2 == 0
        draw_cube(CELL * 0.42, 0.62, CELL * 0.14, 0.06, 0.05, 0.05,
                  (0.3, 0.95, 0.5) if blink else (0.12, 0.3, 0.18))
        draw_cube(0.0, 0.92, 0.0, CELL * 0.5, 0.05, 0.07, (0.72, 0.55, 0.22))             # 버스바

    elif btype == "hv_battery":
        # 고압 배터리(1GMMF): 컨테이너형 ESS 2단 적재 + 냉각 유닛 + 대용량 충전 게이지
        frac = max(0.0, min(1.0, gauge if gauge is not None else 0.0))
        for lvl in range(2):                                                               # 컨테이너 2단
            y = 0.42 + lvl * 0.76
            draw_cube(0.0, y, 0.0, CELL * 0.88, 0.7, CELL * 0.62, color)
            draw_cube(0.0, y + 0.38, 0.0, CELL * 0.92, 0.06, CELL * 0.66, STEEL_TRIM)
            for i in range(4):                                                             # 컨테이너 리브
                draw_cube((i - 1.5) * CELL * 0.22, y, CELL * 0.32, 0.05, 0.62, 0.04, STEEL_TRIM)
        for i in range(8):                                                                 # 충전 게이지
            lit = frac > (i + 0.5) / 8.0
            draw_cube(CELL * 0.46, 0.2 + i * 0.16, 0.0, 0.05, 0.1, CELL * 0.3,
                      (0.95, 0.6, 0.1) if lit else (0.22, 0.24, 0.26))
        draw_cube(0.0, 1.58, 0.0, CELL * 0.5, 0.22, CELL * 0.4, STEEL_TRIM)               # 냉각 유닛
        glPushMatrix()
        glTranslatef(0.0, 1.72, 0.0)
        glRotatef(anim_t * 260.0 if active else 0.0, 0.0, 1.0, 0.0)
        draw_cube(0.0, 0.0, 0.0, 0.4, 0.04, 0.1, (0.8, 0.82, 0.85))
        draw_cube(0.0, 0.0, 0.0, 0.1, 0.04, 0.4, (0.8, 0.82, 0.85))
        glPopMatrix()


# ---- 건물 렌더 배치 처리 ------------------------------------------------------
# 즉시모드(glVertex3f)는 정점 하나마다 파이썬->C 호출이 일어나서, 건물이 조금만
# 늘어도 프레임을 통째로 잡아먹는다(측정: 50채에 11FPS). 다만 같은 프레임 안에서
# 같은 종류·같은 상태의 건물은 형상이 완전히 똑같으므로, 종류당 한 번만 디스플레이
# 리스트로 컴파일해두고 나머지 인스턴스는 위치만 바꿔 재생하면 된다.
_MODEL_LISTS = {}      # key -> [list_id, 마지막으로 컴파일한 애니메이션 틱]
_MODEL_TICK = 0        # 현재 애니메이션 틱 (begin_model_frame이 갱신)
# 애니메이션을 화면 주사율(60fps)에 맞춰 매번 다시 컴파일할 필요는 없다. 초당 이 횟수만
# 형상을 갱신해도 눈으로는 차이가 없고, 재컴파일 비용은 그만큼 줄어든다.
MODEL_ANIM_FPS = 24
_STATIC_CACHE = {}     # (btype, active) -> 이 건물이 애니메이션 없이 고정된 형상인지


def _model_is_static(btype, active):
    """이 건물이 시간에 따라 모양이 변하는지(애니메이션이 있는지) 한 번만 판별해둔다.
    서로 다른 두 시각으로 형상을 그려보고 결과가 완전히 같으면 정적이라고 본다.
    정적인 건물(태양광·파이프 등)은 디스플레이 리스트를 매 프레임 다시 만들 필요가 없어서,
    공장이 커질수록 재컴파일 비용을 크게 줄여준다."""
    key = (btype, active)
    cached = _STATIC_CACHE.get(key)
    if cached is not None:
        return cached

    rec = []
    # 모양 자체를 그리는 호출뿐 아니라 glRotatef/glTranslatef 도 함께 기록해야 한다.
    # 터빈 날개처럼 draw_cube 인자는 그대로인 채 회전각만 바뀌는 건물이 있어서,
    # 도형 호출만 비교하면 "정적"이라고 잘못 판단하게 된다.
    names = ("draw_cube", "draw_cylinder", "draw_pyramid", "glRotatef", "glTranslatef")
    orig = {n: globals()[n] for n in names}

    def snapshot(anim_t):
        rec.clear()
        for n in names:
            def mk(tag, real):
                def f(*a, **k):
                    rec.append((tag, a, tuple(sorted(k.items()))))
                    return real(*a, **k)
                return f
            globals()[n] = mk(n, orig[n])
        try:
            color = BUILD_COLOR.get(btype, (0.5, 0.5, 0.5))
            _draw_model_geometry(btype, industrial_tint(color), color, anim_t, active,
                                  2, [(1, 0)], (1.0, 0.0, 0.0), 0.0)
        finally:
            globals().update(orig)
        return list(rec)

    static = snapshot(0.0) == snapshot(1.73)
    _STATIC_CACHE[key] = static
    return static


def begin_model_frame(anim_time=0.0):
    """새 프레임 시작을 알린다. 애니메이션 틱이 바뀐 경우에만 형상을 다시 만든다."""
    global _MODEL_TICK
    _MODEL_TICK = int(anim_time * MODEL_ANIM_FPS)


def draw_building_model_batched(btype, wx, wz, color, facing_deg=0.0, anim_t=0.0,
                                 active=True, gauge=None, connects=None, filter_color=None):
    """draw_building_model과 결과는 같지만, 같은 프레임에서 형상이 동일한 건물끼리
    디스플레이 리스트를 공유한다. 컨베이어 30개가 있으면 1번만 컴파일하고 29번은
    재생만 하므로, 건물이 많을수록 이득이 커진다."""
    # gauge는 배터리 충전량처럼 연속으로 변하는 실수라, 그대로 키에 쓰면 값이 조금만
    # 바뀌어도 새 디스플레이 리스트가 무한정 생성된다(=GL 리소스 누수). 눈에 안 보일
    # 정도로 잘게 구간을 나눠 캐시가 유한하게 유지되도록 한다.
    gkey = None if gauge is None else round(gauge * 32) / 32
    key = (btype, active, gkey,
           tuple(connects) if connects else None,
           filter_color)
    entry = _MODEL_LISTS.get(key)
    if entry is None:
        entry = [glGenLists(1), -1]
        _MODEL_LISTS[key] = entry
    # 애니메이션이 없는 건물은 한 번 만들어두면 계속 재사용한다(entry[1] = -2로 표시).
    if entry[1] != _MODEL_TICK and entry[1] != -2:
        accent = color
        glNewList(entry[0], GL_COMPILE)
        _draw_model_geometry(btype, industrial_tint(color), accent, anim_t, active,
                              gauge, connects, filter_color, facing_deg)
        glEndList()
        entry[1] = -2 if _model_is_static(btype, active) else _MODEL_TICK
    glPushMatrix()
    glTranslatef(wx, 0.0, wz)
    glRotatef(facing_deg, 0.0, 1.0, 0.0)
    glCallList(entry[0])
    glPopMatrix()


# ----------------------------------------------------------------------
# 2D 오버레이 (HUD / 메뉴) 렌더링
# ----------------------------------------------------------------------
# blit_text 텍스처 캐시: (폰트, 문자열, 색상) -> (tex_id, w, h).
# 글자 하나 그릴 때마다 GPU 텍스처를 새로 만들고 지우면, 건물 메뉴처럼 한 프레임에
# 수십 개 라벨을 그리는 화면에서 초당 수천 번 텍스처가 생성/삭제되어 일부 드라이버
# (특히 내장 GPU)에서 텍스처 상태가 깨지고 화면의 모든 글자가 사라지는 문제가 있었다.
# 같은 문자열은 텍스처를 재사용하도록 캐시해서 프레임당 생성 횟수를 크게 줄인다.
_TEXT_TEXTURE_CACHE = {}
_TEXT_CACHE_ORDER = []
_TEXT_CACHE_MAX = 512   # 계속 바뀌는 숫자 텍스트 때문에 무한정 쌓이지 않도록 오래된 것부터 정리


def _get_text_texture(font, text, color):
    key = (id(font), text, color)
    cached = _TEXT_TEXTURE_CACHE.get(key)
    if cached is not None:
        return cached
    surf = font.render(text, True, color).convert_alpha()
    w, h = surf.get_size()
    if w == 0 or h == 0:
        return None
    data = pygame.image.tobytes(surf, "RGBA", True)

    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)

    entry = (tex_id, w, h)
    _TEXT_TEXTURE_CACHE[key] = entry
    _TEXT_CACHE_ORDER.append(key)
    if len(_TEXT_CACHE_ORDER) > _TEXT_CACHE_MAX:
        old_key = _TEXT_CACHE_ORDER.pop(0)
        old_entry = _TEXT_TEXTURE_CACHE.pop(old_key, None)
        if old_entry is not None:
            glDeleteTextures([old_entry[0]])
    return entry


def blit_text(font, text, x, y, color=(255, 255, 255)):
    """x, y는 화면 좌상단 기준(픽셀, float 허용). pygame 표면을 텍스처로 올려
    사각형에 입혀 그린다. (glRasterPos+glDrawPixels 방식은 최신 드라이버 다수가
    사실상 지원하지 않아 글자가 아예 안 보이는 문제가 있어 텍스처 방식을 쓴다.)"""
    if not text:
        return
    entry = _get_text_texture(font, text, color)
    if entry is None:
        return
    tex_id, w, h = entry

    top = HEIGHT - y
    bottom = HEIGHT - (y + h)
    glEnable(GL_TEXTURE_2D)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glColor4f(1.0, 1.0, 1.0, 1.0)
    glBegin(GL_QUADS)
    glTexCoord2f(0, 0); glVertex2f(x, bottom)
    glTexCoord2f(1, 0); glVertex2f(x + w, bottom)
    glTexCoord2f(1, 1); glVertex2f(x + w, top)
    glTexCoord2f(0, 1); glVertex2f(x, top)
    glEnd()
    glDisable(GL_BLEND)
    glDisable(GL_TEXTURE_2D)


def draw_rect_2d(x, y, w, h, color, alpha=1.0):
    """x, y는 화면 좌상단 기준(픽셀)의 사각형을 ortho 좌표계로 변환해 채운다."""
    top = HEIGHT - y
    bottom = HEIGHT - (y + h)
    glColor4f(color[0], color[1], color[2], alpha)
    glBegin(GL_QUADS)
    glVertex2f(x, bottom); glVertex2f(x + w, bottom)
    glVertex2f(x + w, top); glVertex2f(x, top)
    glEnd()


def draw_rect_outline_2d(x, y, w, h, width=1.0):
    """현재 glColor로 설정된 색을 써서 사각형 테두리만 그린다."""
    top = HEIGHT - y
    bottom = HEIGHT - (y + h)
    glLineWidth(width)
    glBegin(GL_LINE_LOOP)
    glVertex2f(x, bottom); glVertex2f(x + w, bottom)
    glVertex2f(x + w, top); glVertex2f(x, top)
    glEnd()
    glLineWidth(1.0)


def draw_bar_2d(x, y, w, h, frac, color, bg_color=(0.15, 0.15, 0.18)):
    """0~1 비율(frac)만큼 채워지는 가로 게이지 바 (배경 + 채움 + 테두리)."""
    frac = max(0.0, min(1.0, frac))
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    draw_rect_2d(x, y, w, h, bg_color, alpha=0.75)
    if frac > 0.0:
        draw_rect_2d(x, y, w * frac, h, color, alpha=0.95)
    glColor3f(0.85, 0.85, 0.85)
    draw_rect_outline_2d(x, y, w, h, width=1.5)
    glDisable(GL_BLEND)


def _begin_ortho_overlay():
    """3D 렌더링을 잠시 멈추고 화면 좌표계(2D)로 전환한다. HUD/메뉴를 그릴 때 사용."""
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    glOrtho(0, WIDTH, 0, HEIGHT, -1, 1)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_FOG)


def _end_ortho_overlay():
    """_begin_ortho_overlay로 바꿔둔 상태를 원래 3D 렌더링 상태로 되돌린다."""
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_FOG)
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


def _item_label_list(value):
    """RECIPES 산출물처럼 문자열 하나 또는 문자열 리스트로 오는 아이템 타입을,
    쉼표로 이은 한글 라벨 문자열로 바꾼다."""
    items = value if isinstance(value, (list, tuple)) else [value]
    return ", ".join(ITEM_LABEL.get(v, v) for v in items)


def build_menu_info(btype):
    """건물 메뉴에서 우클릭으로 여는 상세 정보 패널에 쓸 줄(list[str])을 만든다.
    설명 문구(BUILD_DESC)는 손으로 쓰지만, 재료/전력/보너스 수치는 기존 레시피·전력
    레지스트리에서 그대로 뽑아와 항상 실제 수치와 어긋나지 않게 한다."""
    lines = [BUILD_LABEL.get(btype, btype), f"가격: ${BUILD_COST.get(btype, 0)}"]
    desc = BUILD_DESC.get(btype)
    if desc:
        lines.append(desc)

    if btype in POWER_DRAW:
        lines.append(f"소모 전력: {POWER_DRAW[btype]:.1f} MF/s")
    if btype in POWER_SUPPLY:
        lines.append(f"공급 전력: {POWER_SUPPLY[btype]:.1f} MF/s")
    if btype in POWER_STORAGE:
        lines.append(f"전력 저장 용량: {POWER_STORAGE[btype]:.0f} MF")

    if btype in DEPOSIT_OUTPUT:
        outs = sorted(set(ITEM_LABEL.get(v, v) for v in DEPOSIT_OUTPUT[btype].values()))
        lines.append(f"채굴 대상: {', '.join(outs)} (부지 어디에 설치하든 채굴됨)")

    if btype in RECIPES:
        for inp, out in RECIPES[btype].items():
            lines.append(f"재료: {ITEM_LABEL.get(inp, inp)}  ->  산출: {_item_label_list(out)}")

    if btype in MULTI_RECIPES:
        recipe = MULTI_RECIPES[btype]
        needs = ", ".join(f"{ITEM_LABEL.get(k, k)} {v}개" for k, v in recipe["inputs"].items())
        lines.append(f"필요 재료: {needs}")
        lines.append(f"산출: {_item_label_list(recipe['output'])}")

    if btype == "blast_furnace":
        fuel_label = " 또는 ".join(ITEM_LABEL.get(f, f) for f in sorted(FUEL_LIKE_ITEMS))
        for primary, out in BLAST_FURNACE_PRIMARY.items():
            lines.append(f"{ITEM_LABEL.get(primary, primary)} + {fuel_label}  ->  {ITEM_LABEL.get(out, out)}")

    if btype in DYNAMIC_RECIPES:
        for recipe in DYNAMIC_RECIPES[btype]:
            needs = " + ".join(f"{ITEM_LABEL.get(k, k)}" + (f" {v}개" if v > 1 else "")
                               for k, v in recipe["inputs"].items())
            lines.append(f"{needs}  ->  {_item_label_list(recipe['output'])}")

    if btype == "mineshaft_drill":
        lines.append("드릴 헤드를 넣어야 작동, 캘 때마다 내구도 소모 (T로 깊이 변경):")
        for head, min_depth in DRILL_HEAD_MIN_DEPTH.items():
            lines.append(f"  {ITEM_LABEL.get(head, head)}: 내구도 {DRILL_HEAD_DURABILITY[head]:.0f}, "
                         f"{DRILL_DEPTH_LABEL[min_depth]} 이상 필요")
        for depth, pool in DRILL_DEPTH_OUTPUTS.items():
            outs = ", ".join(ITEM_LABEL.get(t, t) for t, _w in pool)
            lines.append(f"{DRILL_DEPTH_LABEL[depth]}: {outs}")
        lines.append("산: 내구도 +20  |  머신오일: 10사이클 2배속+증산(마모 증가)  |  다이너마이트: 5사이클 2배속")

    if btype in FUEL_BURNERS:
        info = FUEL_BURNERS[btype]
        lines.append(f"연료: {ITEM_LABEL.get(info['fuel_item'], info['fuel_item'])} "
                     f"(1개당 {info['fuel_per_item']:.1f}초 가동)")
        lines.append(f"발전량: {info['power']:.0f} MF/s   오염: {info['pollution']:.2f}/s")

    for core_type, (_family, bonus_table) in FAMILY_PART_BONUS.items():
        if btype in bonus_table:
            bonus = bonus_table[btype]
            parts = []
            if "power" in bonus:
                parts.append(f"발전량 +{bonus['power']:.0f} MF")
            if "pollution" in bonus:
                parts.append(f"오염 {bonus['pollution']:+.2f}/s")
            if "fuel_per_item" in bonus:
                parts.append(f"연료 효율 +{bonus['fuel_per_item']:.0f}초")
            lines.append(f"{BUILD_LABEL.get(core_type, core_type)}에 인접 시: " + ", ".join(parts))
            break

    if btype == "scrubber":
        lines.append(f"오염 감소량: {SCRUBBER_POLLUTION_REDUCTION:.1f}/s (전력 가동 중일 때)")
    if btype == "research":
        lines.append(f"연구 포인트 생산: {RESEARCH_RP_RATE:.1f} RP/s (전력 가동 중일 때)")
        lines.append(f"RP {RP_PER_TIER:.0f}마다 전 건물 가동률 +{RP_BONUS_PER_TIER * 100:.0f}%"
                     f" (최대 +{RP_BONUS_MAX * 100:.0f}%)")

    return lines


def build_aim_info(world, gx, gz):
    """조준(크로스헤어)이 가리키는 칸에 건물이 있으면, 화면에 보여줄 정보 줄(list[str])을
    만들어 돌려준다. 건물이 없으면 None. 건물 종류에 따라 가동률/연료/충전량/가공중인
    재료/지나가는 아이템 등 "지금 무엇이 있는지"에 해당하는 항목만 골라서 붙인다."""
    b = world.buildings.get((gx, gz))
    if b is None:
        return None
    t = b["type"]
    lines = [BUILD_LABEL.get(t, t)]

    if t in POWER_NODE_TYPES:
        eff = world.building_efficiency.get((gx, gz))
        if eff is not None:
            lines.append(f"가동률: {eff * 100:.0f}%")

    if t in FUEL_BURNERS:
        info = get_burner_stats(world, (gx, gz))
        lines.append(f"연료: {b['fuel']:.1f}s / {info['fuel_per_item']:.1f}s")
        if t in FAMILY_PART_BONUS:
            family, _ = FAMILY_PART_BONUS[t]
            _, parts = _family_cluster(world, (gx, gz), family, t)
            if parts:
                part_names = ", ".join(sorted(BUILD_LABEL.get(p, p) for p in parts))
                lines.append(f"발전량: {info['power']:.0f} MF  (부품: {part_names})")
            else:
                lines.append(f"발전량: {info['power']:.0f} MF  (부품 없음)")

    if t == "gas_input_block":
        turbines, _ = _gas_turbine_cluster(world, (gx, gz))
        if turbines:
            lines.append(f"연결된 가스터빈: {len(turbines)}개  (정제가스를 받으면 나눠서 공급)")
        else:
            lines.append("연결된 가스터빈 없음 (사방으로 이어 붙여야 함)")

    if t in COAL_PLANT_FAMILY - {"coal_power_plant"}:
        cores, _ = _family_cluster(world, (gx, gz), COAL_PLANT_FAMILY, "coal_power_plant")
        if t != "heat_exchanger":
            lines.append(f"연결된 석탄 화력 발전소: {len(cores)}개" if cores
                         else "연결된 발전소 없음 (사방으로 이어 붙여야 함)")
        if t == "heat_exchanger":
            # 이제 발전소 연결은 필수 조건이 아니라 장식용 - 전력만 있으면 물을 바로
            # 고압 증기로 바꾼다. 여기서는 그냥 전력 가동률(위에서 이미 표시됨)만으로 충분.
            lines.append("물이 들어오면 자동으로 고압 증기로 바꿈 (전력 필요)")
        if t == "data_power_node":
            level_label = {1: "저출력 (절약)", 2: "표준", 3: "고출력 (오염 증가)"}
            lines.append(f"출력 단계: {level_label.get(b.get('node_level', 2))}  (T 로 변경)")

    if t == "mineshaft_drill":
        depth = b.get("drill_depth", 1)
        lines.append(f"채굴 깊이: {DRILL_DEPTH_LABEL[depth]}  (T 로 변경)")
        head = b.get("drill_head")
        if head is None:
            lines.append("드릴 헤드 없음 - 드릴 헤드를 넣어야 작동함")
        else:
            durability = b.get("drill_head_durability", 0.0)
            max_durability = DRILL_HEAD_DURABILITY[head]
            lines.append(f"드릴 헤드: {ITEM_LABEL.get(head, head)}  ({durability:.0f}/{max_durability})")
            if DRILL_HEAD_MIN_DEPTH[head] < depth:
                lines.append("이 헤드로는 이 깊이를 감당할 수 없음 - 대기 중")
        boosts = []
        if b.get("oil_boost", 0) > 0:
            boosts.append(f"머신오일 {b['oil_boost']}사이클 (2배속+증산/마모 증가)")
        if b.get("dynamite_boost", 0) > 0:
            boosts.append(f"다이너마이트 {b['dynamite_boost']}사이클 (2배속)")
        if boosts:
            lines.append("효과: " + ", ".join(boosts))

    if t in MODULAR_TURBINE_FAMILY - {"modular_turbine"}:
        cores, _ = _family_cluster(world, (gx, gz), MODULAR_TURBINE_FAMILY, "modular_turbine")
        lines.append(f"연결된 모듈러 터빈: {len(cores)}개" if cores
                     else "연결된 터빈 없음 (사방으로 이어 붙여야 함)")
        if t == "turbine_hp_stage":
            lines.append("터빈 인풋: 열교환기의 고압 증기를 파이프로 여기에 연결하세요")

    if t in POWER_STORAGE:
        cap = POWER_STORAGE[t]
        lines.append(f"충전량: {b['charge']:.0f} / {cap:.0f} MF")

    if t == "power_meter":
        flow = world.building_flow.get((gx, gz), 0.0)
        lines.append(f"순 발전량: {'+' if flow >= 0 else ''}{flow:.1f} MF/s")

    if t == "core":
        stored = {k: v for k, v in world.core_storage.items() if v > 0}
        total = sum(stored.values())
        lines.append(f"보관 중: 총 {total}개 / {len(stored)}종")
        # 많이 쌓인 순으로 상위 몇 종만 보여준다 (패널이 너무 길어지지 않도록)
        for k, v in sorted(stored.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"  {ITEM_LABEL.get(k, k)}: {v}")
        if len(stored) > 8:
            lines.append(f"  ... 외 {len(stored) - 8}종")

    if t == "item_filter":
        target = b.get("filter_item")
        setting = "필터 없음 (전부 통과)" if target is None else ITEM_LABEL.get(target, target)
        lines.append(f"필터 설정: {setting}  (F 로 변경)")

    if t == "drone_transporter":
        target = b.get("drone_item")
        setting = "대상 없음 (G 로 지정)" if target is None else ITEM_LABEL.get(target, target)
        lines.append(f"운반 대상: {setting}  (G 로 변경)")

    if t == "drone_payload":
        target = b.get("drone_item")
        setting = "대상 없음 (G 로 지정)" if target is None else ITEM_LABEL.get(target, target)
        lines.append(f"수신 대상: {setting}  (G 로 변경)")
        lines.append(f"대기중: {b.get('payload_count', 0)}개")

    if (t in MULTI_RECIPES or t in DYNAMIC_RECIPES) and b.get("buffer"):
        parts = [format_item_amount(k, v) for k, v in b["buffer"].items() if v > 0]
        if parts:
            lines.append("모인 재료: " + ", ".join(parts))

    if t == "blast_furnace" and b.get("buffer"):
        buf = b["buffer"]
        parts = []
        if buf.get("primary", 0) > 0:
            parts.append(format_item_amount(buf["primary_item"]))
        if buf.get("fuel", 0) > 0:
            parts.append("연료 1개")
        if parts:
            lines.append("모인 재료: " + ", ".join(parts))

    proc = b.get("processing_item")
    if proc:
        proc_list = proc if isinstance(proc, (list, tuple)) else [proc]
        lines.append("가공중: " + ", ".join(format_item_amount(p) for p in proc_list))

    if t in DEPOSIT_OUTPUT:
        output_item = next(iter(DEPOSIT_OUTPUT[t].values()))
        lines.append(f"채굴 중: {ITEM_LABEL.get(output_item, output_item)}")

    for it in world.items:
        if it["gx"] == gx and it["gz"] == gz:
            lines.append(f"지나가는 중: {format_item_amount(it['type'])}")
            break

    return lines


# ----------------------------------------------------------------------
# HUD (상단 상태 표시줄)
# ----------------------------------------------------------------------
class Hud:
    def __init__(self):
        self.font = pygame.font.SysFont("malgungothic,arial", 22)
        self.small = pygame.font.SysFont("malgungothic,arial", 15)

    def draw(self, world, selected, fps, show_crosshair=True, aim_info=None):
        _begin_ortho_overlay()

        blit_text(self.font, f"돈: ${world.money:,.0f}", 16, 12, (255, 230, 120))
        money_frac = min(1.0, world.money / 1000.0)  # 시각적 기준(1000이면 가득 참), 정확한 값은 텍스트로
        draw_bar_2d(230, 16, 150, 14, money_frac, (0.95, 0.75, 0.20))

        pol = world.pollution
        pol_color = (255, 90, 90) if pol > 60 else ((255, 220, 100) if pol > 25 else (140, 230, 150))
        blit_text(self.font, f"오염도: {pol:5.1f}%", 16, 42, pol_color)
        pol_bar_color = (pol_color[0] / 255.0, pol_color[1] / 255.0, pol_color[2] / 255.0)
        draw_bar_2d(230, 46, 150, 14, pol / 100.0, pol_bar_color)

        eff_pct = world.power_efficiency * 100
        eff_color = (140, 230, 150) if eff_pct >= 99 else (255, 120, 90)
        blit_text(self.font,
                  f"전력(총합): {world.power_supply:.0f} / {world.power_draw:.0f} MF  (평균 {eff_pct:.0f}%)",
                  16, 72, eff_color)
        # RP는 100마다 한 단계씩 모든 건물의 가동률을 올려준다. 지금 몇 % 보너스를 받고
        # 있는지, 다음 단계까지 얼마나 남았는지 함께 보여준다.
        bonus = world.research_bonus
        pct = (bonus - 1.0) * 100.0
        capped = bonus >= 1.0 + RP_BONUS_MAX - 1e-9
        rp_txt = f"RP: {world.research_points:,.0f}   전 건물 효율 +{pct:.0f}%"
        if capped:
            rp_txt += " (최대)"
        else:
            need = RP_PER_TIER - (world.research_points % RP_PER_TIER)
            rp_txt += f"  (다음 단계까지 {need:,.0f})"
        blit_text(self.font, rp_txt, 16, 102, (210, 160, 255))

        blit_text(self.small, f"선택된 건물: {BUILD_LABEL[selected]}  (${BUILD_COST[selected]})",
                  16, 134, (255, 230, 120))
        blit_text(self.small,
                  "B 건물메뉴 | 2 와이어 | 3 파이핑 | R 방향회전 | F 필터설정 | 좌클릭 설치 | 우클릭 철거 | ESC 종료",
                  16, HEIGHT - 30, (255, 255, 255))
        blit_text(self.small, f"FPS: {fps:.0f}", WIDTH - 110, 12, (255, 255, 255))

        if show_crosshair:
            cx, cy = WIDTH // 2, HEIGHT // 2
            glColor3f(1, 1, 1)
            glBegin(GL_LINES)
            glVertex2f(cx - 8, cy); glVertex2f(cx + 8, cy)
            glVertex2f(cx, cy - 8); glVertex2f(cx, cy + 8)
            glEnd()

            if aim_info:
                pad = 10
                line_h = 20
                panel_w = max(160, max(self.small.size(line)[0] for line in aim_info) + pad * 2)
                panel_h = len(aim_info) * line_h + pad * 2
                panel_x = cx - panel_w / 2.0
                panel_y = cy + 26
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                draw_rect_2d(panel_x, panel_y, panel_w, panel_h, (0.05, 0.05, 0.07), alpha=0.72)
                glDisable(GL_BLEND)
                draw_rect_outline_2d(panel_x, panel_y, panel_w, panel_h, width=1.5)
                for i, line in enumerate(aim_info):
                    text_color = (255, 230, 140) if i == 0 else (230, 230, 230)
                    blit_text(self.small, line, panel_x + pad, panel_y + pad + i * line_h, text_color)

        _end_ortho_overlay()


# ----------------------------------------------------------------------
# 건물 메뉴 (B키로 열고, 마우스로 클릭해서 건물 선택)
# ----------------------------------------------------------------------
class BuildMenu:
    BTN_W, BTN_H = 128, 64
    GAP_X, GAP_Y = 10, 24
    START_X, START_Y = 60, 124   # START_Y는 스크롤되는 콘텐츠 내부 기준 좌표 (VIEWPORT_TOP+24와 맞춤)
    VIEWPORT_TOP = 100          # 이 y 아래부터가 실제로 보이는 스크롤 영역
    VIEWPORT_BOTTOM = HEIGHT - 50
    SCROLL_STEP = 70.0

    def __init__(self):
        self.font = pygame.font.SysFont("malgungothic,arial", 17)
        self.small = pygame.font.SysFont("malgungothic,arial", 13)
        self.group_labels = []   # [(text, x, y)] - y는 콘텐츠 기준(스크롤 전) 좌표
        self.buttons = []        # [{"type": btype, "rect": (x, y, w, h)}] - y는 콘텐츠 기준 좌표
        self.scroll_offset = 0.0
        self.icon_textures = {}  # main()에서 load_icon_textures()로 채워짐
        self.detail_btype = None  # 우클릭으로 상세 정보(재료/전력/설명)를 열어둔 건물 (없으면 None)
        self._layout()

    def _layout(self):
        y = self.START_Y
        for gname, items in BUILD_GROUPS:
            self.group_labels.append((gname, self.START_X, y - 24))
            x = self.START_X
            for btype in items:
                self.buttons.append({"type": btype, "rect": (x, y, self.BTN_W, self.BTN_H)})
                x += self.BTN_W + self.GAP_X
            y += self.BTN_H + self.GAP_Y
        self.content_height = y
        viewport_h = self.VIEWPORT_BOTTOM - self.VIEWPORT_TOP
        self.max_scroll = max(0.0, self.content_height - viewport_h)

    def scroll(self, direction):
        """direction>0이면 위로(마우스 휠 위), <0이면 아래로 스크롤."""
        self.scroll_offset -= direction * self.SCROLL_STEP
        self.scroll_offset = max(0.0, min(self.max_scroll, self.scroll_offset))

    def handle_click(self, pos):
        """클릭 좌표(pygame 좌상단 기준)가 어느 버튼 위인지 판정해 건물 타입을 반환."""
        mx, my = pos
        if not (self.VIEWPORT_TOP <= my <= self.VIEWPORT_BOTTOM):
            return None  # 뷰포트 바깥(안내 문구 영역 등) 클릭은 무시
        content_y = my + self.scroll_offset
        for btn in self.buttons:
            x, y, w, h = btn["rect"]
            if x <= mx <= x + w and y <= content_y <= y + h:
                return btn["type"]
        return None

    def handle_right_click(self, pos):
        """우클릭한 버튼의 상세 정보(재료/전력/설명) 패널을 열거나, 같은 버튼을 다시
        우클릭하면 닫는다. 히트박스 판정은 handle_click과 동일하게 재사용한다."""
        btype = self.handle_click(pos)
        if btype is not None:
            self.detail_btype = None if self.detail_btype == btype else btype

    def draw(self, selected, money):
        _begin_ortho_overlay()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # 화면 전체를 살짝 어둡게 덮어서 메뉴가 열렸음을 표시
        draw_rect_2d(0, 0, WIDTH, HEIGHT, (0.0, 0.0, 0.0), alpha=0.55)

        vt, vb = self.VIEWPORT_TOP, self.VIEWPORT_BOTTOM

        for gname, gx, gy_ in self.group_labels:
            vy = gy_ - self.scroll_offset
            if vt - 24 <= vy <= vb:
                blit_text(self.font, gname, gx, vy, (255, 230, 150))

        mouse_pos = pygame.mouse.get_pos()
        for btn in self.buttons:
            x, y, w, h = btn["rect"]
            vy = y - self.scroll_offset
            if vy + h < vt or vy > vb:
                continue  # 뷰포트 밖 -> 그리지 않음(스크롤로 안 보이는 버튼)
            btype = btn["type"]
            hovered = (x <= mouse_pos[0] <= x + w and vy <= mouse_pos[1] <= vy + h
                       and vt <= mouse_pos[1] <= vb)
            is_selected = (btype == selected)
            is_detail = (btype == self.detail_btype)
            afford = money >= BUILD_COST[btype]
            color = BUILD_COLOR[btype]

            draw_rect_2d(x, vy, w, h, color, alpha=(0.95 if (hovered or is_selected) else 0.65))
            if is_selected or hovered:
                glColor3f(1, 1, 1)
                draw_rect_outline_2d(x, vy, w, h, width=3.0 if is_selected else 2.0)
            if is_detail:
                glColor3f(0.4, 0.85, 1.0)  # 우클릭으로 상세 정보를 열어둔 버튼은 하늘색 테두리로 표시
                draw_rect_outline_2d(x, vy, w, h, width=2.5)

            text_color = (255, 255, 255) if afford else (255, 130, 130)
            blit_text(self.small, BUILD_LABEL[btype], x + 8, vy + 8, text_color)
            blit_text(self.small, f"${BUILD_COST[btype]}", x + 8, vy + h - 22, text_color)

        # 스크롤 가능함을 보여주는 세로 스크롤바 (내용이 뷰포트보다 클 때만)
        if self.max_scroll > 0:
            bar_x = WIDTH - 30
            bar_h = vb - vt
            draw_rect_2d(bar_x, vt, 8, bar_h, (0.3, 0.3, 0.3), alpha=0.6)
            thumb_h = max(30.0, bar_h * (bar_h / self.content_height))
            thumb_y = vt + (bar_h - thumb_h) * (self.scroll_offset / self.max_scroll)
            draw_rect_2d(bar_x, thumb_y, 8, thumb_h, (0.85, 0.85, 0.85), alpha=0.9)

        blit_text(self.small, "클릭해서 건물 선택 · 우클릭해서 재료/전력/설명 보기 · "
                  "마우스 휠로 스크롤 · B 또는 ESC 로 메뉴 닫기",
                  self.START_X, HEIGHT - 40, (230, 230, 230))

        if self.detail_btype is not None:
            self._draw_detail_panel(self.detail_btype)

        glDisable(GL_BLEND)
        _end_ortho_overlay()

    def _wrap_line(self, text, max_width_px):
        """text를 self.small 폰트 기준 실제 픽셀 폭(max_width_px)에 맞춰 여러 줄로 나눈다.
        한글은 단어 사이 공백이 안 나오는 경우가 많아 단어 단위 대신 글자 단위로 채워나간다."""
        if self.small.size(text)[0] <= max_width_px:
            return [text]
        lines, cur = [], ""
        for ch in text:
            trial = cur + ch
            if cur and self.small.size(trial)[0] > max_width_px:
                lines.append(cur)
                cur = ch
            else:
                cur = trial
        if cur:
            lines.append(cur)
        return lines

    def _draw_detail_panel(self, btype):
        """우클릭으로 연 건물의 재료/전력/설명 패널을 화면 오른쪽 고정 위치에 그린다
        (스크롤 위치와 무관하게 항상 같은 자리에 뜬다)."""
        pad = 12
        line_h = 20
        panel_w = 360
        panel_x = WIDTH - panel_w - 20
        panel_y = self.VIEWPORT_TOP

        # 실제 렌더링할 줄 수를 먼저 확정해야 패널 높이를 정확히 계산할 수 있으므로,
        # 줄바꿈된 결과를 (텍스트, 원래 줄이 제목(0번째)인지)로 미리 펼쳐 놓는다.
        rows = []
        for i, line in enumerate(build_menu_info(btype)):
            for sub in self._wrap_line(line, panel_w - pad * 2):
                rows.append((sub, i == 0))

        panel_h = len(rows) * line_h + pad * 2
        draw_rect_2d(panel_x, panel_y, panel_w, panel_h, (0.05, 0.05, 0.08), alpha=0.90)
        glColor3f(0.4, 0.85, 1.0)
        draw_rect_outline_2d(panel_x, panel_y, panel_w, panel_h, width=2.0)

        for i, (sub, is_title) in enumerate(rows):
            text_color = (255, 230, 140) if is_title else (225, 225, 230)
            blit_text(self.small, sub, panel_x + pad, panel_y + pad + i * line_h, text_color)


# ----------------------------------------------------------------------
# 아이템 필터 선택 메뉴 (item_filter를 조준한 상태에서 F로 열고, 텍스트 목록에서
# 액체/기체 또는 고체 중 통과시킬 아이템 하나를 클릭해서 고른다)
# ----------------------------------------------------------------------
class FilterMenu:
    ROW_W, ROW_H = 320, 26
    COL_LIQUID_X, COL_SOLID_X = 60, 420
    START_Y = 190
    CLEAR_Y = 130

    def __init__(self):
        self.font = pygame.font.SysFont("malgungothic,arial", 18)
        self.small = pygame.font.SysFont("malgungothic,arial", 15)
        self.liquids = sorted(LIQUID_ITEMS, key=lambda t: ITEM_LABEL.get(t, t))
        self.solids = sorted(set(ITEM_LABEL) - LIQUID_ITEMS, key=lambda t: ITEM_LABEL.get(t, t))
        self.rows = []   # [((x, y, w, h), item_type_or_None)] - None은 "필터 해제"
        self._layout()

    def _layout(self):
        self.rows = [((self.COL_LIQUID_X, self.CLEAR_Y, self.ROW_W * 2 + 40, self.ROW_H), None)]
        y = self.START_Y
        for t in self.liquids:
            self.rows.append(((self.COL_LIQUID_X, y, self.ROW_W, self.ROW_H), t))
            y += self.ROW_H
        y = self.START_Y
        for t in self.solids:
            self.rows.append(((self.COL_SOLID_X, y, self.ROW_W, self.ROW_H), t))
            y += self.ROW_H

    def handle_click(self, pos):
        """클릭한 칸의 아이템 타입을 반환. "필터 해제" 칸이면 "clear", 빈 곳이면 None."""
        mx, my = pos
        for (x, y, w, h), item_type in self.rows:
            if x <= mx <= x + w and y <= my <= y + h:
                return "clear" if item_type is None else item_type
        return None

    def draw(self, current_filter, title="필터로 통과시킬 아이템 선택", close_key="F"):
        _begin_ortho_overlay()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        draw_rect_2d(0, 0, WIDTH, HEIGHT, (0.0, 0.0, 0.0), alpha=0.68)
        blit_text(self.font, title, self.COL_LIQUID_X, 70, (255, 230, 150))
        blit_text(self.font, "액체 / 기체", self.COL_LIQUID_X, self.START_Y - 30, (150, 210, 255))
        blit_text(self.font, "고체", self.COL_SOLID_X, self.START_Y - 30, (230, 200, 150))

        mouse_pos = pygame.mouse.get_pos()
        for (x, y, w, h), item_type in self.rows:
            hovered = x <= mouse_pos[0] <= x + w and y <= mouse_pos[1] <= y + h
            is_selected = (item_type == current_filter)
            if item_type is None:
                bg_color = (0.35, 0.35, 0.38)
                label = "— 필터 해제 (전부 통과) —"
            else:
                bg_color = ITEM_COLOR.get(item_type, (0.5, 0.5, 0.5))
                label = ITEM_LABEL.get(item_type, item_type)

            draw_rect_2d(x, y, w, h, bg_color, alpha=(0.95 if (hovered or is_selected) else 0.55))
            if hovered or is_selected:
                glColor3f(1, 1, 1)
                draw_rect_outline_2d(x, y, w, h, width=3.0 if is_selected else 1.5)
            blit_text(self.small, label, x + 8, y + 5, (255, 255, 255))

        blit_text(self.small, f"클릭해서 선택 · {close_key} 또는 ESC 로 닫기",
                  self.COL_LIQUID_X, HEIGHT - 40, (230, 230, 230))

        glDisable(GL_BLEND)
        _end_ortho_overlay()


# ----------------------------------------------------------------------
# 월드 상태
# ----------------------------------------------------------------------
class World:
    def __init__(self):
        self.buildings = {}    # (gx,gz) -> dict
        self.items = []        # [{"x","z","gx","gz","type"}]
        self.drones = []       # [{"sx","sz","tx","tz","to","item","progress"}] - 비행 중인 드론
        # 코어 창고: 아이템 종류 -> 개수. 코어를 여러 개 지어도 이 창고 하나를 같이 쓴다
        # (Mindustry의 코어처럼 어느 코어에 넣든 같은 저장고에 쌓이도록).
        self.core_storage = {}
        self.money = 30000.0
        self.pollution = 0.0
        self.power_supply = 0.0
        self.power_draw = 0.0
        self.power_efficiency = 1.0
        self.building_efficiency = {}   # (gx,gz) -> 0~1, 와이어 연결 그룹별 실제 가동률
        self.building_flow = {}         # (gx,gz) -> 소속 전력망의 순 발전량(공급-수요), 전력 속도 카운터 표시용
        self.research_points = 0.0
        self.research_bonus = 1.0   # RP로 얻는 전 건물 공통 가동률 배수
        self.anim_time = 0.0   # 기계 애니메이션(드릴 상하운동 등)에 쓰는 누적 시간

    def add_building(self, gx, gz, btype, facing_dir):
        cost = BUILD_COST[btype]
        if self.money < cost or (gx, gz) in self.buildings:
            return False
        self.buildings[(gx, gz)] = {
            "type": btype, "dir": DIRS[facing_dir], "timer": 0.0,
            "processing_item": None, "process_timer": 0.0,
            "fuel": 0.0,     # thermal_plant 전용: 남은 연료(초)
            "buffer": {},    # MULTI_RECIPES 건물 전용: 모아둔 재료 개수
            "charge": 0.0,   # POWER_STORAGE(배터리류) 전용: 현재 저장된 전력량
            "filter_item": None,  # item_filter 전용: F로 선택한, 통과시킬 아이템 종류(None=전부 통과)
            "drone_item": None,   # drone_transporter/drone_payload 전용: G로 선택한 아이템 종류
            "payload_count": 0,   # drone_payload 전용: 드론이 배달했지만 아직 안 내보낸 재고 개수
            "node_level": 2,      # data_power_node 전용: T로 순환하는 출력 단계(1=저출력,2=표준,3=고출력)
            "drill_depth": 1,     # mineshaft_drill 전용: T로 순환하는 채굴 깊이(1=얕음~4=매우 깊음)
            "drill_head": None,   # mineshaft_drill 전용: 현재 장착된 드릴 헤드 종류(없으면 None)
            "drill_head_durability": 0.0,  # mineshaft_drill 전용: 장착된 헤드의 남은 내구도
            "oil_boost": 0,       # mineshaft_drill 전용: 머신오일 효과가 남은 사이클 수
            "dynamite_boost": 0,  # mineshaft_drill 전용: 다이너마이트 효과가 남은 사이클 수
            "dist_index": 0,      # 분배기 전용: 다음에 내보낼 출구 번호(순환)
        }
        self.money -= cost
        return True

    def remove_building(self, gx, gz):
        if (gx, gz) in self.buildings:
            del self.buildings[(gx, gz)]

    def _compute_building_efficiency(self, dt):
        """와이어(및 화력발전소/발전기/소비 건물/변압기/배터리 자체)로 4방향 인접 연결되거나
        변압기끼리 무선으로 이어진 그룹을 찾아, 그룹별로 전력 공급/수요를 계산한다.
        공급이 남으면 그룹 내 배터리를 충전하고, 부족하면 배터리를 방전해 메운다.
        그룹 밖(=전력망에 안 이어진) 소비 건물은 전력을 전혀 받지 못한다 (가동률 0)."""
        positions = [p for p, b in self.buildings.items() if b["type"] in POWER_NODE_TYPES]
        node_set = set(positions)
        parent = {p: p for p in positions}

        def find(x):
            root = x
            while parent[root] != root:
                root = parent[root]
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root

        for (gx, gz) in positions:
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (gx + dx, gz + dz)
                if nb in node_set:
                    ra, rb = find((gx, gz)), find(nb)
                    if ra != rb:
                        parent[ra] = rb

        # 변압기끼리는 인접하지 않아도 TRANSFORMER_RANGE 격자 칸 이내면 무선으로 전력망을 이어준다.
        transformers = [p for p in positions if self.buildings[p]["type"] == "transformer"]
        for i in range(len(transformers)):
            ax, az = transformers[i]
            for j in range(i + 1, len(transformers)):
                bx, bz = transformers[j]
                if max(abs(ax - bx), abs(az - bz)) <= TRANSFORMER_RANGE:
                    ra, rb = find(transformers[i]), find(transformers[j])
                    if ra != rb:
                        parent[ra] = rb

        supply_by_root, draw_by_root = {}, {}
        battery_positions_by_root = {}
        for pos in positions:
            b = self.buildings[pos]
            t = b["type"]
            root = find(pos)
            s = POWER_SUPPLY.get(t, 0.0)
            if t in FUEL_BURNERS and b["fuel"] > 0.0:
                s = get_burner_stats(self, pos)["power"]
            d = POWER_DRAW.get(t, 0.0)
            supply_by_root[root] = supply_by_root.get(root, 0.0) + s
            draw_by_root[root] = draw_by_root.get(root, 0.0) + d
            if t in POWER_STORAGE:
                battery_positions_by_root.setdefault(root, []).append(pos)

        eff_by_root, flow_by_root = {}, {}
        for root in set(supply_by_root) | set(draw_by_root) | set(battery_positions_by_root):
            s, d = supply_by_root.get(root, 0.0), draw_by_root.get(root, 0.0)
            batt_positions = battery_positions_by_root.get(root, [])
            net = s - d
            flow_by_root[root] = net

            if net >= 0.0:
                # 여유 전력은 그룹 내 배터리를 남은 용량에 비례해 충전한다.
                room_by_pos = {p: POWER_STORAGE[self.buildings[p]["type"]] - self.buildings[p]["charge"]
                               for p in batt_positions}
                total_room = sum(room_by_pos.values())
                if total_room > 0.0:
                    add = min(net * dt, total_room)
                    for p, room in room_by_pos.items():
                        if room > 0.0:
                            self.buildings[p]["charge"] += add * (room / total_room)
                eff_by_root[root] = 1.0
            else:
                # 부족한 만큼 배터리에 저장된 전력을 남은 잔량에 비례해 방전한다.
                deficit = -net
                charge_by_pos = {p: self.buildings[p]["charge"] for p in batt_positions}
                total_charge = sum(charge_by_pos.values())
                used = 0.0
                if total_charge > 0.0:
                    used = min(deficit * dt, total_charge)
                    for p, charge in charge_by_pos.items():
                        if charge > 0.0:
                            self.buildings[p]["charge"] -= used * (charge / total_charge)
                satisfied = s + (used / dt if dt > 0.0 else 0.0)
                eff_by_root[root] = 1.0 if d <= 0.0 else max(0.0, min(1.0, satisfied / d))

        self.building_flow = {pos: flow_by_root[find(pos)] for pos in positions}
        return {pos: eff_by_root[find(pos)] for pos in positions}

    def _update_power_and_pollution(self, dt):
        supply = draw = 0.0
        coal_count = oil_gen_count = extractor_count = 0
        scrubber_count = research_count = 0
        burner_pollution = 0.0
        firebox_active_count = 0

        for pos, b in self.buildings.items():
            t = b["type"]
            if t in POWER_SUPPLY:
                supply += POWER_SUPPLY[t]
                if t == "coal_gen":
                    coal_count += 1
                elif t == "oil_gen":
                    oil_gen_count += 1
            if t in POWER_DRAW:
                draw += POWER_DRAW[t]
                if t in DEPOSIT_OUTPUT:  # miner, oil_pump 등 채굴류
                    extractor_count += 1
                elif t == "scrubber":
                    scrubber_count += 1
                elif t == "research":
                    research_count += 1
            if t in FUEL_BURNERS and b["fuel"] > 0.0:
                burner = get_burner_stats(self, pos)
                supply += burner["power"]
                burner_pollution += burner["pollution"]
            if t == "firebox" and b["processing_item"] is not None:
                firebox_active_count += 1  # 물을 석탄으로 데우는 동안 오염 발생

        # HUD에 보여줄 맵 전체 총합 (실제 가동은 아래 building_efficiency가 결정)
        self.power_supply = supply
        self.power_draw = draw
        self.power_efficiency = 1.0 if draw <= 0 else max(0.0, min(1.0, supply / draw))

        # 와이어로 실제 연결된 그룹 단위 가동률 (건물마다 다를 수 있음)
        eff = self._compute_building_efficiency(dt)
        # 연구 보너스는 전력 계산이 끝난 뒤에 곱한다. 전력이 모자라면 여전히 느려지지만,
        # RP를 모을수록 모든 건물이 그만큼 빨라진다(가동률이 100%를 넘을 수 있음).
        self.research_bonus = research_multiplier(self.research_points)
        self.building_efficiency = ({p: e * self.research_bonus for p, e in eff.items()}
                                     if self.research_bonus != 1.0 else eff)

        # 연료발전기(화력발전소/디젤발전기 등)는 실제로 태우는 동안에만 연료가 줄어듦 (전력망 효율과 무관)
        for b in self.buildings.values():
            if b["type"] in FUEL_BURNERS and b["fuel"] > 0.0:
                b["fuel"] = max(0.0, b["fuel"] - dt)

        self.pollution += (
            coal_count * COAL_POLLUTION_RATE
            + oil_gen_count * OIL_GEN_POLLUTION_RATE
            + extractor_count * MINER_POLLUTION_RATE
            + burner_pollution
            + firebox_active_count * FIREBOX_POLLUTION_RATE
        ) * dt
        scrubber_reduction = sum(
            SCRUBBER_POLLUTION_REDUCTION * self.building_efficiency.get(pos, 0.0)
            for pos, b in self.buildings.items() if b["type"] == "scrubber"
        )
        self.pollution -= (POLLUTION_DECAY + scrubber_reduction) * dt
        self.pollution = max(0.0, min(100.0, self.pollution))

        # 연구소: 와이어로 연결되어 실제 전력을 받는 만큼만 RP 생산
        for pos, b in self.buildings.items():
            if b["type"] == "research":
                eff = self.building_efficiency.get(pos, 0.0)
                self.research_points += RESEARCH_RP_RATE * dt * eff

    def _update_extractors(self, dt):
        """채굴기(광석)/오일 펌프(원유)/물 펌프/가스 추출기 공용 추출 로직. 부지 전체가 어떤
        광물이든 액체든 다 뽑을 수 있는 땅이라, 특정 광맥이 있어야 한다는 제약 없이 어디에
        설치하든 그 건물 고유의 자원을 바로 생산한다."""
        for (gx, gz), b in self.buildings.items():
            btype = b["type"]
            if btype not in DEPOSIT_OUTPUT:
                continue
            eff = self.building_efficiency.get((gx, gz), 0.0)
            b["timer"] += dt * eff
            interval = EXTRACT_INTERVAL[btype]
            if b["timer"] >= interval:
                b["timer"] = 0.0
                output_item = next(iter(DEPOSIT_OUTPUT[btype].values()))
                self.items.append({"x": gx * CELL, "z": gz * CELL,
                                    "gx": gx, "gz": gz, "type": output_item, "dir": b["dir"]})

    def _update_processors(self, dt):
        for (gx, gz), b in self.buildings.items():
            if b["type"] not in PROCESS_TIME:
                continue
            if b["processing_item"] is not None:
                eff = self.building_efficiency.get((gx, gz), 0.0)
                b["process_timer"] += dt * eff
                if b["process_timer"] >= PROCESS_TIME[b["type"]]:
                    out = b["processing_item"]
                    b["processing_item"] = None
                    b["process_timer"] = 0.0
                    out_list = out if isinstance(out, (list, tuple)) else [out]
                    for i, out_type in enumerate(out_list):
                        # 여러 종류를 동시에 산출할 때는 겹치지 않도록 살짝 옆으로 벌려서 스폰
                        spread = (i - (len(out_list) - 1) / 2.0) * 0.35
                        # source_pos: 이 아이템을 낳은 칸의 좌표. 폭발로처럼 산출물(목탄)이 같은
                        # 건물의 입력 종류(연료로도 쓰이는 목탄)와 겹치는 경우, 갓 나온 산출물이
                        # 같은 칸에서 자기 자신에게 다시 "재료"로 캡처되는 걸 막는 데 쓰인다.
                        self.items.append({"x": gx * CELL, "z": gz * CELL + spread,
                                            "gx": gx, "gz": gz, "type": out_type, "dir": b["dir"],
                                            "source_pos": (gx, gz)})

    def _update_mineshaft_drills(self, dt):
        """마인샤프트 드릴: 드릴 헤드가 장착되어 있고 그 헤드 등급이 현재 깊이를 감당할 수
        있을 때만 채굴한다. 캘 때마다 헤드 내구도가 줄고, 0이 되면 헤드가 소모되어 다시
        넣어줘야 한다. 다이너마이트/머신오일은 각각 주기를 앞당기고(속도), 머신오일은
        추가로 산출량을 늘리는 대신 내구도를 더 깎는다."""
        for (gx, gz), b in self.buildings.items():
            if b["type"] != "mineshaft_drill":
                continue
            head = b.get("drill_head")
            if head is None:
                continue
            eff = self.building_efficiency.get((gx, gz), 0.0)
            if eff <= 0.0:
                continue
            oiled = b.get("oil_boost", 0) > 0
            dynamited = b.get("dynamite_boost", 0) > 0
            interval = MINESHAFT_BASE_INTERVAL
            if oiled:
                interval *= 0.5   # 머신오일: 2배속
            if dynamited:
                interval *= 0.5   # 다이너마이트: 채굴 주기를 앞당겨줌(원작의 "더 빨리 판다" 효과)
            b["timer"] += dt * eff
            if b["timer"] < interval:
                continue
            b["timer"] = 0.0
            depth = b.get("drill_depth", 1)
            if DRILL_HEAD_MIN_DEPTH[head] < depth:
                continue  # 헤드 등급이 이 깊이를 못 버팀 - 소모/생산 없이 그냥 대기

            wear = 1.0 + (OIL_WEAR_BONUS if oiled else 0.0)
            b["drill_head_durability"] -= wear
            if oiled:
                b["oil_boost"] -= 1
            if dynamited:
                b["dynamite_boost"] -= 1

            pool = DRILL_DEPTH_OUTPUTS[depth]
            types, weights = zip(*pool)
            output_item = random.choices(types, weights=weights)[0]
            self.items.append({"x": gx * CELL, "z": gz * CELL, "gx": gx, "gz": gz,
                                "type": output_item, "dir": b["dir"], "source_pos": (gx, gz)})
            if oiled and random.random() < OIL_YIELD_BONUS:
                # 머신오일: 산출량 +10% (확률적으로 한 개 더 나옴)
                self.items.append({"x": gx * CELL, "z": gz * CELL + 0.3, "gx": gx, "gz": gz,
                                    "type": output_item, "dir": b["dir"], "source_pos": (gx, gz)})

            if b["drill_head_durability"] <= 0.0:
                b["drill_head"] = None
                b["drill_head_durability"] = 0.0

    def _update_drone_transporters(self, dt):
        """드론 수송기: G로 지정한 아이템을 맵 어디서든(컨베이어 연결 없이) 찾아서, 같은 아이템을
        요청 중인 가장 가까운 드론 페이로드로 실어나를 드론을 주기적으로 출발시킨다."""
        for pos, b in self.buildings.items():
            if b["type"] != "drone_transporter":
                continue
            b["timer"] += dt
            if b["timer"] < DRONE_SCAN_INTERVAL or b["drone_item"] is None:
                continue
            b["timer"] = 0.0
            gx, gz = pos
            wanted = b["drone_item"]

            dest_pos, dest_dist = None, None
            for p2, b2 in self.buildings.items():
                if b2["type"] == "drone_payload" and b2.get("drone_item") == wanted:
                    d = max(abs(p2[0] - gx), abs(p2[1] - gz))
                    if d <= DRONE_RANGE and (dest_dist is None or d < dest_dist):
                        dest_pos, dest_dist = p2, d
            if dest_pos is None:
                continue  # 이 화물을 원하는 드론 페이로드가 범위 안에 없음

            best_idx, best_dist = None, None
            for i, it in enumerate(self.items):
                if it["type"] != wanted:
                    continue
                d = max(abs(it["gx"] - gx), abs(it["gz"] - gz))
                if d <= DRONE_RANGE and (best_dist is None or d < best_dist):
                    best_idx, best_dist = i, d
            if best_idx is None:
                continue  # 실어나를 화물이 범위 안에 없음

            picked = self.items.pop(best_idx)
            self.drones.append({
                "sx": gx * CELL, "sz": gz * CELL,
                "tx": dest_pos[0] * CELL, "tz": dest_pos[1] * CELL,
                "to": dest_pos, "item": picked["type"], "progress": 0.0,
            })

    def _update_drones(self, dt):
        """비행 중인 드론들을 출발지 -> 도착지로 이동시키고, 도착하면 드론 페이로드의 재고를 채운다."""
        alive = []
        for d in self.drones:
            dist = max(1e-6, math.hypot(d["tx"] - d["sx"], d["tz"] - d["sz"]))
            d["progress"] += (DRONE_FLIGHT_SPEED * dt) / dist
            if d["progress"] >= 1.0:
                dest = self.buildings.get(d["to"])
                if dest is not None and dest["type"] == "drone_payload":
                    dest["payload_count"] = dest.get("payload_count", 0) + 1
                continue
            alive.append(d)
        self.drones = alive

    def _update_drone_payloads(self, dt):
        """드론 페이로드: 드론이 배달해둔 재고를 일정 주기로 한 개씩, 컨베이어처럼 자기 dir
        방향으로 흘려보낸다 (이후 처리 흐름은 일반 아이템과 동일하게 _move_items가 담당)."""
        for (gx, gz), b in self.buildings.items():
            if b["type"] != "drone_payload":
                continue
            if b.get("payload_count", 0) <= 0 or b.get("drone_item") is None:
                continue
            b["timer"] += dt
            if b["timer"] >= DRONE_EMIT_INTERVAL:
                b["timer"] = 0.0
                b["payload_count"] -= 1
                self.items.append({"x": gx * CELL, "z": gz * CELL,
                                    "gx": gx, "gz": gz, "type": b["drone_item"], "dir": b["dir"]})

    def _try_capture_inputs(self):
        remaining = []
        for it in self.items:
            b = self.buildings.get((it["gx"], it["gz"]))
            captured = False
            if b is not None:
                dx = it["x"] - it["gx"] * CELL
                dz = it["z"] - it["gz"] * CELL
                close_enough = (dx * dx + dz * dz) ** 0.5 <= CAPTURE_RADIUS
                btype = b["type"]
                if btype in RECIPES and b["processing_item"] is None:
                    recipe = RECIPES[btype]
                    if it["type"] in recipe and close_enough:
                        # 열교환기도 다른 가공 건물(제련로 등)과 동일하게, 전력만 연결되어 있으면
                        # 바로 물을 고압 증기로 바꾼다 (예전에는 인접한 석탄 화력 발전소가 실제로
                        # 석탄을 태우는 중이어야만 작동하도록 했었는데, 이 숨은 조건이 무엇이 문제인지
                        # 알기 어려워 혼란을 줘서 제거함).
                        b["processing_item"] = recipe[it["type"]]
                        b["process_timer"] = 0.0
                        captured = True
                elif btype in MULTI_RECIPES and b["processing_item"] is None:
                    recipe = MULTI_RECIPES[btype]
                    needed = recipe["inputs"]
                    if it["type"] in needed and close_enough:
                        have = b["buffer"].get(it["type"], 0)
                        if have < needed[it["type"]]:
                            b["buffer"][it["type"]] = have + 1
                            captured = True
                            # 필요한 재료가 모두 모였으면 가공 시작 (재료 소비 후 타이머 리셋)
                            if all(b["buffer"].get(k, 0) >= v for k, v in needed.items()):
                                for k, v in needed.items():
                                    b["buffer"][k] -= v
                                b["processing_item"] = recipe["output"]
                                b["process_timer"] = 0.0
                elif btype == "blast_furnace" and b["processing_item"] is None:
                    # 갓 나온 산출물(목탄 등)이 같은 칸에서 자기 자신에게 다시 재료로
                    # 캡처되는 걸 막는다 (목탄은 산출물이면서 동시에 연료이기도 하므로).
                    is_own_output = it.get("source_pos") == (it["gx"], it["gz"])
                    if not is_own_output and close_enough:
                        if it["type"] in BLAST_FURNACE_PRIMARY:
                            cur_primary = b["buffer"].get("primary_item")
                            if (cur_primary is None or cur_primary == it["type"]) and b["buffer"].get("primary", 0) < 1:
                                b["buffer"]["primary_item"] = it["type"]
                                b["buffer"]["primary"] = 1
                                captured = True
                        elif it["type"] in FUEL_LIKE_ITEMS:
                            if b["buffer"].get("fuel", 0) < 1:
                                b["buffer"]["fuel"] = 1
                                captured = True
                        if b["buffer"].get("primary", 0) >= 1 and b["buffer"].get("fuel", 0) >= 1:
                            primary_item = b["buffer"]["primary_item"]
                            b["processing_item"] = BLAST_FURNACE_PRIMARY[primary_item]
                            b["process_timer"] = 0.0
                            b["buffer"] = {}
                elif btype in DYNAMIC_RECIPES and b["processing_item"] is None:
                    # 동적 레시피 건물(화학 반응기/산화실/스팀 크래커/플라스틱 정제소 등):
                    # 그 건물의 레시피 중 재료가 다 모인 걸 골라서 처리한다. 어떤 레시피에서도
                    # 안 쓰는 재료는 안 받고, 쓰는 재료도 필요한 개수까지만 받아서 버퍼가 막히지 않게 한다.
                    # 갓 나온 산출물이 같은 칸에서 다시 재료로 잡히는 것도 막는다.
                    is_own_output = it.get("source_pos") == (it["gx"], it["gz"])
                    limits = DYNAMIC_INPUT_MAX[btype]
                    if not is_own_output and it["type"] in limits and close_enough:
                        have = b["buffer"].get(it["type"], 0)
                        if have < limits[it["type"]]:
                            b["buffer"][it["type"]] = have + 1
                            captured = True
                            for recipe in DYNAMIC_RECIPES[btype]:
                                needed = recipe["inputs"]
                                if all(b["buffer"].get(k, 0) >= v for k, v in needed.items()):
                                    for k, v in needed.items():
                                        b["buffer"][k] -= v
                                    b["processing_item"] = recipe["output"]
                                    b["process_timer"] = 0.0
                                    break
                elif btype in FUEL_BURNERS and it["type"] == FUEL_BURNERS[btype]["fuel_item"] and close_enough:
                    b["fuel"] += get_burner_stats(self, (it["gx"], it["gz"]))["fuel_per_item"]
                    captured = True
                elif (btype == "gas_input_block"
                      and it["type"] == FUEL_BURNERS["gas_turbine"]["fuel_item"] and close_enough):
                    # 가스 인풋 블록: 파이프로 정제가스를 직접 받아, 같은 부품 무리로 이어진
                    # 가스터빈(들)에게 연료를 나눠 공급한다 (터빈이 하나도 안 이어져 있으면
                    # 캡처하지 않고 그대로 기다린다).
                    turbines, _ = _gas_turbine_cluster(self, (it["gx"], it["gz"]))
                    if turbines:
                        share = get_burner_stats(self, next(iter(turbines)))["fuel_per_item"] / len(turbines)
                        for tpos in turbines:
                            self.buildings[tpos]["fuel"] += share
                        captured = True
                elif (btype == "turbine_hp_stage"
                      and it["type"] == FUEL_BURNERS["modular_turbine"]["fuel_item"] and close_enough):
                    # 터빈 인풋(고압 터빈 단): 열교환기가 만든 고압 증기를 파이프로 직접 받아,
                    # 같은 부품 무리로 이어진 모듈러 터빈(들)에게 나눠 공급한다.
                    turbines, _ = _family_cluster(self, (it["gx"], it["gz"]),
                                                   MODULAR_TURBINE_FAMILY, "modular_turbine")
                    if turbines:
                        share = get_burner_stats(self, next(iter(turbines)))["fuel_per_item"] / len(turbines)
                        for tpos in turbines:
                            self.buildings[tpos]["fuel"] += share
                        captured = True
                elif btype == "core" and close_enough:
                    # 코어는 종류를 가리지 않고 전부 받아서 공용 창고에 쌓는다.
                    self.core_storage[it["type"]] = self.core_storage.get(it["type"], 0) + 1
                    captured = True
                elif btype == "mineshaft_drill" and close_enough:
                    if it["type"] in DRILL_HEAD_DURABILITY:
                        if b.get("drill_head") is None:
                            b["drill_head"] = it["type"]
                            b["drill_head_durability"] = float(DRILL_HEAD_DURABILITY[it["type"]])
                            captured = True
                    elif it["type"] == "acid":
                        if b.get("drill_head") is not None:
                            b["drill_head_durability"] = b.get("drill_head_durability", 0.0) + ACID_DURABILITY_BONUS
                            captured = True
                    elif it["type"] == "machine_oil":
                        b["oil_boost"] = OIL_BOOST_CYCLES
                        captured = True
                    elif it["type"] == "dynamite":
                        b["dynamite_boost"] = DYNAMITE_BOOST_CYCLES
                        captured = True
            if not captured:
                remaining.append(it)
        self.items = remaining

    def _move_items(self, dt):
        price_mult = max(0.2, 1.0 - self.pollution / 100.0)
        alive = []
        for it in self.items:
            b = self.buildings.get((it["gx"], it["gz"]))
            if b is None:
                continue  # 경로 이탈 -> 분실
            btype = b["type"]
            if btype == "depot":
                self.money += SELL_PRICE.get(it["type"], 2) * price_mult
                continue

            if btype == "core":
                # 코어에 올라온 아이템은 밖으로 흘려보내지 않고 칸 중심으로 빨아들인다.
                # (그냥 제자리에 세워두면 칸 가장자리로 들어온 아이템이 CAPTURE_RADIUS 밖에
                #  머물러서 영영 창고에 안 들어가고 굳어버린다.)
                cx, cz = it["gx"] * CELL, it["gz"] * CELL
                dx, dz = cx - it["x"], cz - it["z"]
                dist = (dx * dx + dz * dz) ** 0.5
                if dist > 1e-4:
                    step = min(ITEM_SPEED * dt, dist)
                    it["x"] += dx / dist * step
                    it["z"] += dz / dist * step
                alive.append(it)
                continue

            if btype in DISTRIBUTOR_TYPES:
                # 분배기: 칸 중심에 닿는 순간 다음 출구를 배정하고, 그 방향으로 내보낸다.
                # 한 아이템이 매 프레임 재배정되지 않도록 배정된 칸을 기록해둔다.
                if btype in PIPE_DISTRIBUTORS and it["type"] not in LIQUID_ITEMS:
                    continue                      # 고체는 파이프 분배기를 통과할 수 없음
                cell = (it["gx"], it["gz"])
                if it.get("dist_cell") != cell:
                    ox = it["x"] - cell[0] * CELL
                    oz = it["z"] - cell[1] * CELL
                    if (ox * ox + oz * oz) ** 0.5 <= CAPTURE_RADIUS:
                        outs = distributor_outputs(btype, b["dir"])
                        incoming = it.get("dir") or b["dir"]
                        reverse = (-incoming[0], -incoming[1])
                        usable = tuple(o for o in outs if o != reverse) or outs
                        idx = (b.get("dist_index", 0) + 1) % len(usable)
                        b["dist_index"] = idx
                        it["dir"] = usable[idx]
                        it["dist_cell"] = cell
                dx, dz = it["dir"]
                it["x"] += dx * ITEM_SPEED * dt
                it["z"] += dz * ITEM_SPEED * dt
                it["gx"] = round(it["x"] / CELL)
                it["gz"] = round(it["z"] / CELL)
                alive.append(it)
            elif btype in CONVEYOR_LIKE or btype in DEPOSIT_OUTPUT:
                dx, dz = b["dir"]
                it["dir"] = (dx, dz)   # 이 칸을 지나며 진행방향이 이 건물 방향으로 갱신됨 (턴)
                it["x"] += dx * ITEM_SPEED * dt
                it["z"] += dz * ITEM_SPEED * dt
                it["gx"] = round(it["x"] / CELL)
                it["gz"] = round(it["z"] / CELL)
                alive.append(it)
            elif btype in PIPE_LIKE:
                if it["type"] not in LIQUID_ITEMS:
                    continue  # 고체 아이템은 파이핑을 통과할 수 없음 (분실)
                dx, dz = b["dir"]
                it["dir"] = (dx, dz)
                it["x"] += dx * ITEM_SPEED * dt
                it["z"] += dz * ITEM_SPEED * dt
                it["gx"] = round(it["x"] / CELL)
                it["gz"] = round(it["z"] / CELL)
                alive.append(it)
            elif btype == "gas_input_block":
                # 정제가스는 여기 멈춰서 캡처(가스터빈에게 연료 전달)를 기다리고,
                # 그 외 아이템은 그냥 통과시킨다(파이프처럼).
                if it["type"] == FUEL_BURNERS["gas_turbine"]["fuel_item"]:
                    alive.append(it)
                    continue
                dx, dz = b["dir"]
                it["dir"] = (dx, dz)
                it["x"] += dx * ITEM_SPEED * dt
                it["z"] += dz * ITEM_SPEED * dt
                it["gx"] = round(it["x"] / CELL)
                it["gz"] = round(it["z"] / CELL)
                alive.append(it)
            elif btype == "turbine_hp_stage":
                # 터빈 인풋(고압 터빈 단): 고압 증기는 여기 멈춰서 캡처(모듈러 터빈에게 연료 전달)를
                # 기다리고, 그 외 아이템은 그냥 통과시킨다(파이프처럼).
                if it["type"] == FUEL_BURNERS["modular_turbine"]["fuel_item"]:
                    alive.append(it)
                    continue
                dx, dz = b["dir"]
                it["dir"] = (dx, dz)
                it["x"] += dx * ITEM_SPEED * dt
                it["z"] += dz * ITEM_SPEED * dt
                it["gx"] = round(it["x"] / CELL)
                it["gz"] = round(it["z"] / CELL)
                alive.append(it)
            elif btype == "mineshaft_drill":
                # 드릴 헤드/산/머신오일/다이너마이트는 여기 멈춰서 캡처를 기다리고,
                # 그 외(채굴된 산출물 등)는 건물 방향으로 흘려보낸다.
                is_own_output = it.get("source_pos") == (it["gx"], it["gz"])
                waiting_type = it["type"] in DRILL_HEAD_DURABILITY or it["type"] in ("acid", "machine_oil", "dynamite")
                if not is_own_output and waiting_type:
                    alive.append(it)
                else:
                    dx, dz = b["dir"]
                    it["dir"] = (dx, dz)
                    it["x"] += dx * ITEM_SPEED * dt
                    it["z"] += dz * ITEM_SPEED * dt
                    it["gx"] = round(it["x"] / CELL)
                    it["gz"] = round(it["z"] / CELL)
                    alive.append(it)
            elif btype == "item_filter":
                # 액체/고체 둘 다 받되, F로 지정해둔 종류(filter_item)와 다르면 여기서 걸러져 사라진다.
                # 아직 아무것도 선택하지 않았으면(None) 전부 그대로 통과시킨다.
                target = b.get("filter_item")
                if target is not None and it["type"] != target:
                    continue  # 필터에 안 맞는 아이템 -> 분실(걸러짐)
                dx, dz = b["dir"]
                it["dir"] = (dx, dz)
                it["x"] += dx * ITEM_SPEED * dt
                it["z"] += dz * ITEM_SPEED * dt
                it["gx"] = round(it["x"] / CELL)
                it["gz"] = round(it["z"] / CELL)
                alive.append(it)
            elif btype in CROSSROAD_TYPES:
                if btype == "pipe_crossroad" and it["type"] not in LIQUID_ITEMS:
                    continue  # 파이프 교차로는 액체/기체만 통과
                # 교차로는 건물의 dir을 무시하고, 아이템이 원래 갖고 있던 진행방향을 그대로 유지한다.
                # 그래야 서로 다른 방향의 두 흐름이 여기서 합쳐지지 않고 각자 직진해서 지나간다.
                dx, dz = it.get("dir", b["dir"])
                it["x"] += dx * ITEM_SPEED * dt
                it["z"] += dz * ITEM_SPEED * dt
                it["gx"] = round(it["x"] / CELL)
                it["gz"] = round(it["z"] / CELL)
                alive.append(it)
            elif btype in RECIPES:
                if it["type"] in RECIPES[btype]:
                    alive.append(it)  # 가공 대기 중인 원료 -> 다음 프레임에 캡처 시도
                else:
                    # 이미 가공되어 나온 완제품 -> 컨베이어처럼 건물의 방향으로 계속 흘려보냄
                    dx, dz = b["dir"]
                    it["dir"] = (dx, dz)
                    it["x"] += dx * ITEM_SPEED * dt
                    it["z"] += dz * ITEM_SPEED * dt
                    it["gx"] = round(it["x"] / CELL)
                    it["gz"] = round(it["z"] / CELL)
                    alive.append(it)
            elif btype in MULTI_RECIPES:
                if it["type"] in MULTI_RECIPES[btype]["inputs"]:
                    alive.append(it)  # 필요한 재료 중 하나 -> 대기하며 캡처 시도
                else:
                    # 산출물(또는 관계없는 아이템) -> 건물 방향으로 흘려보냄
                    dx, dz = b["dir"]
                    it["dir"] = (dx, dz)
                    it["x"] += dx * ITEM_SPEED * dt
                    it["z"] += dz * ITEM_SPEED * dt
                    it["gx"] = round(it["x"] / CELL)
                    it["gz"] = round(it["z"] / CELL)
                    alive.append(it)
            elif btype in DYNAMIC_RECIPES:
                # 동적 레시피 건물: 그 건물이 쓰는 재료면 대기시키고, 그 외(산출물 포함)는
                # 건물 방향으로 흘려보낸다. 산출물이 다시 재료로 잡히는 걸 막기 위해
                # 갓 나온 것인지(source_pos)도 함께 본다.
                is_own_output = it.get("source_pos") == (it["gx"], it["gz"])
                if not is_own_output and it["type"] in DYNAMIC_INPUT_MAX[btype]:
                    alive.append(it)  # 재료 대기 -> 다음 캡처 단계에서 시도
                else:
                    dx, dz = b["dir"]
                    it["dir"] = (dx, dz)
                    it["x"] += dx * ITEM_SPEED * dt
                    it["z"] += dz * ITEM_SPEED * dt
                    it["gx"] = round(it["x"] / CELL)
                    it["gz"] = round(it["z"] / CELL)
                    alive.append(it)
            elif btype == "blast_furnace":
                # 목탄은 산출물이면서 동시에 연료이기도 해서, 갓 나온 산출물인지(source_pos로 판별)
                # 먼저 확인해야 한다 - 갓 나온 산출물이면 대기시키지 않고 바로 건물 방향으로 흘려보낸다.
                is_own_output = it.get("source_pos") == (it["gx"], it["gz"])
                if not is_own_output and (it["type"] in BLAST_FURNACE_PRIMARY or it["type"] in FUEL_LIKE_ITEMS):
                    alive.append(it)  # 재료/연료 대기 -> 다음 캡처 단계에서 시도
                else:
                    dx, dz = b["dir"]
                    it["dir"] = (dx, dz)
                    it["x"] += dx * ITEM_SPEED * dt
                    it["z"] += dz * ITEM_SPEED * dt
                    it["gx"] = round(it["x"] / CELL)
                    it["gz"] = round(it["z"] / CELL)
                    alive.append(it)
            elif btype in FUEL_BURNERS:
                if it["type"] == FUEL_BURNERS[btype]["fuel_item"]:
                    alive.append(it)  # 연료 투입 대기 -> 다음 캡처 단계에서 소모됨
                else:
                    # 연료가 아닌 아이템은 그냥 통과시켜 다른 곳으로 흘려보냄
                    dx, dz = b["dir"]
                    it["dir"] = (dx, dz)
                    it["x"] += dx * ITEM_SPEED * dt
                    it["z"] += dz * ITEM_SPEED * dt
                    it["gx"] = round(it["x"] / CELL)
                    it["gz"] = round(it["z"] / CELL)
                    alive.append(it)
            else:  # solar / coal_gen / scrubber / research 등 위에 올라간 경우 -> 분실
                continue
        self.items = alive

    def update(self, dt):
        self.anim_time += dt
        self._update_power_and_pollution(dt)
        self._update_extractors(dt)
        self._update_processors(dt)
        self._update_mineshaft_drills(dt)
        self._update_drone_transporters(dt)
        self._update_drones(dt)
        self._update_drone_payloads(dt)
        self._move_items(dt)
        self._try_capture_inputs()

    def draw(self, cam_x=None, cam_z=None):
        # 같은 프레임 안에서 형상이 같은 건물끼리 디스플레이 리스트를 공유하도록 프레임 시작을 알린다.
        begin_model_frame(self.anim_time)
        # 카메라 위치를 받으면 멀리 있는 건물은 아예 건너뛴다(거리 컬링).
        cull2 = (DRAW_DISTANCE * CELL) ** 2 if cam_x is not None else None
        dir_relevant = {"conveyor", "wire", "pipe",
                         "coal_miner", "copper_miner", "iron_miner",
                         "lead_miner", "sand_miner", "wood_cutter", "blast_furnace",
                         "oil_pump", "furnace", "press",
                         "refinery", "chem_plant", "molder", "thermal_plant",
                         "silicon_refiner", "alloy_furnace", "circuit_assembler",
                         "assembly_plant", "battery_plant", "water_pump", "water_treatment",
                         "oil_classifier", "diesel_refiner", "filter", "diesel_gen",
                         "firebox", "boiler", "turbine",
                         "conveyor_3way", "conveyor_4way", "pipe_3way", "pipe_4way",
                         "gas_extractor", "condenser", "gas_refiner", "gas_turbine", "item_filter",
                         "drone_payload", "lathe", "fragment_processor", "mineshaft_drill", "ore_refiner",
                         "heavy_oil_separator", "oxidation_chamber", "chemical_reactor",
                         "electrolyzer", "air_separator", "steam_cracker", "plastic_refinery"}
        for (gx, gz), b in self.buildings.items():
            wx, wz = gx * CELL, gz * CELL
            if cull2 is not None:
                ddx, ddz = wx - cam_x, wz - cam_z
                if ddx * ddx + ddz * ddz > cull2:
                    continue        # 시야 밖으로 충분히 먼 건물은 그리지 않는다
            color = BUILD_COLOR[b["type"]]
            t = b["type"]

            # 전력을 쓰는 건물은 실제로 가동률>0일 때만 애니메이션 재생, 그 외(컨베이어 등)는 항상 재생
            if t in POWER_DRAW:
                active = self.building_efficiency.get((gx, gz), 0.0) > 0.01
            else:
                active = True

            gauge = None
            if t == "power_meter":
                gauge = self.building_flow.get((gx, gz), 0.0)
            elif t in POWER_STORAGE:
                gauge = b["charge"] / POWER_STORAGE[t]
            elif t == "data_power_node":
                gauge = b.get("node_level", 2)  # 1~3 - 표시등 개수로 출력 단계를 보여줌
            elif t == "mineshaft_drill":
                gauge = b.get("drill_depth", 1)  # 1~4 - 드릴이 얼마나 깊이 내려가 있는지 표시

            connects = None
            if t == "pipe":
                connects = [(dx, dz) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
                            if self.buildings.get((gx + dx, gz + dz), {}).get("type") in PIPE_CONNECTABLE]

            filter_color = None
            if t == "item_filter":
                filter_color = ITEM_COLOR.get(b.get("filter_item"))
            elif t in DRONE_UI_TYPES:
                filter_color = ITEM_COLOR.get(b.get("drone_item"))
            elif t == "mineshaft_drill":
                filter_color = ITEM_COLOR.get(b.get("drill_head"))  # 장착된 드릴 헤드 색 (없으면 None)

            draw_building_model_batched(t, wx, wz, color, DIR_TO_ANGLE.get(b["dir"], 0.0),
                                         self.anim_time, active, gauge, connects, filter_color)

            # 가공 중이면 위에 맥동하는(pulse) 작은 표시 큐브 (여러 종류를 동시 산출하는 경우 첫 산출물 색 사용)
            if b.get("processing_item"):
                proc = b["processing_item"]
                proc_color = ITEM_COLOR.get(proc[0] if isinstance(proc, (list, tuple)) else proc, (1, 1, 0))
                pulse = 0.24 + 0.10 * abs(math.sin(self.anim_time * 6.0))
                draw_cube(wx, 1.5, wz, pulse, pulse, pulse, proc_color)
            # 드론 페이로드: 드론이 배달해서 아직 안 내보낸 재고가 있으면 맥동하는 표시 큐브
            if t == "drone_payload" and b.get("payload_count", 0) > 0:
                stock_color = ITEM_COLOR.get(b.get("drone_item"), (1.0, 1.0, 0.2))
                pulse = 0.20 + 0.08 * abs(math.sin(self.anim_time * 5.0))
                draw_cube(wx, 1.3, wz, pulse, pulse, pulse, stock_color)
            # 연료발전기(화력발전소/디젤발전기 등) 연료 게이지 (연료가 남아있을 때 노란 큐브 표시)
            if t in FUEL_BURNERS and b.get("fuel", 0.0) > 0.0:
                fuel_full = get_burner_stats(self, (gx, gz))["fuel_per_item"]
                fuel_gauge = max(0.15, min(0.6, b["fuel"] / fuel_full * 0.6))
                draw_cube(wx, 1.9, wz, fuel_gauge, 0.2, fuel_gauge, (0.95, 0.85, 0.20))
            # 출력 방향이 의미 있는 건물은 바닥에 화살표로 방향 표시
            if t in dir_relevant:
                dx, dz = b["dir"]
                draw_ground_arrow(wx, wz, dx, dz, CELL * 0.32, (1.0, 1.0, 0.4))

        # 핵심 건물 + 인접 부품 구조(가스터빈/석탄 화력 발전소/모듈러 터빈)는 부품군끼리
        # 인접해 있으면 연결관/케이블로 이어진 것처럼 표시한다.
        conduit_pulse = 0.5 + 0.5 * abs(math.sin(self.anim_time * 2.5))
        family_conduit_colors = {
            "gas_turbine": (0.45, 0.75 * conduit_pulse + 0.15, 0.55),
            "coal_power_plant": (0.75 * conduit_pulse + 0.15, 0.45, 0.20),
            "modular_turbine": (0.35, 0.55, 0.85 * conduit_pulse + 0.15),
        }
        for (gx, gz), b in self.buildings.items():
            family, conduit_color = None, None
            for core_type, (fam, _) in FAMILY_PART_BONUS.items():
                if b["type"] in fam:
                    family = fam
                    conduit_color = family_conduit_colors[core_type]
                    break
            if family is None:
                continue
            wx, wz = gx * CELL, gz * CELL
            for dx, dz in ((1, 0), (0, 1)):  # 동/남쪽만 검사해서 같은 쌍을 두 번 그리지 않음
                nb = self.buildings.get((gx + dx, gz + dz))
                if nb is not None and nb["type"] in family:
                    nwx, nwz = (gx + dx) * CELL, (gz + dz) * CELL
                    mx, mz = (wx + nwx) / 2.0, (wz + nwz) / 2.0
                    if dx:
                        draw_cube(mx, 0.85, mz, CELL, 0.09, 0.09, conduit_color)
                    else:
                        draw_cube(mx, 0.85, mz, 0.09, 0.09, CELL, conduit_color)
                    draw_cube(mx, 0.85, mz, 0.16, 0.16, 0.16, (0.25, 0.25, 0.28))  # 이음매 표시

        for it in self.items:
            color = ITEM_COLOR.get(it["type"], (0.9, 0.9, 0.2))
            draw_cube(it["x"], 0.55, it["z"], 0.35, 0.35, 0.35, color)

        # 비행 중인 드론: 출발-도착 사이를 직선으로 이동하며, 높이는 사인 곡선으로 뜨고 내려앉는다.
        for d in self.drones:
            t = min(1.0, d["progress"])
            x = d["sx"] + (d["tx"] - d["sx"]) * t
            z = d["sz"] + (d["tz"] - d["sz"]) * t
            y = 1.2 + DRONE_LIFT_HEIGHT * math.sin(math.pi * t)
            draw_cube(x, y, z, 0.32, 0.14, 0.32, (0.75, 0.78, 0.82))
            draw_cube(x, y + 0.12, z, 0.10, 0.10, 0.10, (0.20, 0.55, 0.90))
            item_color = ITEM_COLOR.get(d["item"], (0.9, 0.9, 0.2))
            draw_cube(x, y - 0.16, z, 0.18, 0.14, 0.18, item_color)


def draw_ground(world):
    clean = (0.30, 0.62, 0.30)
    dirty = (0.42, 0.38, 0.32)
    t = world.pollution / 100.0
    r = clean[0] + (dirty[0] - clean[0]) * t
    g = clean[1] + (dirty[1] - clean[1]) * t
    b = clean[2] + (dirty[2] - clean[2]) * t

    ext = GRID_RANGE * CELL
    glColor3f(r, g, b)
    glBegin(GL_QUADS)
    glVertex3f(-ext, 0, -ext); glVertex3f(ext, 0, -ext)
    glVertex3f(ext, 0, ext); glVertex3f(-ext, 0, ext)
    glEnd()

    # 그리드 선 - 오염도에 따라 탁해지는 바닥색과 상관없이 항상 눈에 잘 띄는
    # 밝은 회백색으로 표시하고, 두께도 살짝 키워서 맵 전체(가장자리까지)에
    # 20칸 단위 격자가 뚜렷하게 보이도록 함
    glLineWidth(1.6)
    glColor3f(0.92, 0.94, 0.90)
    glBegin(GL_LINES)
    for i in range(-GRID_RANGE, GRID_RANGE + 1):
        p = i * CELL
        glVertex3f(p, 0.01, -ext); glVertex3f(p, 0.01, ext)
        glVertex3f(-ext, 0.01, p); glVertex3f(ext, 0.01, p)
    glEnd()


# ----------------------------------------------------------------------
# 메인
# ----------------------------------------------------------------------
def draw_placement_preview(gx, gz, valid):
    """조준 중인 그리드 칸을 반투명 사각형 + 테두리로 표시.
    valid=True면 초록(설치 가능), False면 빨강(이미 있음/자금 부족)."""
    color = (0.25, 0.95, 0.35) if valid else (0.95, 0.25, 0.25)
    x0, x1 = gx * CELL - CELL / 2, gx * CELL + CELL / 2
    z0, z1 = gz * CELL - CELL / 2, gz * CELL + CELL / 2

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glColor4f(color[0], color[1], color[2], 0.35)
    glBegin(GL_QUADS)
    glVertex3f(x0, 0.02, z0); glVertex3f(x1, 0.02, z0)
    glVertex3f(x1, 0.02, z1); glVertex3f(x0, 0.02, z1)
    glEnd()

    glColor4f(color[0], color[1], color[2], 0.95)
    glLineWidth(2.5)
    glBegin(GL_LINE_LOOP)
    glVertex3f(x0, 0.03, z0); glVertex3f(x1, 0.03, z0)
    glVertex3f(x1, 0.03, z1); glVertex3f(x0, 0.03, z1)
    glEnd()
    glDisable(GL_BLEND)


def main():
    pygame.init()
    pygame.display.set_caption("ALPHA PROJECT - Tier 1 Prototype")
    pygame.display.set_mode((WIDTH, HEIGHT), pygame.DOUBLEBUF | pygame.OPENGL)
    pygame.mouse.set_visible(False)
    pygame.event.set_grab(True)

    glEnable(GL_DEPTH_TEST)
    glEnable(GL_FOG)
    glFogi(GL_FOG_MODE, GL_EXP2)
    glMatrixMode(GL_PROJECTION)
    gl_perspective(70, WIDTH / HEIGHT, 0.1, 340.0)
    glMatrixMode(GL_MODELVIEW)

    clock = pygame.time.Clock()
    hud = Hud()
    menu = BuildMenu()
    filter_menu = FilterMenu()
    world = World()

    pos = [0.0, 1.6, 8.0]
    yaw, pitch = -90.0, 0.0
    selected = "coal_miner"
    menu_open = False
    filter_menu_open = False
    filter_target_pos = None   # F로 필터 메뉴를 열 당시 조준하고 있던 item_filter 칸
    drone_menu_open = False
    drone_menu_target_pos = None  # G로 드론 메뉴를 열 당시 조준하고 있던 drone_transporter/drone_payload 칸
    facing_offset = 0  # R키로 90도씩 누적되는 배치 방향 회전 오프셋 (0~3)

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        # 배치 목표 칸 계산: 피치(위아래 시선)는 무시하고 수평(yaw) 방향으로만
        # 앞쪽 지점을 잡아야, 위/아래를 볼 때 조준 칸이 그리드에서 어긋나지 않는다.
        aim_fx = math.cos(math.radians(yaw))
        aim_fz = math.sin(math.radians(yaw))
        target_gx = round((pos[0] + aim_fx * PLACE_DISTANCE) / CELL)
        target_gz = round((pos[2] + aim_fz * PLACE_DISTANCE) / CELL)
        target_facing = rotate_dir(snap_dir_from_yaw(yaw), facing_offset)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if menu_open:
                        menu_open = False
                        menu.detail_btype = None
                        pygame.mouse.set_visible(False)
                        pygame.event.set_grab(True)
                        pygame.mouse.get_rel()  # 메뉴 사용 중 쌓인 이동값 초기화 (시점 튐 방지)
                    elif filter_menu_open:
                        filter_menu_open = False
                        pygame.mouse.set_visible(False)
                        pygame.event.set_grab(True)
                        pygame.mouse.get_rel()
                    elif drone_menu_open:
                        drone_menu_open = False
                        pygame.mouse.set_visible(False)
                        pygame.event.set_grab(True)
                        pygame.mouse.get_rel()
                    else:
                        running = False
                elif event.key == pygame.K_b and not filter_menu_open and not drone_menu_open:
                    menu_open = not menu_open
                    pygame.mouse.set_visible(menu_open)
                    pygame.event.set_grab(not menu_open)
                    if not menu_open:
                        menu.detail_btype = None
                        pygame.mouse.get_rel()
                elif event.key == pygame.K_f and not menu_open and not drone_menu_open:
                    if filter_menu_open:
                        filter_menu_open = False
                        pygame.mouse.set_visible(False)
                        pygame.event.set_grab(True)
                        pygame.mouse.get_rel()
                    else:
                        target_b = world.buildings.get((target_gx, target_gz))
                        if target_b is not None and target_b["type"] == "item_filter":
                            filter_menu_open = True
                            filter_target_pos = (target_gx, target_gz)
                            pygame.mouse.set_visible(True)
                            pygame.event.set_grab(False)
                elif event.key == pygame.K_g and not menu_open and not filter_menu_open:
                    if drone_menu_open:
                        drone_menu_open = False
                        pygame.mouse.set_visible(False)
                        pygame.event.set_grab(True)
                        pygame.mouse.get_rel()
                    else:
                        target_b = world.buildings.get((target_gx, target_gz))
                        if target_b is not None and target_b["type"] in DRONE_UI_TYPES:
                            drone_menu_open = True
                            drone_menu_target_pos = (target_gx, target_gz)
                            pygame.mouse.set_visible(True)
                            pygame.event.set_grab(False)
                elif not menu_open and not filter_menu_open and not drone_menu_open and event.key == pygame.K_r:
                    facing_offset = (facing_offset + 1) % 4  # 조준 중인 미리보기 방향 90도 회전
                elif not menu_open and not filter_menu_open and not drone_menu_open and event.key == pygame.K_t:
                    # 데이터 파워 노드 조준 중이면 출력 단계(1저출력/2표준/3고출력)를 순환시킨다.
                    # 마인샤프트 드릴 조준 중이면 채굴 깊이(1얕음~4매우 깊음)를 순환시킨다.
                    target_b = world.buildings.get((target_gx, target_gz))
                    if target_b is not None and target_b["type"] == "data_power_node":
                        target_b["node_level"] = target_b.get("node_level", 2) % 3 + 1
                    elif target_b is not None and target_b["type"] == "mineshaft_drill":
                        target_b["drill_depth"] = target_b.get("drill_depth", 1) % 4 + 1
                elif not menu_open and not filter_menu_open and not drone_menu_open and event.key == pygame.K_2:
                    selected = "wire"
                elif not menu_open and not filter_menu_open and not drone_menu_open and event.key == pygame.K_3:
                    selected = "pipe"
                elif menu_open and event.key == pygame.K_UP:
                    menu.scroll(1)
                elif menu_open and event.key == pygame.K_DOWN:
                    menu.scroll(-1)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if menu_open:
                    if event.button == 1:
                        picked = menu.handle_click(event.pos)
                        if picked is not None:
                            selected = picked
                            menu_open = False
                            menu.detail_btype = None
                            pygame.mouse.set_visible(False)
                            pygame.event.set_grab(True)
                            pygame.mouse.get_rel()
                    elif event.button == 3:
                        menu.handle_right_click(event.pos)
                elif filter_menu_open:
                    if event.button == 1:
                        picked = filter_menu.handle_click(event.pos)
                        if picked is not None:
                            target_b = world.buildings.get(filter_target_pos)
                            if target_b is not None:
                                target_b["filter_item"] = None if picked == "clear" else picked
                            filter_menu_open = False
                            pygame.mouse.set_visible(False)
                            pygame.event.set_grab(True)
                            pygame.mouse.get_rel()
                elif drone_menu_open:
                    if event.button == 1:
                        picked = filter_menu.handle_click(event.pos)
                        if picked is not None:
                            target_b = world.buildings.get(drone_menu_target_pos)
                            if target_b is not None:
                                target_b["drone_item"] = None if picked == "clear" else picked
                            drone_menu_open = False
                            pygame.mouse.set_visible(False)
                            pygame.event.set_grab(True)
                            pygame.mouse.get_rel()
                else:
                    if event.button == 1:
                        world.add_building(target_gx, target_gz, selected, target_facing)
                    elif event.button == 3:
                        world.remove_building(target_gx, target_gz)
            elif event.type == pygame.MOUSEWHEEL:
                if menu_open:
                    menu.scroll(event.y)

        if not menu_open and not filter_menu_open and not drone_menu_open:
            mrel_x, mrel_y = pygame.mouse.get_rel()
            yaw += mrel_x * MOUSE_SENS
            pitch -= mrel_y * MOUSE_SENS
            pitch = max(-89.0, min(89.0, pitch))

            front_x = math.cos(math.radians(yaw))
            front_z = math.sin(math.radians(yaw))
            right_x = math.cos(math.radians(yaw - 90))
            right_z = math.sin(math.radians(yaw - 90))

            keys = pygame.key.get_pressed()
            speed = MOVE_SPEED * (SPRINT_MULT if keys[pygame.K_LSHIFT] else 1.0) * dt
            if keys[pygame.K_w]:
                pos[0] += front_x * speed; pos[2] += front_z * speed
            if keys[pygame.K_s]:
                pos[0] -= front_x * speed; pos[2] -= front_z * speed
            if keys[pygame.K_a]:
                pos[0] -= right_x * speed; pos[2] -= right_z * speed
            if keys[pygame.K_d]:
                pos[0] += right_x * speed; pos[2] += right_z * speed

            limit = GRID_RANGE * CELL - 0.5
            pos[0] = max(-limit, min(limit, pos[0]))
            pos[2] = max(-limit, min(limit, pos[2]))

        world.update(dt)

        t = world.pollution / 100.0
        sky = (0.53 + 0.15 * t, 0.80 - 0.35 * t, 0.92 - 0.45 * t)
        glClearColor(*sky, 1.0)
        glFogfv(GL_FOG_COLOR, (*sky, 1.0))
        glFogf(GL_FOG_DENSITY, 0.015 + t * 0.05)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        look_x = pos[0] + math.cos(math.radians(yaw)) * math.cos(math.radians(pitch))
        look_y = pos[1] + math.sin(math.radians(pitch))
        look_z = pos[2] + math.sin(math.radians(yaw)) * math.cos(math.radians(pitch))
        gl_look_at(pos[0], pos[1], pos[2], look_x, look_y, look_z, 0, 1, 0)

        draw_ground(world)
        world.draw(pos[0], pos[2])
        aim_info = None
        if not menu_open and not filter_menu_open and not drone_menu_open:
            valid = (target_gx, target_gz) not in world.buildings and world.money >= BUILD_COST[selected]
            draw_placement_preview(target_gx, target_gz, valid)
            fdx, fdz = DIRS[target_facing]
            draw_ground_arrow(target_gx * CELL, target_gz * CELL, fdx, fdz, CELL * 0.4, (1.0, 1.0, 1.0))
            aim_info = build_aim_info(world, target_gx, target_gz)
        hud.draw(world, selected, clock.get_fps(),
                 show_crosshair=not menu_open and not filter_menu_open and not drone_menu_open,
                 aim_info=aim_info)
        if menu_open:
            menu.draw(selected, world.money)
        elif filter_menu_open:
            current_filter = None
            target_b = world.buildings.get(filter_target_pos)
            if target_b is not None:
                current_filter = target_b.get("filter_item")
            filter_menu.draw(current_filter)
        elif drone_menu_open:
            current_drone_item = None
            target_b = world.buildings.get(drone_menu_target_pos)
            if target_b is not None:
                current_drone_item = target_b.get("drone_item")
            title = ("드론이 가져올 아이템 선택" if target_b is not None and target_b["type"] == "drone_transporter"
                     else "드론 페이로드가 받을 아이템 선택")
            filter_menu.draw(current_drone_item, title=title, close_key="G")

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()