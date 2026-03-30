import streamlit as st
import pandas as pd
import io

# --- Page Config ---
st.set_page_config(page_title="Zalando Marketing Specialist", layout="wide")
st.title("🎯 Swedemount Campaign Optimizer")

# --- 1. ROBUST NUMERIC & SKU CLEANING ---
def clean_numeric(series):
    """Handles European formatting: 1.454,95 -> 1454.95"""
    s = series.astype(str).str.strip().str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def to_article(sku):
    """Pivots SKU level to Article level (Config SKU)"""
    sku = str(sku).strip()
    # Zalando Config SKUs are usually 13 chars (e.g., 00F11N000-Q11)
    # If longer, it's a simple SKU with size suffix
    if len(sku) > 13 and '-' in sku:
        return sku[:13]
    return sku

def load_csv(file):
    if file is None: return None
    raw_data = file.read(20000)
    file.seek(0)
    try: sample = raw_data.decode('utf-8')
    except: sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1')

# --- 2. SIDEBAR: KPI STEERING ---
with st.sidebar:
    st.header("📂 Upload Reports")
    z_marketing = st.file_uploader("1. Swedemount SKU Report (ZMS)", type="csv")
    stock_file = st.file_uploader("2. Inventory File (SKU Level)", type="csv")
    curr_attalos = st.file_uploader("3. Attalos Profit File (SKU Level)", type="csv")
    
    st.divider()
    st.header("🏆 TOP Tier Thresholds")
    t_stock = st.number_input("Min Total Stock (Article)", value=15)
    t_roas = st.number_input("Min ROAS", value=4.0)
    t_profit = st.number_input("Min Article Profit €", value=10.0)

    st.header("🥈 MEDIUM Tier Thresholds")
    m_stock = st.number_input("Min Total Stock (Article)", value=5)
    m_roas = st.number_input("Min ROAS", value=2.0)
    m_profit = st.number_input("Min Article Profit €", value=5.0)

