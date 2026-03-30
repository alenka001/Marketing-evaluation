import streamlit as st
import pandas as pd
import io

# --- Page Configuration ---
st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("🚀 Swedemount Campaign Optimizer")
st.markdown("### Weekly Article Tiering & Performance Dashboard")

# --- 1. UTILITY FUNCTIONS ---
def clean_numeric(series):
    """Handles European formatting: 1.454,95 -> 1454.95"""
    s = series.astype(str).str.strip().str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def get_article_key(sku):
    """Truncates size-level SKUs to the 13-character Article/Config level"""
    sku = str(sku).strip()
    return sku[:13] if len(sku) > 13 and '-' in sku else sku

def load_csv(file):
    """Detects delimiter and encoding automatically"""
    if file is None: return None
    raw_data = file.read(20000)
    file.seek(0)
    try: sample = raw_data.decode('utf-8')
    except: sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1')

# --- 2. SIDEBAR: UPLOADS & KPI THRESHOLDS ---
with st.sidebar:
    st.header("📂 Step 1: Upload Data")
    z_marketing = st.file_uploader("Swedemount SKU Report (ZMS)", type="csv")
    stock_file = st.file_uploader("Inventory/Stock File", type="csv")
    curr_attalos = st.file_uploader("Attalos Profit File", type="csv")
    
    st.divider()
    st.header("🏆 Step 2: TOP Tier Thresholds")
    t_stock = st.number_input("Min Stock (TOP)", value=10)
    t_roas = st.number_input("Min ROAS (TOP)", value=4.0)
    t_profit = st.number_input("Min Profit € (TOP)", value=10.0)

    st.header("🥈 Step 3: MEDIUM Tier Thresholds")
    m_stock = st.number_input("Min Stock (MED)", value=5)
    m_roas = st.number_input("Min ROAS (MED)", value=2.0)
    m_profit = st.number_input("Min Profit € (MED)", value=5.0)

