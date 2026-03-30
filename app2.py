import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("🚀 Zalando Expert Campaign Dashboard")

# --- Helper: Robust CSV Loader ---
def load_csv(file):
    if file is None: return None
    raw_data = file.read(10000)
    file.seek(0)
    try:
        content_sample = raw_data.decode('utf-8')
    except UnicodeDecodeError:
        content_sample = raw_data.decode('latin-1')
    dialect_sep = ';' if ';' in content_sample else ','
    try:
        file.seek(0)
        return pd.read_csv(file, sep=dialect_sep, encoding='utf-8')
    except:
        file.seek(0)
        return pd.read_csv(file, sep=dialect_sep, encoding='latin-1')

# --- Helper: Numeric Cleaning ---
def clean_numeric(series):
    s = series.astype(str).str.strip()
    s = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

# --- 1. SIDEBAR: DATA INPUT ---
with st.sidebar:
    st.header("📂 Data Upload")
    curr_attalos = st.file_uploader("1. Attalos Profit (Current)", type="csv")
    z_marketing = st.file_uploader("2. Zalando SKU Report", type="csv")
    stock_file = st.file_uploader("3. Zalando Stock (Current)", type="csv")
    prev_attalos = st.file_uploader("4. Attalos Profit (Previous Week)", type="csv")
    
    st.divider()
    st.header("⚙️ Strategy Thresholds")
    top_stock = st.number_input("Min Stock for TOP", value=20)
    top_profit = st.number_input("Min Profit (€) for TOP", value=10.0)

# --- 2. DATA PROCESSING ---
if curr_attalos and z_marketing and stock_file:
    df_p = load_csv(curr_attalos)
    df_m = load_csv(z_marketing)
    df_s = load_csv(stock_file)
    
    # --- AUTO-COLUMN MAPPING ---
    # Find SKU column in Attalos
    attalos_sku_col = next((c for c in df_p.columns if 'SKU' in c.upper() or 'ARTICLE' in c.upper()), df_p.columns[0])
    # Find Profit column in Attalos
    attalos_profit_col = next((c for c in df_p.columns if 'PROFIT' in c.upper() or 'MARGIN' in c.upper() or 'CONTRIBUTION' in c.upper()), df_p.columns[-1])
    # Find Gender column in Stock
    stock_gender_col = next((c for c in df_s.columns if 'GENDER' in c.upper() or 'GESCHLECHT' in c.upper()), df_s.columns[0])
    # Find SKU in Stock
    stock_sku_col = next((c for c in df_s.columns if 'SKU' in c.upper()), 'SKU' if 'SKU' in df_s.columns else df_s.columns[0])

    st.sidebar.success(f"Matched: {attalos_sku_col} & {attalos_profit_col}")

    # Standardize and Clean
    df_p['SKU_clean'] = df_p[attalos_sku_col].astype(str).str.strip()
    df_s['SKU_clean'] = df_s[stock_sku_col].astype(str).str.strip()
    df_m['ConfigSKU'] = df_m['ConfigSKU'].astype(str).str.strip() if 'ConfigSKU' in df_m.columns else df_m.iloc[:, 6].astype(str).str.strip()

    df_m['GMV_Clean'] = clean_numeric(df_m['GMV']) if 'GMV' in df_m.columns else 0
    df_m['Spend_Clean'] = clean_numeric(df_m['Budgetspent']) if 'Budgetspent' in df_m.columns else 0
    df_p['Profit_Clean'] = clean_numeric(df_p[attalos_profit_col])

    # Merge Data
    df = pd.merge(df_s, df_p[['SKU_clean', 'Profit_Clean']], left_on='SKU_clean', right_on='SKU_clean', how='left')
    df = pd.merge(df, df_m[['ConfigSKU', 'GMV_Clean', 'Spend_Clean']], left_on='SKU_clean', right_on='ConfigSKU', how='left')
    
    # Stock Calculation
    zfs = clean_numeric(df['ZFS_Stock']) if 'ZFS_Stock' in df.columns else 0
    pf = clean_numeric(df['PF_Stock']) if 'PF_Stock' in df.columns else 0
    df['Total_Stock'] = zfs + pf

    # Trend Logic
    if prev_attalos:
        df_prev = load_csv(prev_attalos)
        df_prev['SKU_prev'] = df_prev[attalos_sku_col].astype(str).str.strip()
        new_skus = set(df_p['SKU_clean']) - set(df_prev['SKU_prev'])
    else:
        new_skus = set()

    # Categorization
    def assign_tier(row):
        if row['SKU_clean'] in new_skus: return 'TEST (NEW)'
        if row['Total_Stock'] >= top_stock and row['Profit_Clean'] >= top_profit: return 'TOP'
        if row['Total_Stock'] >= 5 and row['Profit_Clean'] > 0: return 'MEDIUM'
        return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)
    df['Group'] = df
