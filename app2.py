import streamlit as st
import pandas as pd
import io

# --- Page Setup ---
st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("🚀 Swedemount Expert: Final Campaign Sync")
st.markdown("### Integrated: Article Sync, Stock Warnings, and Strict Gender Isolation")

# --- 1. UTILITIES (The "Engine") ---
def clean_numeric(series):
    """Handles European formatting: 1.454,95 -> 1454.95"""
    s = series.astype(str).str.strip().str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def standardize_sku(sku):
    """Truncates SKU to the 13-character Config ID (00F11N000-Q11)"""
    s = str(sku).strip().upper().replace('.0', '')
    if '-' in s:
        parts = s.split('-')
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1][:3]}"
    return s

def load_csv(file):
    """Auto-detects delimiter and encoding for European CSVs"""
    if file is None: return None
    raw_data = file.read(40000)
    file.seek(0)
    try: sample = raw_data.decode('utf-8')
    except: sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1')

# --- 2. SIDEBAR: THE STEERING WHEEL ---
with st.sidebar:
    st.header("📂 Data Upload")
    z_marketing = st.file_uploader("1. Swedemount SKU Report (ZMS)", type="csv")
    stock_file = st.file_uploader("2. Inventory File (47a2...)", type="csv")
    
    st.divider()
    st.header("🏆 TOP Tier Thresholds")
    t_stock = st.number_input("Min Stock (TOP Article)", value=10)
    t_roas = st.number_input("Min ROAS (TOP Article)", value=4.0)
    
    st.header("🥈 MEDIUM Tier Thresholds")
    m_stock = st.number_input("Min Stock (MED Article)", value=5)
    m_roas = st.number_input("Min ROAS (MED Article)", value=2.0)

    st.header("⚠️ Stock Warning")
    days_threshold = st.slider("Alert if Stock Days less than:", 1, 10, 3)

# --- 3. DATA PROCESSING ENGINE ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    # A. Clean Marketing Data & Filter for Latest Week
    df_m = df_m_raw[df_m_raw.iloc[:, 0].astype(str).str.contains('20', na=False)].copy()
    latest_week = clean_numeric(df_m.iloc[:, 2]).max()
    df_m_latest = df_m[clean_numeric(df_m.iloc[:, 2]) == latest_week].copy()
    
    # Generate Article IDs
    df_m_latest['Article'] = df_m_latest.iloc[:, 6].apply(standardize_sku)
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budgetspent'])
    df_m_latest['Sold_Val'] = clean_numeric(df_m_latest['Itemssold'])
    
    # B. STRICT GENDER ISOLATION RULE
    # If an article is labeled 'Damen' anywhere in the report, it is locked to FEMALE
    def detect_group(row):
        g = str(row).lower()
        return 'FEMALE' if 'dam' in g or 'fem' in g else 'MALE_UNISEX_KIDS'
    
    df_m_latest['Group_Draft'] = df_m_latest.iloc[:, 4].apply(detect_group)
    
    # Priority Sorting: 'FEMALE' comes before 'MALE' alphabetically, so .first() grabs it
    gender_lock = df_m_latest.sort_values('Group_Draft').groupby('Article')['Group_Draft'].first().reset_index()

    # C. Aggregate Marketing Metrics to Article level
    df_m_agg = df_m_latest.groupby('Article').agg({
        'GMV_Val': 'sum', 
        'Spend_Val': 'sum', 
        'Sold_Val': 'sum'
    }).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)
    
    # Attach the Locked Gender Group
    df_m_agg = pd.merge(df_m_agg, gender_lock, on='Article', how='left')

    # D. Clean & Pivot Inventory Data
    df_s_raw['Article'] = df_s_raw.iloc[:, 4].apply(standardize_sku)
    stock_cols = [c for c in df_s_raw.columns if 'STOCK' in c.upper()]
    for col in stock_cols:
        df_s_raw[col] = clean_numeric(df_s_raw[col])
    
    df_s_pivot = df_s_raw.groupby('Article')[stock_cols].sum().reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)

    # E. Merge & Tiering Logic
    df = pd.merge(df_m_agg, df_s_pivot[['Article', 'Total_Stock']], on='Article', how='left').fillna(0)
    
    # Days of Stock = Total Stock / (Weekly Sales / 7)
    df['Daily_Velocity'] = df['Sold_Val'] / 7
    df['Days_Left'] = df['Total_Stock'] / df['Daily_Velocity'].replace(0, 0.001)

    def assign_tier(row):
        if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas: return 'TOP'
        elif row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas: return 'MEDIUM'
        return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)

    # --- 4. DASHBOARD OUTPUT ---
    st.header("📊 Final Campaign Distribution")
    
    # Summary Metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Unique Articles", len(df))
    m2.metric("Overall ROAS", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.0")
    m3.metric("Stock Alerts", len(df[(df['Tier'] == 'TOP') & (df['Days_Left'] < days_threshold) & (df['Sold_Val'] > 0)]))
    m4.metric("Matched Inventory", f"{df['Total_Stock'].sum():,.0f} units")

    # STOCK WARNING SECTION
    warnings = df[(df['Tier'] == 'TOP') & (df['Days_Left'] < days_threshold) & (df['Sold_Val'] > 0)]
    if not warnings.empty:
        st.error(f"🔥 STOCK ALERT: {len(warnings)} TOP Articles running out fast!")
        st.dataframe(warnings[['Article', 'Group_Draft', 'Total_Stock', 'Sold_Val', 'Days_Left']], use_container_width=True)

    st.divider()

    # THE 6 EXPORT BUCKETS
    for group in ['FEMALE', 'MALE_UNISEX_KIDS']:
        st.subheader(f"📂 {group} Campaign Tiers")
        cols = st.columns(3)
        for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
            with cols[i]:
                # Strictest filter: Group AND Tier
                subset = df[(df['Group_Draft'] == group) & (df['Tier'] == tier)]
                skus = subset['Article'].unique().tolist()
                
                st.markdown(f"**{tier} {group}**")
                st.metric("Articles", len(skus))
                st.text_area("SKU List", ",".join(skus), height=150, key=f"t_{group}_{tier}", label_visibility="collapsed")
                
                csv = pd.DataFrame(skus).to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Export CSV", csv, f"{group}_{tier}.csv", key=f"d_{group}_{tier}")

    # --- 5. LOGIC INSPECTOR ---
    st.divider()
    with st.expander("🔍 Deep Dive Diagnostic"):
        st.dataframe(df[['Article', 'Group_Draft', 'Tier', 'Total_Stock', 'Days_Left', 'ROAS_Actual']], use_container_width=True)

else:
    st.info("👋 Everything is ready. Just upload your Marketing and Inventory files to begin.")
