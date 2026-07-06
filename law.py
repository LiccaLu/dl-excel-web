import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin
import re
from io import BytesIO

st.set_page_config(page_title="勞動法規整理工具", page_icon="⚖️", layout="wide")

st.title("⚖️ 勞動法規行政規則整理工具")
st.write("按下按鈕後，系統會即時爬取勞動部最新動態，整理行政規則，並產生 Excel 下載檔。")

base_url = "https://laws.mol.gov.tw"

def scrape_laws(pages=10):
    law = []

    for page in range(1, pages + 1):
        if page == 1:
            url = base_url + "/index.aspx"
        else:
            url = base_url + f"/index.aspx?page={page}"

        read = requests.get(url)
        read.encoding = "utf-8"

        soup = BeautifulSoup(read.text, "html.parser")
        table = soup.find("table", class_="table-list news-table")

        if table is None:
            continue

        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")

            if len(cols) < 3:
                continue

            date = cols[0].get_text(strip=True)
            category = cols[1].get_text(strip=True)
            title = cols[2].get_text(strip=True)

            if category != "行政規則":
                continue

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
                "公發布日": date,
                "類別": category,
                "訊息摘要": title,
                "生效日期": effective_date,
                "公告連結": link
            })

    law_df = pd.DataFrame(law)

    source_links = []

    for _, row in law_df.iterrows():
        detail_url = row["公告連結"]

        source_url = ""

        try:
            response = requests.get(detail_url)
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

    web_text_links = []

    for _, row in law_df.iterrows():
        gazette_url = row["行政院公報連結"]

        if not gazette_url:
            web_text_links.append("")
            continue

        web_text_url = ""

        try:
            response = requests.get(gazette_url)
            response.encoding = "utf-8"
            soup = BeautifulSoup(response.text, "html.parser")

            for a in soup.find_all("a"):
                text = a.get_text(strip=True)

                if "網頁文字版" in text:
                    web_text_url = urljoin(gazette_url, a.get("href", ""))
                    break

        except Exception:
            web_text_url = ""

        web_text_links.append(web_text_url)

    law_df["網頁文字版連結"] = web_text_links

    return law_df


pages = st.number_input("要抓幾頁？", min_value=1, max_value=50, value=10)

if st.button("開始整理"):
    with st.spinner("正在爬取資料，請稍候..."):
        df = scrape_laws(pages)

    st.success(f"整理完成，共 {len(df)} 筆行政規則")

    st.dataframe(df, use_container_width=True)

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

print("完成")
