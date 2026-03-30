import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("🚀 Swedemount Campaign Optimizer")

def clean_numeric(series):
    s = series.astype(str).str.strip()
    s = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def get_article_key(sku):
    sku = str(sku).strip()
    # Ensure we use the 13-character Article/Config SKU
    if len(sku) > 13 and '-' in sku:
        return sku[:13]
    return sku

def load_csv(file):
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
    st.header("📂 Data Sources")
    z_marketing = st.file_uploader("1. Swedemount Marketing File (Primary)", type="csv")
    stock_file = st.file_uploader("2. Inventory/Stock File", type="csv")
    curr_attalos = st.file_uploader("3. Attalos Profit File", type="csv")
    prev_attalos = st.file_uploader("4. Previous Week (Optional)", type="csv")
    
    st.divider()
    st.header("⚙️ Strategy Thresholds")
    top_stock = st.number_input("Min Stock for TOP", value=15)
    top_profit = st.number_input("Min Net Profit (€) for TOP", value=8.0)

# --- CORE LOGIC ---
if z_marketing and stock_file and curr_attalos:
    df_m = load_csv(z_marketing)
    df_s = load_csv(stock_file)
    df_p = load_csv(curr_attalos)
    
    # 1. PROCESS MARKETING FILE (THE BASE)
    m_sku_col = 'ConfigSKU' if 'ConfigSKU' in df_m.columns else df_m.columns[6]
    # Filter out 'undefined' or empty SKUs from marketing
    df_m = df_m[df_m[m_sku_col].notna() & (df_m[m_sku_col] != 'undefined')]
    
    df_m['Article_Key'] = df_m[m_sku_col].apply(get_article_key)
    df_m['GMV_Val'] = clean_numeric(df_m['GMV'])
    df_m['Spend_Val'] = clean_numeric(df_m['Budgetspent'])
    
    # Aggregate Marketing to Article Level
    # We keep 'Gender' from the marketing file here
    df_m_agg = df_m.groupby(['Article_Key', 'Gender']).agg({
        'GMV_Val': 'sum', 
        'Spend_Val': 'sum'
    }).reset_index()

    # 2. PROCESS STOCK (Summarize to Article)
    s_sku_col = next((c for c in df_s.columns if 'SKU' in c.upper()), df_s.columns[0])
    df_s['Article_Key'] = df_s[s_sku_col].apply(get_article_key)
    df_s['ZFS_Clean'] = clean_numeric(df_s['ZFS_Stock']) if 'ZFS_Stock' in df_s.columns else 0
    df_s['PF_Clean'] = clean_numeric(df_s['PF_Stock']) if 'PF_Stock' in df_s.columns else 0
    
    df_s_agg = df_s.groupby('Article_Key').agg({
        'ZFS_Clean': 'sum', 
        'PF_Clean': 'sum'
    }).reset_index()
    df_s_agg['Total_Stock'] = df_s_agg['ZFS_Clean'] + df_s_agg['PF_Clean']

    # 3. PROCESS PROFIT
    p_sku_col = next((c for c in df_p.columns if 'SKU' in c.upper()), df_p.columns[0])
    p_profit_col = next((c for c in df_p.columns if any(k in c.upper() for k in ['PROFIT', 'MARGIN'])), df_p.columns[-1])
    df_p['Article_Key'] = df_p[p_sku_col].apply(get_article_key)
    df_p['Profit_Clean'] = clean_numeric(df_p[p_profit_col])

    # 4. FINAL MERGE (Driven by Marketing File)
    df = pd.merge(df_m_agg, df_s_agg, on='Article_Key', how='left')
    df = pd.merge(df, df_p[['Article_Key', 'Profit_Clean']], on='Article_Key', how='left')

    # 5. NEW ARRIVAL CHECK
    new_articles = set()
    if prev_attalos:
        df_prev = load_csv(prev_attalos)
        df_prev['Article_Key'] = df_prev[p_sku_col].apply(get_article_key)
        new_articles = set(df_p['Article_Key']) - set(df_prev['Article_Key'])

    # 6. TIER LOGIC
    def assign_tier(row):
        if row['Article_Key'] in new_articles: return 'TEST (NEW)'
        if row['Total_Stock'] >= top_stock and row['Profit_Clean'] >= top_profit: return 'TOP'
        if row['Total_Stock'] >= 5 and row['Profit_Clean'] > 0: return 'MEDIUM'
        return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)

    # 7. GENDER GROUPING (Damen vs Herren/Kinder/Unisex)
    def map_gender(val):
        val = str(val).strip().capitalize()
        if val == 'Damen': return 'FEMALE'
        return 'MALE_UNISEX'
    
    df['Campaign_Group'] = df['Gender'].apply(map_gender)

    # --- DASHBOARD ---
    st.header("📊 Marketing-Driven Performance")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total GMV", f"€{df['GMV_Val'].sum():,.0f}")
    m2.metric("Total Spend", f"€{df['Spend_Val'].sum():,.0f}")
    m3.metric("ROAS", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.00")
    m4.metric("Active Articles", len(df))

    st.divider()
    
    # 8. THE 6 CAMPAIGN BUCKETS
    tiers = ['TOP', 'MEDIUM', 'LOW', 'TEST (NEW)']
    for group in ['FEMALE', 'MALE_UNISEX']:
        st.subheader(f"📂 {group} Campaigns")
        cols = st.columns(4)
        for i, tier in enumerate(tiers):
            with cols[i]:
                subset = df[(df['Campaign_Group'] == group) & (df['Tier'] == tier)]
                st.markdown(f"**{tier}**")
                st.metric("Articles", len(subset))
                
                sku_list = subset['Article_Key'].unique().tolist()
                sku_str = ",".join(sku_list)
                st.text_area("Copy SKUs:", value=sku_str, height=150, key=f"t_{group}_{tier}", label_visibility="collapsed")
                
                csv = pd.DataFrame(sku_list).to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Export", csv, f"{group}_{tier}.csv", key=f"d_{group}_{tier}")

else:
    st.info("👋 To start, upload the Swedemount Marketing File, Inventory, and Attalos Profit data.")