# --- 3. THE DATA ENGINE ---
if z_marketing and stock_file and curr_attalos:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)
    df_p_raw = load_csv(curr_attalos)

    # A. MARKETING: Filter for Latest Week & Pivot to Article
    df_m = df_m_raw[df_m_raw['Year'].astype(str).str.contains('20', na=False)].copy()
    df_m['Year_N'] = clean_numeric(df_m['Year'])
    df_m['Week_N'] = clean_numeric(df_m['Week'])
    
    latest_y = df_m['Year_N'].max()
    latest_w = df_m[df_m['Year_N'] == latest_y]['Week_N'].max()
    st.info(f"📅 Analyzing: Year {int(latest_y)}, Week {int(latest_w)}")
    
    df_m_latest = df_m[(df_m['Year_N'] == latest_y) & (df_m['Week_N'] == latest_w)].copy()
    
    # Identify SKU Column (usually ConfigSKU or index 6)
    m_sku_col = 'ConfigSKU' if 'ConfigSKU' in df_m_latest.columns else df_m_latest.columns[6]
    df_m_latest['Article'] = df_m_latest[m_sku_col].apply(to_article)
    
    # Summary Metrics Parsing
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budgetspent'])
    df_m_latest['Wish_Val'] = clean_numeric(df_m_latest['Addtowishlist'])
    
    # Pivot Marketing to Article
    df_m_agg = df_m_latest.groupby(['Article', 'Gender']).agg({
        'GMV_Val': 'sum',
        'Spend_Val': 'sum',
        'Wish_Val': 'sum'
    }).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)

    # B. STOCK: Pivot SKU level to Article level
    s_sku_col = next((c for c in df_s_raw.columns if 'SKU' in c.upper()), df_s_raw.columns[0])
    df_s_raw['Article'] = df_s_raw[s_sku_col].apply(to_article)
    
    # Identify Stock Columns
    zfs_col = 'ZFS_Stock' if 'ZFS_Stock' in df_s_raw.columns else None
    pf_col = 'PF_Stock' if 'PF_Stock' in df_s_raw.columns else None
    
    df_s_raw['ZFS_Clean'] = clean_numeric(df_s_raw[zfs_col]) if zfs_col else 0
    df_s_raw['PF_Clean'] = clean_numeric(df_s_raw[pf_col]) if pf_col else 0
    
    # PIVOT: Sum all SKU stock into the Article
    df_s_pivot = df_s_raw.groupby('Article').agg({
        'ZFS_Clean': 'sum',
        'PF_Clean': 'sum'
    }).reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot['ZFS_Clean'] + df_s_pivot['PF_Clean']

    # C. PROFIT: Pivot SKU level to Article level
    p_sku_col = next((c for c in df_p_raw.columns if 'SKU' in c.upper()), df_p_raw.columns[0])
    p_profit_col = next((c for c in df_p_raw.columns if any(k in c.upper() for k in ['PROFIT', 'MARGIN'])), df_p_raw.columns[-1])
    
    df_p_raw['Article'] = df_p_raw[p_sku_col].apply(to_article)
    df_p_raw['Profit_Val'] = clean_numeric(df_p_raw[p_profit_col])
    
    # PIVOT: Take the average/first profit value for the article
    df_p_pivot = df_p_raw.groupby('Article').agg({'Profit_Val': 'mean'}).reset_index()

    # D. JOIN ALL DATA (Marketing as Base)
    df = pd.merge(df_m_agg, df_s_pivot[['Article', 'Total_Stock']], on='Article', how='left')
    df = pd.merge(df, df_p_pivot, on='Article', how='left').fillna(0)

    # E. TIERING LOGIC
    def categorize(row):
        if (row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas and row['Profit_Val'] >= t_profit):
            return 'TOP', 'All KPI Met'
        elif (row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas and row['Profit_Val'] >= m_profit):
            return 'MEDIUM', 'Medium KPI Met'
        else:
            reasons = []
            if row['Total_Stock'] < m_stock: reasons.append(f"Stock ({int(row['Total_Stock'])})")
            if row['ROAS_Actual'] < m_roas: reasons.append(f"ROAS ({row['ROAS_Actual']:.1f})")
            if row['Profit_Val'] < m_profit: reasons.append(f"Profit (€{row['Profit_Val']:.1f})")
            return 'LOW', "Below: " + " & ".join(reasons)

    df[['Tier', 'Reason']] = df.apply(lambda r: pd.Series(categorize(r)), axis=1)

    # F. GENDER SEGMENTATION
    df['Campaign'] = df['Gender'].apply(lambda x: 'FEMALE' if str(x).strip().capitalize() == 'Damen' else 'MALE_UNISEX_KIDS')

    # --- 4. DASHBOARD: SUMMARY METRICS ---
    st.header("📊 Performance Summary (Latest Week)")
    c1, c2, c3, c4 = st.columns(4)
    total_gmv = df['GMV_Val'].sum()
    total_spend = df['Spend_Val'].sum()
    c1.metric("Total GMV", f"€{total_gmv:,.0f}")
    c2.metric("Ad Spend", f"€{total_spend:,.0f}")
    c3.metric("ROAS", f"{(total_gmv/total_spend):.2f}" if total_spend > 0 else "0.00")
    c4.metric("Wishlist Adds", f"{df['Wish_Val'].sum():,.0f}")

    # --- 5. WISHLIST FAVORITES ---
    st.divider()
    st.subheader("💖 Most Wishlisted Articles (Customer Demand)")
    st.table(df.sort_values(by='Wish_Val', ascending=False).head(5)[['Article', 'Gender', 'Wish_Val', 'Total_Stock', 'ROAS_Actual']])

    # --- 6. CAMPAIGN EXPORTS ---
    st.divider()
    for g in ['FEMALE', 'MALE_UNISEX_KIDS']:
        st.subheader(f"📂 {g} Campaigns")
        cols = st.columns(3)
        for i, t in enumerate(['TOP', 'MEDIUM', 'LOW']):
            with cols[i]:
                subset = df[(df['Campaign'] == g) & (df['Tier'] == t)]
                sku_list = subset['Article'].unique().tolist()
                st.markdown(f"**{t}** ({len(sku_list)})")
                st.text_area("SKUs", value=",".join(sku_list), height=150, key=f"t_{g}_{t}", label_visibility="collapsed")
                csv = pd.DataFrame(sku_list).to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Export", csv, f"{g}_{t}.csv", key=f"d_{g}_{t}")

    # --- 7. LOGIC INSPECTOR ---
    st.divider()
    with st.expander("🔍 Logic Inspector: Why are items in LOW?"):
        st.dataframe(df[['Article', 'Campaign', 'Total_Stock', 'ROAS_Actual', 'Profit_Val', 'Tier', 'Reason']], use_container_width=True)

else:
    st.warning("⚠️ Upload Marketing, Stock, and Profit files to generate the dashboard.")
