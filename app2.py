import streamlit as st
import pandas as pd

st.set_page_config(page_title="Zalando Campaign specialist", layout="wide")
st.title("🎯 Zalando Marketing: KPI-Based Tiering")

# --- Helper: Numeric Cleaning ---
def clean_numeric(series):
    s = series.astype(str).str.strip()
    s = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

# --- Helper: Article Aggregator ---
def get_article_key(sku):
    sku = str(sku).strip()
    return sku[:13] if len(sku) > 13 and '-' in sku else sku

# --- Helper: CSV Loader ---
def load_csv(file):
    if file is None: return None
    raw_data = file.read(20000)
    file.seek(0)
    try: sample = raw_data.decode('utf-8')
    except: sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1')

# --- SIDEBAR: KPI STEERING ---
with st.sidebar:
    st.header("📊 Upload Data")
    z_marketing = st.file_uploader("1. Swedemount Marketing File", type="csv")
    stock_file = st.file_uploader("2. Inventory/Stock File", type="csv")
    curr_attalos = st.file_uploader("3. Attalos Profit File", type="csv")
    
    st.divider()
    st.header("🏆 TOP Tier Thresholds")
    t_stock = st.number_input("Min Stock (TOP)", value=10)
    t_roas = st.number_input("Min ROAS (TOP)", value=4.0)
    t_profit = st.number_input("Min Profit € (TOP)", value=10.0)

    st.header("🥈 MEDIUM Tier Thresholds")
    m_stock = st.number_input("Min Stock (MED)", value=5)
    m_roas = st.number_input("Min ROAS (MED)", value=2.0)
    m_profit = st.number_input("Min Profit € (MED)", value=5.0)

# --- PROCESSING ---
if z_marketing and stock_file and curr_attalos:
    df_m = load_csv(z_marketing)
    df_s = load_csv(stock_file)
    df_p = load_csv(curr_attalos)

    # 1. Base: Swedemount Marketing
    m_sku = 'ConfigSKU' if 'ConfigSKU' in df_m.columns else df_m.columns[6]
    df_m['Article'] = df_m[m_sku].apply(get_article_key)
    df_m['GMV_Val'] = clean_numeric(df_m['GMV'])
    df_m['Spend_Val'] = clean_numeric(df_m['Budgetspent'])
    
    # Aggregating marketing (handling multiple rows per article)
    df_m_agg = df_m.groupby(['Article', 'Gender']).agg({'GMV_Val':'sum', 'Spend_Val':'sum'}).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)

    # 2. Inventory: Summing all sizes
    s_sku = next((c for c in df_s.columns if 'SKU' in c.upper()), df_s.columns[0])
    df_s['Article'] = df_s[s_sku].apply(get_article_key)
    df_s['ZFS'] = clean_numeric(df_s['ZFS_Stock']) if 'ZFS_Stock' in df_s.columns else 0
    df_s['PF'] = clean_numeric(df_s['PF_Stock']) if 'PF_Stock' in df_s.columns else 0
    df_s_agg = df_s.groupby('Article').agg({'ZFS':'sum', 'PF':'sum'}).reset_index()
    df_s_agg['Total_Stock'] = df_s_agg['ZFS'] + df_s_agg['PF']

    # 3. Profit: Attalos Data
    p_sku = next((c for c in df_p.columns if 'SKU' in c.upper()), df_p.columns[0])
    p_prof = next((c for c in df_p.columns if any(k in c.upper() for k in ['PROFIT', 'MARGIN'])), df_p.columns[-1])
    df_p['Article'] = df_p[p_sku].apply(get_article_key)
    df_p['Profit_Actual'] = clean_numeric(df_p[p_prof])

    # 4. Merge (Left Join on Marketing File)
    df = pd.merge(df_m_agg, df_s_agg[['Article', 'Total_Stock']], on='Article', how='left')
    df = pd.merge(df, df_p[['Article', 'Profit_Actual']], on='Article', how='left').fillna(0)

    # 5. KPI Steering Logic
    def categorize(row):
        # TOP CHECK
        if (row['Total_Stock'] >= t_stock and 
            row['ROAS_Actual'] >= t_roas and 
            row['Profit_Actual'] >= t_profit):
            return 'TOP'
        # MEDIUM CHECK
        elif (row['Total_Stock'] >= m_stock and 
              row['ROAS_Actual'] >= m_roas and 
              row['Profit_Actual'] >= m_profit):
            return 'MEDIUM'
        # DEFAULT
        else:
            return 'LOW'

    df['Tier'] = df.apply(categorize, axis=1)

    # 6. Unified Gender Grouping
    def group_gender(val):
        v = str(val).capitalize()
        if v == 'Damen': return 'FEMALE'
        return 'MALE_UNISEX_KIDS' # Herren, Kinder, Unisex merged

    df['Campaign'] = df['Gender'].apply(group_gender)

    # --- OUTPUT ---
    st.header("🚀 Campaign Tiers")
    
    # Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("TOP Articles", len(df[df['Tier']=='TOP']))
    c2.metric("MEDIUM Articles", len(df[df['Tier']=='MEDIUM']))
    c3.metric("LOW Articles", len(df[df['Tier']=='LOW']))

    st.divider()

    for g in ['FEMALE', 'MALE_UNISEX_KIDS']:
        st.subheader(f"Campaign Group: {g}")
        cols = st.columns(3)
        for i, t in enumerate(['TOP', 'MEDIUM', 'LOW']):
            with cols[i]:
                subset = df[(df['Campaign'] == g) & (df['Tier'] == t)]
                sku_list = subset['Article'].unique().tolist()
                
                st.markdown(f"**{t}** ({len(sku_list)})")
                st.text_area("SKUs", value=",".join(sku_list), height=150, key=f"{g}_{t}", label_visibility="collapsed")
                
                csv = pd.DataFrame(sku_list).to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Export", csv, f"{g}_{t}.csv", key=f"dl_{g}_{t}")

    # --- Debugging Table ---
    with st.expander("🔍 View Merged Data (Check why items are LOW)"):
        st.dataframe(df[['Article', 'Gender', 'Total_Stock', 'ROAS_Actual', 'Profit_Actual', 'Tier']])

else:
    st.info("👋 Upload all three files to see your campaign distribution.")
