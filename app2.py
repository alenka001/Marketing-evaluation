import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("🚀 Zalando Expert Campaign Dashboard")

# --- Helper: Robust CSV Loader ---
def load_csv(file):
    if file is None:
        return None
    content = file.read(2048).decode('utf-8', errors='ignore')
    file.seek(0)
    dialect_sep = ';' if ';' in content else ','
    return pd.read_csv(file, sep=dialect_sep)

# --- Helper: Numeric Cleaning ---
def clean_numeric(series):
    s = series.astype(str).str.strip()
    s = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

# --- 1. SIDEBAR: DATA INPUT ---
with st.sidebar:
    st.header("📂 Data Upload")
    curr_attalos = st.file_uploader("1. Attalos Profit (Current)", type="csv")
    z_marketing = st.file_uploader("2. Zalando SKU Report (Marketing Outcome)", type="csv")
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
    
    # Standardize SKUs
    df_p['SKU'] = df_p['SKU'].astype(str).str.strip()
    df_s['SKU'] = df_s['SKU'].astype(str).str.strip()
    df_m['ConfigSKU'] = df_m['ConfigSKU'].astype(str).str.strip()

    # Data Health Calculations
    total_skus_in_stock = len(df_s['SKU'].unique())
    skus_matched = len(set(df_s['SKU']) & set(df_p['SKU']))
    match_rate = (skus_matched / total_skus_in_stock) * 100

    # --- DATA HEALTH SECTION ---
    st.header("🩺 Data Health Check")
    h1, h2, h3 = st.columns(3)
    
    with h1:
        st.metric("SKU Match Rate (Stock vs Profit)", f"{match_rate:.1f}%")
        if match_rate < 90:
            st.warning("⚠️ High number of SKUs missing profit data!")
    with h2:
        st.metric("Total Stock Units", int(clean_numeric(df_s.get('ZFS_Stock', 0)).sum() + clean_numeric(df_s.get('PF_Stock', 0)).sum()))
    with h3:
        st.info("💡 Tip: Ensure SKUs in all files match the Zalando 'Config SKU' format.")

    # Processing & Merging
    df_m['GMV_Clean'] = clean_numeric(df_m['GMV'])
    df_m['Spend_Clean'] = clean_numeric(df_m['Budgetspent'])
    df_p['Profit_Clean'] = clean_numeric(df_p['Net_Profit'])

    df = pd.merge(df_s, df_p[['SKU', 'Profit_Clean']], on='SKU', how='left')
    df = pd.merge(df, df_m[['ConfigSKU', 'GMV_Clean', 'Spend_Clean']], left_on='SKU', right_on='ConfigSKU', how='left')
    
    df['Total_Stock'] = clean_numeric(df.get('ZFS_Stock', 0)) + clean_numeric(df.get('PF_Stock', 0))

    # Trend & New Arrival Logic
    if prev_attalos:
        df_prev = load_csv(prev_attalos)
        df_prev['SKU'] = df_prev['SKU'].astype(str).str.strip()
        new_skus = set(df_p['SKU']) - set(df_prev['SKU'])
        df_prev['Prev_Profit_Clean'] = clean_numeric(df_prev['Net_Profit'])
        df = pd.merge(df, df_prev[['SKU', 'Prev_Profit_Clean']], on='SKU', how='left')
        df['Profit_Delta'] = df['Profit_Clean'] - df['Prev_Profit_Clean'].fillna(0)
    else:
        new_skus = set()
        df['Profit_Delta'] = 0

    # Categorization
    def assign_tier(row):
        if row['SKU'] in new_skus: return 'TEST (NEW)'
        if row['Total_Stock'] >= top_stock and row['Profit_Clean'] >= top_profit: return 'TOP'
        if row['Total_Stock'] >= 5 and row['Profit_Clean'] > 0: return 'MEDIUM'
        return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)
    df['Group'] = df['Gender'].apply(lambda x: 'FEMALE' if any(g in str(x).upper() for g in ['DAM', 'FEMALE']) else 'MALE_UNISEX')

    # --- 3. CAMPAIGN EXPORTS ---
    st.divider()
    st.header("🎯 Weekly Campaign SKU Updates")
    all_tiers = ['TOP', 'MEDIUM', 'LOW', 'TEST (NEW)']
    
    for group in ['FEMALE', 'MALE_UNISEX']:
        st.subheader(f"Campaign Group: {group}")
        cols = st.columns(4)
        for i, tier in enumerate(all_tiers):
            with cols[i]:
                subset = df[(df['Group'] == group) & (df['Tier'] == tier)]
                st.write(f"**{tier}** ({len(subset)} items)")
                sku_str = ",".join(subset['SKU'].tolist())
                st.text
