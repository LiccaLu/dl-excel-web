import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin
import re
from io import BytesIO
from datetime import date
import urllib3
from st_aggrid import AgGrid, GridOptionsBuilder

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

    # 找網頁文字版連結
    web_text_links = []

    for _, row in law_df.iterrows():
        gazette_url = row["行政院公報連結"]

        if not gazette_url:
            web_text_links.append("")
            continue

        web_text_url = ""

        try:
            response = requests.get(gazette_url, verify=False, timeout=20)
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

        gb = GridOptionsBuilder.from_dataframe(df)

        gb.configure_column("公告連結", cellRenderer="""
        class UrlCellRenderer {
            init(params) {
                this.eGui = document.createElement('a');
                this.eGui.innerText = '開啟';
                this.eGui.href = params.value;
                this.eGui.target = '_blank';
            }
            getGui() {
                return this.eGui;
            }
        }
        """)
        
        gb.configure_column("行政院公報連結", cellRenderer="""
        class UrlCellRenderer {
            init(params) {
                this.eGui = document.createElement('a');
                this.eGui.innerText = '開啟';
                this.eGui.href = params.value;
                this.eGui.target = '_blank';
            }
            getGui() {
                return this.eGui;
            }
        }
        """)
        
        gb.configure_column("網頁文字版連結", cellRenderer="""
        class UrlCellRenderer {
            init(params) {
                this.eGui = document.createElement('a');
                this.eGui.innerText = '開啟';
                this.eGui.href = params.value;
                this.eGui.target = '_blank';
            }
            getGui() {
                return this.eGui;
            }
        }
        """)
        
        AgGrid(
            df,
            gridOptions=gb.build(),
            allow_unsafe_jscode=True,
            fit_columns_on_grid_load=True,
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
