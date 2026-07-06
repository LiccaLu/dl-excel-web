import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin
import re
from datetime import datetime

base_url = "https://laws.mol.gov.tw"
law = []

for page in range(1, 11):
    url = base_url + "/index.aspx" if page == 1 else base_url + f"/index.aspx?page={page}"

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

source = []

for _, row in law_df.iterrows():
    detail_url = row["公告連結"]

    response = requests.get(detail_url)
    response.encoding = "utf-8"
    detail_soup = BeautifulSoup(response.text, "html.parser")

    source_url = ""

    for a in detail_soup.find_all("a"):
        text = a.get_text(strip=True)

        if "行政院公報" in text:
            source_url = urljoin(detail_url, a["href"])
            break

    source.append(source_url)

law_df["行政院公報連結"] = source

web_text_links = []

for _, row in law_df.iterrows():
    gazette_url = row["行政院公報連結"]

    if not gazette_url:
        web_text_links.append("")
        continue

    response = requests.get(gazette_url)
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    web_text_url = ""

    for a in soup.find_all("a"):
        text = a.get_text(strip=True)

        if "網頁文字版" in text:
            web_text_url = urljoin(gazette_url, a["href"])
            break

    web_text_links.append(web_text_url)

law_df["網頁文字版連結"] = web_text_links

excel_file = "行政規則公報整理.xlsx"
law_df.to_excel(excel_file, index=False)

updated_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

html = f"""
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <title>勞動法規行政規則整理</title>
    <style>
        body {{
            font-family: Arial, "Microsoft JhengHei", sans-serif;
            max-width: 900px;
            margin: 60px auto;
            padding: 20px;
            line-height: 1.6;
        }}
        h1 {{
            color: #236000;
        }}
        .card {{
            border: 1px solid #ddd;
            border-radius: 12px;
            padding: 24px;
            background: #f8fff5;
        }}
        a.button {{
            display: inline-block;
            margin-top: 20px;
            padding: 14px 24px;
            background: #2f7d00;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <h1>勞動法規行政規則整理</h1>

    <div class="card">
        <p>本頁自動整理勞動部法令查詢系統中的「行政規則」資料。</p>
        <p>更新時間：{updated_time}</p>
        <p>目前筆數：{len(law_df)}</p>

        <a class="button" href="{excel_file}" download>
            下載 Excel 檔案
        </a>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("完成")
