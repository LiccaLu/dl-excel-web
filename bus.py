import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Ingrasys 外勞交通車費用計算",
    page_icon="🚌",
    layout="wide",
)

WEEKDAY_MAP = {
    "一": "平日", "二": "平日", "三": "平日", "四": "平日", "五": "平日",
    "六": "假日", "日": "假日",
}

DEFAULT_PRICE = {
    "平日": {
        "大巴": {False: 2200, True: 2500},
        "中巴": {False: 2000, True: 2200},
    },
    "假日": {
        "大巴": {False: 3500, True: 3800},
        "中巴": {False: 2800, True: 3000},
    },
}

TIME_LABELS = {
    "06:50": "日班去程",
    "18:00": "日班回程",
    "20:20": "日班回程",
    "21:10": "日班回程",
    "18:50": "夜班去程",
    "06:00": "夜班回程",
    "08:20": "夜班回程",
    "09:10": "夜班回程",
}

TIME_ORDER = list(TIME_LABELS.keys())

SAMPLE_TEXT = """1/3（六）
08:20 南青回大明 ：2大巴，1中巴
08:20 南青回興華：2大巴
08:20 南青回興業：1大巴
⭐️ 09:10 南青-大明-興華：1 中巴（停兩個點）

大明
1/3（六）
06:50 ：4大巴
18:00 ：1中巴
20:20 ：3大巴，1中巴
夜班
18:50 ：2大巴，1中巴

興華
1/3（六）
06:50 ：4大巴
18:00 ：1中巴
20:20 ：3大巴，1中巴
夜班
18:50 ：2大巴

興業
1/3（六）
06:50 ：1大巴
18:00 ：1中巴
20:20 ：1大巴
夜班
18:50 ：1大巴"""


@dataclass
class DetailRow:
    day_type: str
    shift: str
    time: str
    bus_type: str
    quantity: int
    two_stops: bool
    unit_price: int
    subtotal: int
    source: str


def normalize_text(value: str) -> str:
    return (
        value.replace("：", ":")
        .replace("，", ",")
        .replace("（", "(")
        .replace("）", ")")
        .replace("－", "-")
        .replace("—", "-")
    )


def detect_day_type(line: str) -> Optional[str]:
    match = re.search(r"[（(]([一二三四五六日])[）)]", line)
    return WEEKDAY_MAP.get(match.group(1)) if match else None


def is_two_stop_route(line: str) -> bool:
    normalized = normalize_text(line)
    explicit = any(token in normalized for token in ["停兩", "停2", "兩個點", "2個點"])
    route_part = normalized.split(":", 1)[0]
    # 路線文字中出現兩個以上連接點，例如「南青-大明-興華」。
    route_has_multiple_segments = route_part.count("-") >= 2
    return explicit or route_has_multiple_segments


def build_price_table() -> Dict[str, Dict[str, Dict[bool, int]]]:
    st.sidebar.header("單價設定")
    st.sidebar.caption("修改後重新按下「開始計算」即可套用。")

    prices: Dict[str, Dict[str, Dict[bool, int]]] = {
        day: {bus: {} for bus in ["大巴", "中巴"]} for day in ["平日", "假日"]
    }

    for day_type in ["平日", "假日"]:
        st.sidebar.subheader(day_type)
        for bus_type in ["大巴", "中巴"]:
            c1, c2 = st.sidebar.columns(2)
            prices[day_type][bus_type][False] = int(c1.number_input(
                f"{bus_type}停一站",
                min_value=0,
                value=DEFAULT_PRICE[day_type][bus_type][False],
                step=100,
                key=f"{day_type}_{bus_type}_normal",
            ))
            prices[day_type][bus_type][True] = int(c2.number_input(
                f"{bus_type}停兩站",
                min_value=0,
                value=DEFAULT_PRICE[day_type][bus_type][True],
                step=100,
                key=f"{day_type}_{bus_type}_two",
            ))
    return prices


