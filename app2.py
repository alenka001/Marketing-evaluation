import streamlit as st
import pandas as pd
import plotly.express as px

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
    
    # Identify SKU and Gender columns dynamically
    p_sku = next((c for c in df_p.columns if 'SKU' in c.upper()), df_p.columns[0])
    s_sku = next((c for c in df_s.columns if 'SKU' in c.upper()), df_s.columns[0])
    m_sku = 'ConfigSKU' if 'ConfigSKU' in df_m.columns else df_m.columns[6]
    s_gender = next((c for c in df_s.columns if 'GENDER' in c.upper() or 'GESCHLECHT' in c.upper()), None)

    # Clean SKUs
    df_p['SKU_KEY'] = df_p[p_sku].astype(str).str.strip()
    df_s['SKU_KEY'] = df_s[s_sku].astype(str).str.strip()
    df_m['SKU_KEY'] = df_m[m_sku].astype(str).str.strip()

    # Clean Numerics
    profit_col = next((c for c in df_p.columns if 'PROFIT' in c.upper() or 'MARGIN' in c.upper()), df_p.columns[-1])
    df_p['Profit_Clean'] = clean_numeric(df_p[profit_col])
    df_m['GMV_Clean'] = clean_numeric(df_m['GMV']) if 'GMV' in df_m.columns else 0
    df_m['Spend_Clean'] = clean_numeric(df_m['Budgetspent']) if 'Budgetspent' in df_m.columns else 0

    # Stock Calculation
    zfs = clean_numeric(df_s['ZFS_Stock']) if 'ZFS_Stock' in df_s.columns else 0
    pf = clean_numeric(df_s['PF_Stock']) if 'PF_Stock' in df_s.columns else 0
    df_s['Total_Stock'] = zfs + pf

    # Sequential Merging to avoid row bloat
    df = pd.merge(df_s, df_p[['SKU_KEY', 'Profit_Clean']], on='SKU_KEY', how='left')
    df = pd.merge(df, df_m[['SKU_KEY', 'GMV_Clean', 'Spend_Clean']], on='SKU_KEY', how='left')

    # Trend Logic
    new_skus = set()
    if prev_attalos:
        df_prev = load_csv(prev_attalos)
        prev_sku_col = next((c for c in df_prev.columns if 'SKU' in c.upper()), df_prev.columns[0])
        new_skus = set(df_p['SKU_KEY']) - set(df_prev[prev_sku_col].astype(str).str.strip())

    # Tier Assignment
    def assign_tier(row):
        if row['SKU_KEY'] in new_skus: return 'TEST (NEW)'
        if row['Total_Stock'] >= top_stock and row['Profit_Clean'] >= top_profit: return 'TOP'
        if row['Total_Stock'] >= 5 and row['Profit_Clean'] > 0: return 'MEDIUM'
        return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)

    # Group Assignment (Safety Check for Missing Gender)
    if s_gender:
        df['Group'] = df[s_gender].apply(lambda x: 'FEMALE' if any(g in str(x).upper() for g in ['DAM', 'FEMALE', 'WMS']) else 'MALE_UNISEX')
    else:
        df['Group'] = 'MALE_UNISEX'

    # --- 3. DASHBOARD ---
    st.header("📈 Inventory & Performance")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total GMV", f"€{df['GMV_Clean'].sum():,.0f}")
    col2.metric("Total Spend", f"€{df['Spend_Clean'].sum():,.0f}")
    col3.metric("New Arrivals", len(new_skus))

    # --- 4. CAMPAIGN EXPORTS ---
    st.divider()
    all_tiers = ['TOP', 'MEDIUM', 'LOW', 'TEST (NEW)']
    
    for group in ['FEMALE', 'MALE_UNISEX']:
        st.subheader(f"Group: {group}")
        cols = st.columns(4)
        group_df = df[df['Group'] == group]
        
        for i, tier in enumerate(all_tiers):
            with cols[i]:
                subset = group_df[group_df['Tier'] == tier]
                st.write(f"**{tier}** ({len(subset)})")
                sku_str = ",".join(subset['SKU_KEY'].dropna().unique().tolist())
                st.text_area("Copy SKUs:", value=sku_str, height=100, key=f"t_{group}_{tier}", label_visibility="collapsed")
                
                # Export Button
                csv = pd.DataFrame(subset['SKU_KEY'].unique()).to_csv(index=False, header=
