import streamlit as st
import pandas as pd
import io

# --- Page Setup ---
st.set_page_config(page_title="Zalando Marketing Specialist", layout="wide")
st.title("🎯 Swedemount Campaign Optimizer")
st.markdown("### Matching Marketing (Col G) to Inventory (Col E)")

# --- 1. ROBUST DATA CLEANING ---
def clean_numeric(series):
    """Parses European decimals (1.454,95) into numbers"""
    s = series.astype(str).str.strip().str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def standardize_sku(sku):
    """Standardizes SKU to 13-char Article Config ID (e.g., 00F11N000-Q11)"""
    s = str(sku).strip().upper().replace('.0', '')
    # Truncate size-specific SKUs to Article level (usually the first 13 characters)
    if '-' in s:
        parts = s.split('-')
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1][:3]}"
    return s

def load_csv(file):
    if file is None: return None
    raw_data = file.read(20000)
    file.seek(0)
    try: sample = raw_data.decode('utf-8')
    except: sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1')

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("📂 Upload Reports")
    z_marketing = st.file_uploader("1. Swedemount Marketing File", type="csv")
    stock_file = st.file_uploader("2. Inventory/Stock File", type="csv")
    
    st.divider()
    st.header("🏆 Strategy Thresholds")
    t_stock = st.number_input("Min Stock (Article)", value=10)
    t_roas = st.number_input("Min ROAS", value=4.0)

# --- 3. THE DATA ENGINE ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    # --- A. MARKETING (Column G / Index 6) ---
    # Filter for Latest Week
    df_m = df_m_raw[df_m_raw.iloc[:, 0].astype(str).str.contains('20', na=False)].copy()
    latest_week = clean_numeric(df_m.iloc[:, 2]).max() # Column C
    df_m_latest = df_m[clean_numeric(df_m.iloc[:, 2]) == latest_week].copy()
    
    # Use Column G (Index 6) for SKU
    df_m_latest['Article'] = df_m_latest.iloc[:, 6].apply(standardize_sku)
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budgetspent'])
    df_m_latest['Wish_Val'] = clean_numeric(df_m_latest['Addtowishlist'])
    
    # Aggregate Marketing by Article
    df_m_agg = df_m_latest.groupby(['Article', 'Gender']).agg({
        'GMV_Val': 'sum', 'Spend_Val': 'sum', 'Wish_Val': 'sum'
    }).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)

    # --- B. INVENTORY (Column E / Index 4) ---
    # Use Column E (Index 4) for SKU
    df_s_raw['Article'] = df_s_raw.iloc[:, 4].apply(standardize_sku)
    
    # Dynamically find stock columns (ZFS and PF)
    stock_cols = [c for c in df_s_raw.columns if 'STOCK' in c.upper()]
    for col in stock_cols:
        df_s_raw[col] = clean_numeric(df_s_raw[col])
    
    # PIVOT: Summarize total stock by Article
    df_s_pivot = df_s_raw.groupby('Article')[stock_cols].sum().reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)

    # --- C. SYNC / JOIN ---
    df = pd.merge(df_m_agg, df_s_pivot[['Article', 'Total_Stock']], on='Article', how='left').fillna(0)

    # --- D. TIERING LOGIC ---
    def categorize(row):
        if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas:
            return 'TOP'
        elif row['Total_Stock'] >= 5 and row['ROAS_Actual'] >= 2.0:
            return 'MEDIUM'
        else:
            return 'LOW'

    df['Tier'] = df.apply(categorize, axis=1)
    df['Campaign'] = df['Gender'].apply(lambda x: 'FEMALE' if str(x).strip().capitalize() == 'Damen' else 'MALE_UNISEX_KIDS')

    # --- 4. OUTPUT ---
    st.header("📊 Performance Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total GMV", f"€{df['GMV_Val'].sum():,.0f}")
    c2.metric("Overall ROAS", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.0")
    c3.metric("Matched Articles", len(df[df['Total_Stock'] > 0]))

    # EXPORT BINS
    for g in ['FEMALE', 'MALE_UNISEX_KIDS']:
        st.subheader(f"📂 {g} Campaigns")
        cols = st.columns(3)
        for i, t in enumerate(['TOP', 'MEDIUM', 'LOW']):
            with cols[i]:
                subset = df[(df['Campaign'] == g) & (df['Tier'] == t)]
                skus = subset['Article'].unique().tolist()
                st.markdown(f"**{t}** ({len(skus)})")
                st.text_area("SKUs", ",".join(skus), height=150, key=f"t_{g}_{t}", label_visibility="collapsed")
                csv = pd.DataFrame(skus).to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Export", csv, f"{g}_{t}.csv", key=f"d_{g}_{t}")

    # DEBUG TABLE
    with st.expander("🔍 Match Diagnostic (View Full Data)"):
        st.write("Check if Column G SKUs match Column E SKUs below:")
        st.dataframe(df[['Article', 'Total_Stock', 'ROAS_Actual', 'Tier']], use_container_width=True)

else:
    st.warning("👋 Upload the Marketing File and Inventory File to activate the matching engine.")
