import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="DL基本資料整理工具", page_icon="📄", layout="centered")
st.title("DL基本資料整理工具")
st.write("上傳履歷表 Excel，系統會自動整理，完成後可下載處理後檔案。")

uploaded_file = st.file_uploader("請上傳 Excel 檔案", type=["xlsx", "xls"])


def safe_check_columns(df, required_cols):
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error("Excel 缺少以下欄位：" + "、".join(missing))
        st.stop()


def process_excel(file):
    df = pd.read_excel(file)

    required_cols = [
        "開始時間", "性別",
        "學士 學業狀態", "專科 學業狀態", "高中/職 學業狀態",
        "1公司規模", "2公司規模", "3公司規模", "4公司規模", "5公司規模",
        '1服務期間', '2服務期間 ', '3服務期間 ', '4服務期間 ', '5服務期間 '
    ]
    
    safe_check_columns(df, required_cols)

    # 填表時間
    df["開始時間"] = pd.to_datetime(df["開始時間"], errors="coerce").dt.strftime("%Y年%m月%d日")

    # 性別
    df["性別"] = np.where(df["性別"] == "男", "■男    □女", "□男    ■女")

    # 學歷
    graduate = ["學士 學業狀態", "專科 學業狀態", "高中/職 學業狀態"]
    for col in graduate:
        idx = df.columns.get_loc(col)
        df.insert(idx + 1, column=f"{col}學業狀態_畢業", value=np.where(df[col] == "畢業", "■", "□"))
        df.insert(idx + 2, column=f"{col}學業狀態_結業", value=np.where(df[col] == "結業", "■", "□"))
        df.insert(idx + 3, column=f"{col}學業狀態_肆業", value=np.where(df[col] == "肆業", "■", "□"))

    # 公司規模
    comp = ["1公司規模", "2公司規模", "3公司規模", "4公司規模", "5公司規模"]
    company_size_map = {
        "1000人 以上": "■1000人 以上  □500 ~1000人 □100 ~500人 □100人以下",
        "500-1000人": "□1000人 以上  ■500 ~1000人 □100 ~500人 □100人以下",
        "100-500人": "□1000人 以上  □500 ~1000人 ■100 ~500人 □100人以下",
        "100人 以下": "□1000人 以上  □500 ~1000人 □100 ~500人 ■100人以下",
    }
    for col in comp:
        df[col] = df[col].replace(company_size_map)

    #服務期間
    worktime = ['1服務期間', '2服務期間 ', '3服務期間 ', '4服務期間 ', '5服務期間 ']
    for col in worktime:
        idx2 = df.columns.get_loc(col)
        split = df[col].astype(str).str.split(r'[~～]', expand=True)
        df.insert(idx2 + 1, f'{col}_結束', split[1].str.strip())
        df[col] = split[0].str.strip()

    #生日
    df['生日'] = pd.to_datetime(df['生日'].astype(str), errors = 'coerce', format= 'mixed').dt.strftime('%Y年%m月%d日')

    #婚姻狀況
    for i, row in df.iterrows():
      if row['婚姻狀況'] == '已婚':
        df.loc[i, '婚姻狀況'] = '■已婚    □未婚    □離異'
      elif row['婚姻狀況'] == '未婚':
        df.loc[i, '婚姻狀況'] = '□已婚    ■未婚    □離異'
      elif row['婚姻狀況'] == '離異':
        df.loc[i, '婚姻狀況'] = '□已婚    □未婚    ■離異'

    #血型
    for i, row in df.iterrows():
      if row['血型'] == 'A':
        df.loc[i, '血型'] = '■A    □B    □O    □AB'
      elif row['血型'] == 'B':
        df.loc[i, '血型'] = '□A    ■B    □O    □AB'
      elif row['血型'] == 'O':
        df.loc[i, '血型'] = '□A    □B    ■O    □AB'
      elif row['血型'] == 'AB':
        df.loc[i, '血型'] = '□A    □B    □O    ■AB'

    #原住民身份
    df['是否有原住民身分？'] = np.where(df[col].astype(str).str.startswith('是'),'■是    □否','□是    ■否')

    #兵歷
    df['兵歷'] = np.where(df['兵歷'] == '役畢','■役畢    □免役','□役畢    ■免役')

    #入伍與退伍時間
    for col in ['入伍與退伍時間']:
      idx2 = df.columns.get_loc(col)
      split1 = df[col].astype(str).str.split(r'[~～]', expand=True)

      if split1.shape[1] == 1:
        split[1] = ''

      df.insert(idx2 + 1, f'{col}_退伍', split[1].str.strip())
      df[col] = split[0].str.strip()

    #住宿情況
    for i, row in df.iterrows():
      if row['住宿情形'] == '自宅':
        df.loc[i, '住宿情形'] = '■自宅    □未婚    □其他＿＿＿＿'
      elif row['住宿情形'] == '租屋':
        df.loc[i, '住宿情形'] = '□自宅    ■租屋    □其他＿＿＿＿'
      else:
        df.loc[i, '住宿情形'] = f'□自宅 □租屋 ■其他__{row["住宿情形"]}__'

    #存歿
    live = ['存歿', '存歿2', '存歿3', '存歿4', '存歿5']
    for col in live:
      for i, row in df.iterrows():
        if row[col] == '存':
          df.loc[i, col] = '■  □'
        else:
          df.loc[i, col] = '□  ■'
        
    return df


if uploaded_file is not None:
    st.success("檔案上傳成功")

    if st.button("開始處理"):
        result_df = process_excel(uploaded_file)

        output = BytesIO()
        result_df.to_excel(output, index=False, engine="openpyxl")
        output.seek(0)

        st.success("處理完成")
        st.download_button(
            label="下載處理後 Excel",
            data=output,
            file_name="處理後履歷表.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