# --- 3. DATA PROCESSING ENGINE ---
if z_marketing and stock_file and curr_attalos:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)
    df_p_raw = load_csv(curr_attalos)

    # A. Filter for Latest Week in Marketing Report
    df_m = df_m_raw[df_m_raw['Year'].astype(str).str.contains('20', na=False)].copy()
    df_m['Year_Num'] = clean_numeric(df_m['Year'])
    df_m['Week_Num'] = clean_numeric(df_m['Week'])
    
    latest_year = df_m['Year_Num'].max()
    latest_week = df_m[df_m['Year_Num'] == latest_year]['Week_Num'].max()
    
    st.info(f"📅 Analyzing Latest Data: Year {int(latest_year)}, Week {int(latest_week)}")
    df_m_latest = df_m[(df_m['Year_Num'] == latest_year) & (df_m['Week_Num'] == latest_week)].copy()
    
    # B. Aggregate Marketing by Article
    m_sku = 'ConfigSKU' if 'ConfigSKU' in df_m_latest.columns else df_m_latest.columns[6]
    df_m_latest['Article'] = df_m_latest[m_sku].apply(get_article_key)
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budgetspent'])
    df_m_latest['Wishlist_Val'] = clean_numeric(df_m_latest['Addtowishlist'])
    
    df_m_agg = df_m_latest.groupby(['Article', 'Gender']).agg({
        'GMV_Val': 'sum',
        'Spend_Val': 'sum',
        'Wishlist_Val': 'sum'
    }).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)

    # C. Aggregate Stock by Article
    s_sku = next((c for c in df_s_raw.columns if 'SKU' in c.upper()), df_s_raw.columns[0])
    df_s_raw['Article'] = df_s_raw[s_sku].apply(get_article_key)
    df_s_raw['ZFS'] = clean_numeric(df_s_raw['ZFS_Stock']) if 'ZFS_Stock' in df_s_raw.columns else 0
    df_s_raw['PF'] = clean_numeric(df_s_raw['PF_Stock']) if 'PF_Stock' in df_s_raw.columns else 0
    df_s_agg = df_s_raw.groupby('Article').agg({'ZFS':'sum', 'PF':'sum'}).reset_index()
    df_s_agg['Total_Stock'] = df_s_agg['ZFS'] + df_s_agg['PF']

    # D. Aggregate Profit by Article
    p_sku = next((c for c in df_p_raw.columns if 'SKU' in c.upper()), df_p_raw.columns[0])
    p_prof = next((c for c in df_p_raw.columns if any(k in c.upper() for k in ['PROFIT', 'MARGIN'])), df_p_raw.columns[-1])
    df_p_raw['Article'] = df_p_raw[p_sku].apply(get_article_key)
    df_p_raw['Profit_Actual'] = clean_numeric(df_p_raw[p_prof])

    # E. Join All Datasets
    df = pd.merge(df_m_agg, df_s_agg[['Article', 'Total_Stock']], on='Article', how='left')
    df = pd.merge(df, df_p_raw[['Article', 'Profit_Actual']], on='Article', how='left').fillna(0)

    # F. Tiering Logic + Reasoning
    def categorize(row):
        if (row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas and row['Profit_Actual'] >= t_profit):
            return 'TOP', 'Meets all criteria'
        elif (row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas and row['Profit_Actual'] >= m_profit):
            return 'MEDIUM', 'Meets Medium criteria'
        else:
            reasons = []
            if row['Total_Stock'] < m_stock: reasons.append(f"Stock < {m_stock}")
            if row['ROAS_Actual'] < m_roas: reasons.append(f"ROAS < {m_roas}")
            if row['Profit_Actual'] < m_profit: reasons.append(f"Profit < {m_profit}")
            return 'LOW', " | ".join(reasons)

    df[['Tier', 'Low_Reason']] = df.apply(lambda r: pd.Series(categorize(r)), axis=1)

    # G. Gender Grouping
    df['Campaign'] = df['Gender'].apply(lambda x: 'FEMALE' if str(x).capitalize() == 'Damen' else 'MALE_UNISEX_KIDS')

    # --- 4. DASHBOARD: TOP METRICS ---
    st.header("📊 Weekly Sales Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total GMV", f"€{df['GMV_Val'].sum():,.0f}")
    c2.metric("Ad Spend", f"€{df['Spend_Val'].sum():,.0f}")
    c3.metric("ROAS", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.00")
    c4.metric("Wishlist Adds", f"{df['Wishlist_Val'].sum():,.0f}")

    # --- 5. WISHLIST FAVORITES ---
    st.divider()
    st.subheader("💖 Customer Wishlist Favorites (High Intent)")
    st.table(df.sort_values(by='Wishlist_Val', ascending=False).head(5)[['Article', 'Gender', 'Wishlist_Val', 'Total_Stock', 'ROAS_Actual']])

    # --- 6. CAMPAIGN EXPORTS ---
    st.divider()
    for g in ['FEMALE', 'MALE_UNISEX_KIDS']:
        st.subheader(f"📂 {g} Campaign Tiers")
        cols = st.columns(3)
        for i, t in enumerate(['TOP', 'MEDIUM', 'LOW']):
            with cols[i]:
                subset = df[(df['Campaign'] == g) & (df['Tier'] == t)]
                sku_list = subset['Article'].unique().tolist()
                st.markdown(f"**{t}** ({len(sku_list)})")
                st.text_area("SKUs", value=",".join(sku_list), height=150, key=f"txt_{g}_{t}", label_visibility="collapsed")
                csv = pd.DataFrame(sku_list).to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Export CSV", csv, f"{g}_{t}.csv", key=f"btn_{g}_{t}")

    # --- 7. DEEP DIVE ---
    st.divider()
    with st.expander("🔍 Deep Dive: Logic Inspector"):
        st.write("Use this table to see exactly why articles are in 'LOW'.")
        st.dataframe(df[['Article', 'Campaign', 'Total_Stock', 'ROAS_Actual', 'Profit_Actual', 'Tier', 'Low_Reason']], use_container_width=True)

else:
    st.warning("⚠️ Please upload all three files in the sidebar to activate the dashboard.")
