import streamlit as st
import pandas as pd
import io

# --- Page Setup ---
st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("🚀 Swedemount Expert: Strict Article Tiering")

# --- 1. UTILITIES ---
def clean_numeric(series):
    """Handles European formatting: 1.454,95 -> 1454.95"""
    s = series.astype(str).str.strip().str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def standardize_sku(sku):
    """Truncates SKU to the 13-character Config ID"""
    s = str(sku).strip().upper().replace('.0', '')
    if '-' in s:
        parts = s.split('-')
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1][:3]}"
    return s

def load_csv(file):
    if file is None: return None
    raw_data = file.read(30000)
    file.seek(0)
    try: sample = raw_data.decode('utf-8')
    except: sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1')

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("📂 Data Upload")
    z_marketing = st.file_uploader("1. Swedemount Marketing File", type="csv")
    stock_file = st.file_uploader("2. Inventory File (47a2...)", type="csv")
    
    st.divider()
    st.header("🏆 TOP Tier Thresholds")
    t_stock = st.number_input("Min Stock (TOP)", value=10)
    t_roas = st.number_input("Min ROAS (TOP)", value=4.0)
    
    st.header("🥈 MEDIUM Tier Thresholds")
    m_stock = st.number_input("Min Stock (MED)", value=5)
    m_roas = st.number_input("Min ROAS (MED)", value=2.0)

    st.header("⚠️ Stock Warning")
    days_threshold = st.slider("Alert if Stock Days less than:", 1, 10, 3)

# --- 3. DATA ENGINE ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    # A. Clean Marketing Data
    df_m = df_m_raw[df_m_raw.iloc[:, 0].astype(str).str.contains('20', na=False)].copy()
    latest_week = clean_numeric(df_m.iloc[:, 2]).max()
    df_m_latest = df_m[clean_numeric(df_m.iloc[:, 2]) == latest_week].copy()
    
    df_m_latest['Article'] = df_m_latest.iloc[:, 6].apply(standardize_sku)
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budgetspent'])
    df_m_latest['Sold_Val'] = clean_numeric(df_m_latest['Itemssold'])
    
    # DEDUPLICATION RULE: Group by Article only, take first Gender found
    # This ensures one article cannot exist in two different gender rows
    m_gen_col = df_m_latest.columns[4]
    df_m_agg = df_m_latest.groupby('Article').agg({
        m_gen_col: 'first',
        'GMV_Val': 'sum', 
        'Spend_Val': 'sum', 
        'Sold_Val': 'sum'
    }).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)

    # B. Clean Inventory Data
    df_s_raw['Article'] = df_s_raw.iloc[:, 4].apply(standardize_sku)
    stock_cols = [c for c in df_s_raw.columns if 'STOCK' in c.upper()]
    for col in stock_cols:
        df_s_raw[col] = clean_numeric(df_s_raw[col])
    
    df_s_pivot = df_s_raw.groupby('Article')[stock_cols].sum().reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)

    # C. Merge & Velocity
    df = pd.merge(df_m_agg, df_s_pivot[['Article', 'Total_Stock']], on='Article', how='left').fillna(0)
    df['Daily_Velocity'] = df['Sold_Val'] / 7
    df['Days_Stock_Left'] = df['Total_Stock'] / df['Daily_Velocity'].replace(0, 0.001)

    # D. STRICT TIERING (Mutually Exclusive)
    def assign_tier(row):
        # 1. Check TOP first
        if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas:
            return 'TOP'
        # 2. Check MEDIUM only if TOP failed
        elif row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas:
            return 'MEDIUM'
        # 3. Everything else is LOW
        else:
            return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)
    df['Campaign'] = df[m_gen_col].apply(lambda x: 'FEMALE' if 'dam' in str(x).lower() else 'MALE_UNISEX_KIDS')

    # --- 4. DASHBOARD OUTPUT ---
    st.header("📊 Campaign Summary (Strict Unique Articles)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Unique Articles", len(df))
    c2.metric("TOP Articles", len(df[df['Tier']=='TOP']))
    c3.metric("MEDIUM Articles", len(df[df['Tier']=='MEDIUM']))
    c4.metric("LOW Articles", len(df[df['Tier']=='LOW']))

    st.divider()
    
    # STOCK WARNINGS
    warnings = df[(df['Tier'] == 'TOP') & (df['Days_Stock_Left'] < days_threshold) & (df['Sold_Val'] > 0)]
    if not warnings.empty:
        st.error(f"🔥 STOCK ALERT: {len(warnings)} TOP Articles running out!")
        st.dataframe(warnings[['Article', 'Campaign', 'Total_Stock', 'Sold_Val', 'Days_Stock_Left']], use_container_width=True)

    # EXPORT BUCKETS
    for group in ['FEMALE', 'MALE_UNISEX_KIDS']:
        st.subheader(f"📂 {group} Campaign Tiers")
        cols = st.columns(3)
        for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
            with cols[i]:
                subset = df[(df['Campaign'] == group) & (df['Tier'] == tier)]
                skus = subset['Article'].unique().tolist()
                st.markdown(f"**{tier}** ({len(skus)})")
                st.text_area("SKUs", ",".join(skus), height=150, key=f"t_{group}_{tier}", label_visibility="collapsed")
                csv = pd.DataFrame(skus).to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Export", csv, f"{group}_{tier}.csv", key=f"d_{group}_{tier}")

else:
    st.info("👋 Upload your files to generate unique tier lists.")
