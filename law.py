import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin, quote
import re
from io import BytesIO
from datetime import date
import urllib3
from concurrent.futures import ThreadPoolExecutor

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="勞動法規整理工具", page_icon="⚖️", layout="wide")

st.title("⚖️ 勞動法規行政規則整理工具")
st.write("選擇日期區間後，系統會即時爬取勞動部最新動態，整理行政規則，並產生 Excel 下載檔。")

base_url = "https://laws.mol.gov.tw"


def get_html(url, timeout=8):
    response = requests.get(url, verify=False, timeout=timeout)
    response.encoding = "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def roc_to_date(roc_text):
    y, m, d = roc_text.split(".")
    return date(int(y) + 1911, int(m), int(d))


def search_law_history(law_name):
    if not law_name:
        return "", 0

    search_url = base_url + "/results.aspx?searchmode=global&keyword=" + quote(law_name)

    try:
        soup = get_html(search_url)
        dates = []

        for row in soup.find_all("tr"):
            cols = row.find_all("td")

            if len(cols) >= 4:
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
    detail_url = row["公告連結"]

    law_name = ""
    history_dates = ""
    history_count = 0
    source_url = ""
    web_text_url = ""

    try:
        detail_soup = get_html(detail_url)

        lines = detail_soup.get_text("\n", strip=True).split("\n")

        for i, line in enumerate(lines):
            if "法規名稱" in line and i + 1 < len(lines):
                law_name = lines[i + 1].strip()
                break

        for a in detail_soup.find_all("a"):
            text = a.get_text(strip=True)
            href = a.get("href", "")

            if "行政院公報" in text:
                source_url = urljoin(detail_url, href)
                break

        if law_name:
            history_dates, history_count = search_law_history(law_name)

        if source_url:
            gazette_soup = get_html(source_url)

            for tag in gazette_soup.find_all(["a", "iframe"]):
                text = tag.get_text(strip=True)
                href = tag.get("href") or tag.get("src") or ""

                if not href:
                    continue

                if "網頁文字版" in text or "文字版" in text or "eguploadpubWrapper" in href: web_text_url = urljoin(source_url, href) break

    except Exception:
        pass

    return law_name, history_dates, history_count, source_url, web_text_url


def scrape_laws(start_date, end_date):
    law = []
    page = 1

    while True:
        url = base_url + "/index.aspx" if page == 1 else base_url + f"/index.aspx?page={page}"

        soup = get_html(url)
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
            title = title.replace("勞動部令：", "").replace("勞動部公告：", "")

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

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(enrich_one, [row for _, row in law_df.iterrows()]))

    law_df["法規名稱"] = [r[0] for r in results]
    law_df["歷次修改日期"] = [r[1] for r in results]
    law_df["歷史筆數"] = [r[2] for r in results]
    law_df["行政院公報連結"] = [r[3] for r in results]
    law_df["網頁文字版連結"] = [r[4] for r in results]

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
                "公告連結": st.column_config.LinkColumn("公告連結", display_text="開啟公告"),
                "行政院公報連結": st.column_config.LinkColumn("行政院公報連結", display_text="開啟公報"),
                "網頁文字版連結": st.column_config.LinkColumn("網頁文字版連結", display_text="開啟文字版"),
            }
        )

        output = BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="行政規則整理")

        st.download_button(
            label="下載 Excel 檔案",
            data=output.getvalue(),
            file_name="行政規則公報整理.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
