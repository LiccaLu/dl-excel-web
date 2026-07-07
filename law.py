import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin
import re
from io import BytesIO
from datetime import date
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(
    page_title="勞動法規整理工具",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ 勞動法規行政規則整理工具")
st.write("選擇日期區間後，系統會即時爬取勞動部最新動態，整理行政規則，並產生 Excel 下載檔。")

base_url = "https://laws.mol.gov.tw"


def roc_to_date(roc_text):
    """
    把民國日期轉成西元日期
    例如：115.07.03 -> 2026-07-03
    """
    y, m, d = roc_text.split(".")
    return date(int(y) + 1911, int(m), int(d))


def scrape_laws(start_date, end_date):
    law = []
    page = 1

    while True:
        if page == 1:
            url = base_url + "/index.aspx"
        else:
            url = base_url + f"/index.aspx?page={page}"

        read = requests.get(url, verify=False, timeout=20)
        read.encoding = "utf-8"

        soup = BeautifulSoup(read.text, "html.parser")
        table = soup.find("table", class_="table-list news-table")

        if table is None:
            break

        stop = False

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
                stop = True
                break

            if publish_date > end_date:
                continue

            category = cols[1].get_text(strip=True)

            if category != "行政規則":
                continue

            title = cols[2].get_text(strip=True)

            title = title.replace("勞動部令：", "")
            title = title.replace("勞動部公告：", "")

            effective_date = ""
            match = re.search(r"自(.+?)生效", title)

            if match:
                effective_date = match.group(1)
                title = title.split("，自")[0]

            a = cols[2].find("a")
            link = urljoin(base_url, a["href"]) if a else ""

            law.append({
                "公發布日": date_text,
                "類別": category,
                "訊息摘要": title,
                "生效日期": effective_date,
                "公告連結": link
            })

        if stop:
            break

        page += 1

    law_df = pd.DataFrame(law)

    if law_df.empty:
        return law_df

    # 找行政院公報連結
    source_links = []

    for _, row in law_df.iterrows():
        detail_url = row["公告連結"]
        source_url = ""

        try:
            response = requests.get(detail_url, verify=False, timeout=20)
            response.encoding = "utf-8"

            detail_soup = BeautifulSoup(response.text, "html.parser")

            for a in detail_soup.find_all("a"):
                text = a.get_text(strip=True)

                if "行政院公報" in text:
                    source_url = urljoin(detail_url, a.get("href", ""))
                    break

        except Exception:
            source_url = ""

        source_links.append(source_url)

    law_df["行政院公報連結"] = source_links

    def get_law_name(detail_url):
    try:
        response = requests.get(detail_url, verify=False, timeout=8)
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        text = soup.get_text("\n", strip=True).split("\n")

        for i, line in enumerate(text):
            if "法規名稱" in line and i + 1 < len(text):
                return text[i + 1]

    except Exception:
        return ""

    return ""

def search_law_history(law_name):
    if not law_name:
        return "", 0

    search_url = base_url + "/SearchResult.aspx"

    try:
        response = requests.get(
            search_url,
            params={"keyword": law_name},
            verify=False,
            timeout=8
        )
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        dates = []

        for row in soup.find_all("tr"):
            cols = row.find_all("td")

            if len(cols) >= 4:
                category = cols[1].get_text(strip=True)
                title = cols[2].get_text(strip=True)
                date_text = cols[3].get_text(strip=True)

                if law_name in title or "勞動部令" in title:
                    dates.append(date_text)

        if dates:
            return dates[0], len(dates)

    except Exception:
        return "", 0

    return "", 0

    # 找網頁文字版連結
    web_text_links = []
    
    for _, row in law_df.iterrows():
        gazette_url = row["行政院公報連結"]
    
        if not gazette_url:
            web_text_links.append("")
            continue
    
        web_text_url = ""
    
        try:
            response = requests.get(gazette_url, verify=False, timeout=8)
            response.encoding = "utf-8"
            soup = BeautifulSoup(response.text, "html.parser")
    
            for a in soup.find_all("a"):
                href = a.get("href", "")
    
                if "eguploadpubWrapper" in href:
                    web_text_url = urljoin(gazette_url, href)
                    break
    
        except Exception:
            web_text_url = ""
    
        web_text_links.append(web_text_url)
    
    law_df["網頁文字版連結"] = web_text_links

    history_dates = []

    for _, row in law_df.iterrows():
        text_url = row["網頁文字版連結"]
        last_date = ""
    
        if text_url:
            try:
                response = requests.get(text_url, verify=False, timeout=8)
                response.encoding = "utf-8"
                soup = BeautifulSoup(response.text, "html.parser")
                text = soup.get_text("\n", strip=True)
    
                matches = re.findall(r"中華民國(\d+年\d+月\d+日)", text)
    
                if matches:
                    last_date = matches[-1]   # 通常最後一個是最近一次修正/發布日期
    
            except Exception:
                last_date = ""
    
        history_dates.append(last_date)
    
    law_df["上次修改日期"] = history_dates

    law_names = []
    last_dates = []
    history_counts = []
    
    for _, row in law_df.iterrows():
        detail_url = row["公告連結"]
    
        law_name = get_law_name(detail_url)
        last_date, count = search_law_history(law_name)
    
        law_names.append(law_name)
        last_dates.append(last_date)
        history_counts.append(count)
    
    law_df["法規名稱"] = law_names
    law_df["上次修改日期"] = last_dates
    law_df["歷史筆數"] = history_counts

    return law_df


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
            
        output = BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="行政規則整理")

        excel_data = output.getvalue()

        st.download_button(
            label="下載 Excel 檔案",
            data=excel_data,
            file_name="行政規則公報整理.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
