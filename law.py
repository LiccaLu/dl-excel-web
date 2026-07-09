import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin, quote
import re
from io import BytesIO
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(
    page_title="勞動法規行政規則整理工具",
    page_icon="⚖️",
    layout="wide"
)

st.markdown("""
<style>
.block-container {
    padding-top: 2rem;
    max-width: 1200px;
}

h1 {
    font-size: 42px !important;
    font-weight: 800 !important;
}

.stButton > button {
    background: #1f7a3f;
    color: white;
    border-radius: 10px;
    padding: 0.6rem 1.4rem;
    border: none;
    font-weight: 700;
}

.stButton > button:hover {
    background: #166534;
    color: white;
}

div[data-testid="stDateInput"] input {
    border-radius: 10px;
}

div[data-testid="stAlert"] {
    border-radius: 14px;
}

[data-testid="stDataFrame"] {
    border-radius: 14px;
    overflow: hidden;
    border: 1px solid #e5e7eb;
}

.stDownloadButton > button {
    background: #2563eb;
    color: white;
    border-radius: 10px;
    padding: 0.6rem 1.4rem;
    font-weight: 700;
    border: none;
}
</style>
""", unsafe_allow_html=True)


BASE_URL = "https://laws.mol.gov.tw"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://laws.mol.gov.tw/",
    "Connection": "close",
}


def get_html(url, timeout=90):
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            verify=False,
            timeout=timeout
        )
        r.raise_for_status()
        r.encoding = "utf-8"
        return BeautifulSoup(r.text, "html.parser")

    except requests.exceptions.Timeout:
        st.warning(f"連線逾時，略過：{url}")
        return None

    except requests.exceptions.RequestException as e:
        st.warning(f"無法連線，略過：{url}")
        return None

    except Exception as e:
        st.error(repr(e))
        return None


def roc_to_date(roc_text):
    y, m, d = roc_text.split(".")
    return date(int(y) + 1911, int(m), int(d))


def clean_title(title):
    title = title.replace("勞動部令：", "")
    title = title.replace("勞動部公告：", "")
    title = title.strip()

    effective_date = ""
    match = re.search(r"自(.+?)生效", title)

    if match:
        effective_date = match.group(1)
        title = title.split("，自")[0]

    return title, effective_date


def scrape_index(start_date, end_date):
    records = []
    page = 1

    while True:
        if page == 1:
            url = BASE_URL + "/index.aspx"
        else:
            url = BASE_URL + f"/index.aspx?page={page}"

        soup = get_html(url)

        if soup is None:
            st.error("連不上勞動部網站，這不是沒有資料，是網站連線失敗。")
            return pd.DataFrame()
            
        table = soup.find("table", class_="table-list news-table")

        if table is None:
            break

        should_stop = False

        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")

            if len(cols) < 3:
                continue

            date_text = cols[0].get_text(strip=True)

            try:
                publish_date = roc_to_date(date_text)
            except Exception:
                continue

            if publish_date < start_date:
                should_stop = True
                break

            if publish_date > end_date:
                continue

            category = cols[1].get_text(strip=True)

            if category != "行政規則":
                continue

            raw_title = cols[2].get_text(strip=True)
            title, effective_date = clean_title(raw_title)

            a = cols[2].find("a")
            notice_url = urljoin(BASE_URL, a.get("href", "")) if a else ""

            records.append({
                "公發布日": date_text,
                "類別": category,
                "訊息摘要": title,
                "生效日期": effective_date,
                "公告連結": notice_url
            })

        if should_stop:
            break

        page += 1

    return pd.DataFrame(records)


def get_law_name(detail_soup):
    lines = detail_soup.get_text("\n", strip=True).split("\n")

    for i, line in enumerate(lines):
        if "法規名稱" in line and i + 1 < len(lines):
            return lines[i + 1].strip()

    return ""


