import streamlit as st
import pandas as pd
import io

# --- Page Configuration ---
st.set_page_config(page_title="Zalando Marketing Specialist", layout="wide")
st.title("🚀 Swedemount Campaign Tiering Tool")
st.markdown("### Sorting Articles into Female vs. Male/Unisex Campaigns")

# --- 1. DATA CLEANING UTILITIES ---
def clean_numeric(series):
    """Handles European formatting: 1.454,95 -> 1454.95"""
    s = series.astype(str).str.strip().str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def standardize_sku(sku):
    """Truncates SKU to the 13-character Config ID for matching"""
    s = str(sku).strip().upper().replace('.0', '')
    if '-' in s:
        parts = s.split('-')
        if len(parts) >= 2:
            # Matches format: 00F11N000-Q11
            return f"{parts[0]}-{parts[1][:3]}"
    return s

def load_csv(file):
    """Detects delimiter and encoding for European files"""
    if file is None: return None
    raw_data = file.read(30000)
    file.seek(0)
    try: sample = raw_data.decode('utf-8')
    except: sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1')

# --- 2. SIDEBAR: THRESHOLDS ---
with st.sidebar:
    st.header("📂 Data Upload")
    z_marketing = st.file_uploader("1. Swedemount Marketing File", type="csv")
    stock_file = st.file_uploader("2. Inventory File (47a2...)", type="csv")
    
    st.divider()
    st.header("🏆 TOP Tier Thresholds")
    t_stock = st.number_input("Min Stock (TOP Article)", value=10)
    t_roas = st.number_input("Min ROAS (TOP Article)", value=4.0)

    st.header("🥈 MEDIUM Tier Thresholds")
    m_stock = st.number_input("Min Stock (MED Article)", value=5)
    m_roas = st.number_input("Min ROAS (MED Article)", value=2.0)

# --- 3. DATA ENGINE ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    # A. Clean Marketing Data (Col G / Index 6)
    # Extract year/week to find latest
    df_m = df_m_raw[df_m_raw.iloc[:, 0].astype(str).str.contains('20', na=False)].copy()
    latest_week = clean_numeric(df_m.iloc[:, 2]).max()
    df_m_latest = df_m[clean_numeric(df_m.iloc[:, 2]) == latest_week].copy()
    
    # standardize Article Key
    df_m_latest['Article'] = df_m_latest.iloc[:, 6].apply(standardize_sku)
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budgetspent'])
    
    # Pivot Marketing by Article and Gender
    # Gender is usually at Index 4 (Damen, Herren, etc.)
    m_gen_col = df_m_latest.columns[4]
    df_m_agg = df_m_latest.groupby(['Article', m_gen_col]).agg({
        'GMV_Val': 'sum', 'Spend_Val': 'sum'
    }).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)

    # B. Clean Inventory Data (Col E / Index 4)
    df_s_raw['Article'] = df_s_raw.iloc[:, 4].apply(standardize_sku)
    stock_cols = [c for c in df_s_raw.columns if 'STOCK' in c.upper()]
    for col in stock_cols:
        df_s_raw[col] = clean_numeric(df_s_raw[col])
    
    # Pivot Inventory to Article level
    df_s_pivot = df_s_raw.groupby('Article')[stock_cols].sum().reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)

    # C. Merge
    df = pd.merge(df_m_agg, df_s_pivot[['Article', 'Total_Stock']], on='Article', how='left').fillna(0)

    # D. Categorization Logic
    def assign_tier(row):
        if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas:
            return 'TOP'
        elif row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas:
            return 'MEDIUM'
        else:
            return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)

    # E. Campaign Segmentation Logic
    # Mapping 'Damen' -> Female, everything else -> Male/Unisex/Kids
    def map_campaign(gender_val):
        g = str(gender_val).strip().lower()
        if 'dam' in g or 'fem' in g:
            return 'FEMALE'
        return 'MALE_UNISEX_KIDS'

    df['Campaign'] = df[m_gen_col].apply(map_campaign)

    # --- 4. DASHBOARD: BUCKET OVERVIEW ---
    st.header("📋 Campaign Distribution")
    
    # Create a small summary table for quick checking
    summary = df.groupby(['Campaign', 'Tier']).size().unstack(fill_value=0)
    # Ensure all columns exist
    for t in ['TOP', 'MEDIUM', 'LOW']:
        if t not in summary.columns: summary[t] = 0
    st.table(summary[['TOP', 'MEDIUM', 'LOW']])

    st.divider()

    # --- 5. THE 6 CAMPAIGN BUCKETS ---
    campaign_order = ['FEMALE', 'MALE_UNISEX_KIDS']
    tier_order = ['TOP', 'MEDIUM', 'LOW']

    for group in campaign_order:
        st.subheader(f"🚀 {group} Campaigns")
        cols = st.columns(3)
        for i, tier in enumerate(tier_order):
            with cols[i]:
                # Filter specifically for this Campaign + Tier
                subset = df[(df['Campaign'] == group) & (df['Tier'] == tier)]
                sku_list = subset['Article'].unique().tolist()
                
                count = len(sku_list)
                st.markdown(f"**{tier} {group}**")
                st.metric("Total Articles", count)
                
                # SKU string for copy-pasting
                sku_str = ",".join(sku_list)
                st.text_area("SKU List", value=sku_str, height=150, key=f"area_{group}_{tier}", label_visibility="collapsed")
                
                # CSV Export
                csv = pd.DataFrame(sku_list).to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Download CSV", csv, f"{group}_{tier}.csv", key=f"btn_{group}_{tier}")

    # --- 6. DIAGNOSTIC ---
    st.divider()
    with st.expander("🔍 Diagnostic Overview (Full Table)"):
        st.dataframe(df[['Article', 'Campaign', 'Tier', 'Total_Stock', 'ROAS_Actual']], use_container_width=True)

else:
    st.info("👋 To begin, upload your Swedemount Marketing File and the Inventory File (47a2...).")
