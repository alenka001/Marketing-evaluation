import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Zalando Marketing Specialist", layout="wide")
st.title("🚀 Zalando Expert Campaign Dashboard")

def clean_numeric(series):
    """Handles European formatting: 1.454,95 -> 1454.95"""
    s = series.astype(str).str.strip()
    s = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def get_article_key(sku):
    """Summarizes size-level SKUs to Article/Config level (first 13 chars)"""
    sku = str(sku).strip()
    if len(sku) > 13 and '-' in sku:
        return sku[:13]
    return sku

def load_csv(file):
    """Detects delimiter (; or ,) and encoding (UTF-8 or Latin-1)"""
    if file is None: return None
    raw_data = file.read(20000)
    file.seek(0)
    try:
        sample = raw_data.decode('utf-8')
    except UnicodeDecodeError:
        sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    try:
        file.seek(0)
        return pd.read_csv(file, sep=sep, encoding='utf-8')
    except:
        file.seek(0)
        return pd.read_csv(file, sep=sep, encoding='latin-1')

# --- SIDEBAR ---
with st.sidebar:
    st.header("📂 Upload Weekly Data")
    curr_attalos = st.file_uploader("1. Attalos Profit (Current)", type="csv")
    z_marketing = st.file_uploader("2. Zalando SKU Report (Marketing)", type="csv")
    stock_file = st.file_uploader("3. Inventory File (Stock)", type="csv")
    prev_attalos = st.file_uploader("4. Attalos Profit (Previous Week)", type="csv")
    
    st.divider()
    st.header("⚙️ Strategy Thresholds")
    top_stock = st.number_input("Min Article Stock for TOP", value=20)
    top_profit = st.number_input("Min Net Profit (€) for TOP", value=10.0)

# --- CORE LOGIC ---
if curr_attalos and z_marketing and stock_file:
    df_p = load_csv(curr_attalos)
    df_m = load_csv(z_marketing)
    df_s = load_csv(stock_file)
    
    # 1. Process Marketing (Swedemount Report)
    m_sku_col = 'ConfigSKU' if 'ConfigSKU' in df_m.columns else df_m.columns[6]
    df_m['Article_Key'] = df_m[m_sku_col].apply(get_article_key)
    df_m['GMV_Val'] = clean_numeric(df_m['GMV']) if 'GMV' in df_m.columns else 0
    df_m['Spend_Val'] = clean_numeric(df_m['Budgetspent']) if 'Budgetspent' in df_m.columns else 0
    df_m_agg = df_m.groupby('Article_Key').agg({'GMV_Val': 'sum', 'Spend_Val': 'sum'}).reset_index()

    # 2. Process Inventory (Dynamic Column Finding)
    s_sku_col = next((c for c in df_s.columns if 'SKU' in c.upper()), df_s.columns[0])
    # Find Gender column dynamically
    s_gen_col = next((c for c in df_s.columns if any(k in c.upper() for k in ['GENDER', 'GESCHLECHT', 'GENDER'])), None)
    
    df_s['Article_Key'] = df_s[s_sku_col].apply(get_article_key)
    df_s['ZFS_Clean'] = clean_numeric(df_s['ZFS_Stock']) if 'ZFS_Stock' in df_s.columns else 0
    df_s['PF_Clean'] = clean_numeric(df_s['PF_Stock']) if 'PF_Stock' in df_s.columns else 0
    
    # If gender column is missing, assign a dummy 'Unisex' to everything
    if s_gen_col:
        df_s['Gender_Clean'] = df_s[s_gen_col].fillna('Unisex')
    else:
        df_s['Gender_Clean'] = 'Unisex'

    # Summing Stock to Article Level (using the found/created Gender_Clean column)
    df_s_agg = df_s.groupby(['Article_Key', 'Gender_Clean']).agg({'ZFS_Clean': 'sum', 'PF_Clean': 'sum'}).reset_index()
    df_s_agg['Total_Stock'] = df_s_agg['ZFS_Clean'] + df_s_agg['PF_Clean']

    # 3. Process Profit
    p_sku_col = next((c for c in df_p.columns if 'SKU' in c.upper()), df_p.columns[0])
    p_profit_col = next((c for c in df_p.columns if any(k in c.upper() for k in ['PROFIT', 'MARGIN', 'CONTRIBUTION'])), df_p.columns[-1])
    df_p['Article_Key'] = df_p[p_sku_col].apply(get_article_key)
    df_p['Profit_Clean'] = clean_numeric(df_p[p_profit_col])

    # 4. Final Merge
    df = pd.merge(df_s_agg, df_p[['Article_Key', 'Profit_Clean']], on='Article_Key', how='left')
    df = pd.merge(df, df_m_agg, on='Article_Key', how='left')

    # 5. Trend/New Arrival Check
    new_articles = set()
    if prev_attalos:
        df_prev = load_csv(prev_attalos)
        df_prev['Article_Key'] = df_prev[p_sku_col].apply(get_article_key)
        new_articles = set(df_p['Article_Key']) - set(df_prev['Article_Key'])

    # 6. Tiers and Groups
    def assign_tier(row):
        if row['Article_Key'] in new_articles: return 'TEST (NEW)'
        if row['Total_Stock'] >= top_stock and row['Profit_Clean'] >= top_profit: return 'TOP'
        if row['Total_Stock'] >= 5 and row['Profit_Clean'] > 0: return 'MEDIUM'
        return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)
    df['Campaign_Group'] = df['Gender_Clean'].apply(lambda x: 'FEMALE' if any(g in str(x).upper() for g in ['DAM', 'FEMALE', 'WMS']) else 'MALE_UNISEX')

    # --- DASHBOARD DISPLAY ---
    st.header("📊 Weekly Performance Summary")
    m1, m2, m3, m4 = st.columns(4)
    total_gmv = df['GMV_Val'].sum()
    total_spend = df['Spend_Val'].sum()
    m1.metric("Total GMV", f"€{total_gmv:,.0f}")
    m2.metric("Total Spend", f"€{total_spend:,.0f}")
    m3.metric("ROAS", f"{total_gmv/total_spend:.2f}" if total_spend > 0 else "0.00")
    m4.metric("New Articles", len(new_articles))

    st.divider()
    tiers = ['TOP', 'MEDIUM', 'LOW', 'TEST (NEW)']
    for group in ['FEMALE', 'MALE_UNISEX']:
        st.subheader(f"📂 {group} Campaign Tiers")
        cols = st.columns(4)
        for i, tier in enumerate(tiers):
            with cols[i]:
                subset = df[(df['Campaign_Group'] == group) & (df['Tier'] == tier)]
                st.markdown(f"**{tier}** ({len(subset)})")
                sku_list = subset['Article_Key'].unique().tolist()
                sku_str = ",".join(sku_list)
                st.text_area("Copy SKUs:", value=sku_str, height=100, key=f"t_{group}_{tier}", label_visibility="collapsed")
                csv = pd.DataFrame(sku_list).to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Export CSV", csv, f"{group}_{tier}.csv", key=f"d_{group}_{tier}")

else:
    st.info("👋 Dashboard Ready. Please upload Attalos, Swedemount SKU Report, and Inventory files to start.")