def get_gazette_url(detail_url, detail_soup):
    for a in detail_soup.find_all("a"):
        text = a.get_text(strip=True)
        href = a.get("href", "")

        if "行政院公報" in text and href:
            return urljoin(detail_url, href.replace("&amp;", "&"))

    return ""


def get_text_version_url(gazette_url):
    if not gazette_url:
        return ""

    try:
        soup = get_html(gazette_url)
        if soup is None:
            return ""

        for tag in soup.find_all(["a", "iframe"]):
            text = tag.get_text(strip=True)
            href = tag.get("href") or tag.get("src") or ""

            if not href:
                continue

            if (
                "網頁文字版" in text
                or "文字版" in text
                or "eguploadpubWrapper" in href
                or "eguploadpub" in href
            ):
                return urljoin(gazette_url, href.replace("&amp;", "&"))

    except Exception:
        return ""

    return ""


def search_history(law_name):
    if not law_name:
        return "", 0

    search_url = BASE_URL + "/results.aspx?searchmode=global&keyword=" + quote(law_name)

    try:
        soup = get_html(search_url)
        if soup is None:
            return "", 0
        dates = []

        for row in soup.find_all("tr"):
            cols = row.find_all("td")

            if len(cols) < 4:
                continue

            category = cols[1].get_text(strip=True)
            date_text = cols[3].get_text(strip=True)

            if category != "最新動態":
                dates.append(date_text)

        if dates:
            return "、".join(dates), len(dates)

    except Exception:
        pass

    return "", 0


def enrich_one(row):
    notice_url = row["公告連結"]

    law_name = ""
    history_dates = ""
    history_count = 0
    gazette_url = ""
    text_url = ""

    try:
        detail_soup = get_html(notice_url)

        law_name = get_law_name(detail_soup)
        gazette_url = get_gazette_url(notice_url, detail_soup)
        text_url = get_text_version_url(gazette_url)

        history_dates, history_count = search_history(law_name)

    except Exception:
        pass

    return {
        "法規名稱": law_name,
        "歷次修改日期": history_dates,
        "歷史筆數": history_count,
        "行政院公報連結": gazette_url,
        "網頁文字版連結": text_url
    }


def scrape_laws(start_date, end_date):
    df = scrape_index(start_date, end_date)

    if df.empty:
        return df

    rows = [row for _, row in df.iterrows()]

    with ThreadPoolExecutor(max_workers=2) as executor:
        enriched = list(executor.map(enrich_one, rows))

    enrich_df = pd.DataFrame(enriched)
    df = pd.concat([df.reset_index(drop=True), enrich_df], axis=1)

    return df


def to_excel(df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="行政規則整理")

    return output.getvalue()


st.title("⚖️ 勞動法規行政規則整理工具")
st.write("選擇日期區間後，系統會即時爬取勞動部最新動態，整理行政規則，並產生 Excel 下載檔。")

start_date = st.date_input("開始日期", value=date(2026, 6, 1))
end_date = st.date_input("結束日期", value=date(2026, 7, 7))

if start_date > end_date:
    st.error("開始日期不能晚於結束日期。")

if st.button("開始整理"):
    with st.spinner("正在爬取資料，請稍候..."):
        df = scrape_laws(start_date, end_date)

    if df.empty:
        st.warning("這個日期區間沒有找到行政規則。")
    else:
        st.success(f"整理完成，共 {len(df)} 筆行政規則")

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "公告連結": st.column_config.LinkColumn(
                    "公告連結",
                    display_text="開啟公告"
                ),
                "行政院公報連結": st.column_config.LinkColumn(
                    "行政院公報連結",
                    display_text="開啟公報"
                ),
                "網頁文字版連結": st.column_config.LinkColumn(
                    "網頁文字版連結",
                    display_text="開啟文字版"
                ),
            }
        )

        st.download_button(
            label="下載 Excel 檔案",
            data=to_excel(df),
            file_name="行政規則公報整理.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
