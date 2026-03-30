import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("🚀 Zalando Expert Campaign Dashboard")

# --- Helper: Robust CSV Loader with Multi-Encoding Support ---
def load_csv(file):
    if file is None:
        return None
    
    # Read raw bytes to detect delimiter and handle encodings
    raw_data = file.read(5000)
    file.seek(0) # Reset
    
    # Try to decode to check for semicolon
    try:
        content_sample = raw_data.decode('utf-8')
    except UnicodeDecodeError:
        content_sample = raw_data.decode('latin-1')
        
    dialect_sep = ';' if ';' in content_sample else ','
    
    # Try reading with UTF-8 first, fallback to Latin-1
    try:
        file.seek(0)
        return pd.read_csv(file, sep=dialect_sep, encoding='utf-8')
    except (UnicodeDecodeError, pd.errors.ParserError):
        file.seek(0)
        return pd.read_csv(file, sep=dialect_sep, encoding='latin-1')

# --- Helper: Numeric Cleaning ---
def clean_numeric(series):
    s = series.astype(str).str.strip()
    # Remove dots (thousands) and change commas to dots (decimals)
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
    
    # Ensure SKUs are clean strings
    df_p['SKU'] = df_p['SKU'].astype(str).str.strip()
    df_s['SKU'] = df_s['SKU'].astype(str).str.strip()
    df_m['ConfigSKU'] = df_m['ConfigSKU'].astype(str).str.strip()

    # Numeric Cleaning
    df_m['GMV_Clean'] = clean_numeric(df_m['GMV'])
    df_m['Spend_Clean'] = clean_numeric(df_m['Budgetspent'])
    # Check if Attalos uses 'Net_Profit' or similar
    profit_col = 'Net_Profit' if 'Net_Profit' in df_p.columns else df_p.columns[-1]
    df_p['Profit_Clean'] = clean_numeric(df_p[profit_col])

    # Merge Data
    df = pd.merge(df_s, df_p[['SKU', 'Profit_Clean']], on='SKU', how='left')
    df = pd.merge(df, df_m[['ConfigSKU', 'GMV_Clean', 'Spend_Clean']], left_on='SKU', right_on='ConfigSKU', how='left')
    
    df['Total_Stock'] = clean_numeric(df.get('ZFS_Stock', 0)) + clean_numeric(df.get('PF_Stock', 0))

    # Trend & New Arrival Logic
    if prev_attalos:
        df_prev = load_csv(prev_attalos)
        df_prev['SKU'] = df_prev['SKU'].astype(str).str.strip()
        new_skus = set(df_p['SKU']) - set(df_prev['SKU'])
        df_prev['Prev_Profit_Clean'] = clean_numeric(df_prev[profit_col])
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

    # --- 3. DASHBOARD ---
    st.header("📈 Weekly Summary")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total GMV", f"€{df['GMV_Clean'].sum():,.0f}")
    m2.metric("Ad Spend", f"€{df['Spend_Clean'].sum():,.0f}")
    m3.metric("New Arrivals", len(new_skus))
    m4.metric("Avg Profit Margin", f"€{df['Profit_Clean'].mean():.2f}")

    # --- 4. CAMPAIGN EXPORTS ---
    st.divider()
    st.header("🎯 Campaign SKU Updates")
    all_tiers = ['TOP', 'MEDIUM', 'LOW', 'TEST (NEW)']
    
    for group in ['FEMALE', 'MALE_UNISEX']:
        st.subheader(f"Group: {group}")
        cols = st.columns(4)
        for i, tier in enumerate(all_tiers):
            with cols[i]:
                subset = df[(df['Group'] == group) & (df['Tier'] == tier)]
                st.write(f"**{tier}** ({len(subset)})")
                sku_str = ",".join(subset['SKU'].tolist())
                st.text_area("SKUs:", value=sku_str, height=100, key=f"t_{group}_{tier}", label_visibility="collapsed")
                csv = subset[['SKU']].to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Export CSV", csv, f"{group}_{tier}.csv", "text/csv", key=f"d_{group}_{tier}")

else:
    st.info("👋 Ready to start. Upload all files (including the Zalando SKU report) in the sidebar.")