def parse_transport_text(
    text: str,
    prices: Dict[str, Dict[str, Dict[bool, int]]],
) -> Tuple[List[DetailRow], List[str]]:
    rows: List[DetailRow] = []
    warnings: List[str] = []
    current_day_type: Optional[str] = None

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        detected = detect_day_type(line)
        if detected:
            current_day_type = detected
            continue

        normalized = normalize_text(line)
        time_match = re.search(r"(?<!\d)(\d{1,2}:\d{2})(?!\d)", normalized)
        buses = re.findall(r"(\d+)\s*(大巴|中巴)", normalized)

        if not time_match or not buses:
            continue

        time = time_match.group(1)
        if time not in TIME_LABELS:
            warnings.append(f"第 {line_no} 行的時間 {time} 尚未設定分類，已略過：{line}")
            continue

        if current_day_type is None:
            warnings.append(f"第 {line_no} 行前找不到星期資訊，已略過：{line}")
            continue

        two_stops = is_two_stop_route(normalized)
        for qty_text, bus_type in buses:
            quantity = int(qty_text)
            unit_price = prices[current_day_type][bus_type][two_stops]
            rows.append(DetailRow(
                day_type=current_day_type,
                shift=TIME_LABELS[time],
                time=time,
                bus_type=bus_type,
                quantity=quantity,
                two_stops=two_stops,
                unit_price=unit_price,
                subtotal=quantity * unit_price,
                source=line,
            ))

    return rows, warnings


def rows_to_dataframe(rows: List[DetailRow]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "平假日": r.day_type,
            "班別": r.shift,
            "時間": r.time,
            "車型": r.bus_type,
            "數量": r.quantity,
            "停兩站": "是" if r.two_stops else "否",
            "單價": r.unit_price,
            "小計": r.subtotal,
            "原始內容": r.source,
        }
        for r in rows
    ])


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df.groupby(["平假日", "班別", "時間", "車型"], as_index=False)["小計"]
        .sum()
        .rename(columns={"小計": "費用"})
    )
    summary["時間排序"] = summary["時間"].map({t: i for i, t in enumerate(TIME_ORDER)})
    summary["車型排序"] = summary["車型"].map({"大巴": 0, "中巴": 1})
    summary = summary.sort_values(["時間排序", "車型排序", "平假日"]).drop(
        columns=["時間排序", "車型排序"]
    )
    summary.insert(
        0,
        "項目",
        summary["平假日"] + summary["班別"] + summary["時間"] + summary["車型"],
    )
    return summary.reset_index(drop=True)


prices = build_price_table()

st.title("🚌 Ingrasys 外勞交通車費用計算")
st.write("貼上當天完整交通車訊息，系統會自動依平假日、時間、車型及停靠站數計算。")

with st.expander("使用說明與判定規則"):
    st.markdown(
        """
- 星期一至五判定為平日，星期六、日判定為假日。
- 支援時間：06:50、18:00、20:20、21:10、18:50、06:00、08:20、09:10。
- 出現「停兩」、「兩個點」，或路線像「南青-大明-興華」時，套用停兩站單價。
- 每一段資料前需有日期與星期，例如 `1/3（六）`。
        """
    )

text = st.text_area(
    "貼上交通車訊息",
    value="",
    height=500,
    placeholder="請貼上當天交通車訊息",
)

calculate = st.button("開始計算", type="primary", use_container_width=True)

if calculate:
    if not text.strip():
        st.error("請先貼上交通車訊息。")
        st.stop()

    rows, warnings = parse_transport_text(text, prices)
    if not rows:
        st.error("沒有辨識到可計算的交通車資料，請檢查日期、時間和車型格式。")
        if warnings:
            for warning in warnings:
                st.warning(warning)
        st.stop()

    detail_df = rows_to_dataframe(rows)
    summary_df = build_summary(detail_df)
    total = int(detail_df["小計"].sum())
    total_buses = int(detail_df["數量"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("總費用", f"NT$ {total:,}")
    c2.metric("總車次數量", f"{total_buses} 輛")
    c3.metric("辨識項目", f"{len(detail_df)} 筆")

    st.subheader("費用彙總")
    display_summary = summary_df.copy()
    display_summary["費用"] = display_summary["費用"].map(lambda x: f"NT$ {x:,}")
    st.dataframe(display_summary, use_container_width=True, hide_index=True)

    st.subheader("計算明細")
    display_detail = detail_df.copy()
    display_detail["單價"] = display_detail["單價"].map(lambda x: f"NT$ {x:,}")
    display_detail["小計"] = display_detail["小計"].map(lambda x: f"NT$ {x:,}")
    st.dataframe(display_detail, use_container_width=True, hide_index=True)

    csv_data = detail_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "下載計算明細 CSV",
        data=csv_data,
        file_name="Ingrasys外勞交通車費用明細.csv",
        mime="text/csv",
        use_container_width=True,
    )

    if warnings:
        with st.expander(f"注意事項（{len(warnings)}）"):
            for warning in warnings:
                st.warning(warning)

