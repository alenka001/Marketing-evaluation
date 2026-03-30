import streamlit as st
import pandas as pd
import io

# --- Page Setup ---
st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("🚀 Swedemount Campaign Optimizer")

# --- 1. ROBUST DATA CLEANING TOOLS ---
def clean_numeric(series):
    """Parses European decimals (1.454,95) into Python floats (1454.95)"""
    s = series.astype(str).str.strip().str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def to_article_id(sku):
    """
    Standardizes any SKU format into a 13-char Zalando Config Article ID.
    Handles size suffixes and scientific notation errors.
    """
    s = str(sku).strip().upper().replace('.0', '')
    if '-' in s:
        parts = s.split('-')
        if len(parts) >= 2:
            # Rebuilds the Config ID: [Base]-[Color]
            return f"{parts[0]}-{parts[1][:3]}"
    return s

def load_csv(file):
    """Automatically handles Semicolon/Comma and UTF-8/Latin-1"""
    if file is None: return None
    raw_data = file.read(20000)
    file.seek(0)
    try: sample = raw_data.decode('utf-8')
    except: sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1')

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("📂 Upload Reports")
    z_marketing = st.file_uploader("1. Swedemount Marketing File", type="csv")
    stock_file = st.file_uploader("2. Inventory File (SKU Level)", type="csv")
    curr_attalos = st.file_uploader("3. Attalos Profit File (SKU Level)", type="csv")
    
    st.divider()
    st.header("🏆 TOP Tier Thresholds")
    t_stock = st.number_input("Min Stock (Article)", value=10)
    t_roas = st.number_input("Min ROAS", value=4.0)
    t_profit = st.number_input("Min Profit €", value=10.0)

    st.header("🥈 MEDIUM Tier Thresholds")
    m_stock = st.number_input("Min Stock (MED)", value=5)
    m_roas = st.number_input("Min ROAS", value=2.0)
    m_profit = st.number_input("Min Profit €", value=5.0)

# --- 3. PROCESSING ENGINE ---
if z_marketing and stock_file and curr_attalos:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)
    df_p_raw = load_csv(curr_attalos)

    # --- A. MARKETING (Pivot by Article) ---
    df_m = df_m_raw[df_m_raw['Year'].astype(str).str.contains('20', na=False)].copy()
    df_m['Year_N'] = clean_numeric(df_m['Year'])
    df_m['Week_N'] = clean_numeric(df_m['Week'])
    
    # Filter for Latest Week
    latest_y, latest_w = df_m['Year_N'].max(), df_m[df_m['Year_N'] == df_m['Year_N'].max()]['Week_N'].max()
    st.info(f"📅 Analyzing Performance for: Year {int(latest_y)}, Week {int(latest_w)}")
    df_m_latest = df_m[(df_m['Year_N'] == latest_y) & (df_m['Week_N'] == latest_w)].copy()
    
    m_sku_col = 'ConfigSKU' if 'ConfigSKU' in df_m_latest.columns else df_m_latest.columns[6]
    df_m_latest['Article'] = df_m_latest[m_sku_col].apply(to_article_id)
    
    # Clean Values
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budgetspent'])
    df_m_latest['Wish_Val'] = clean_numeric(df_m_latest['Addtowishlist'])
    
    # Group by Article
    df_m_agg = df_m_latest.groupby(['Article', 'Gender']).agg({
        'GMV_Val': 'sum', 'Spend_Val': 'sum', 'Wish_Val': 'sum'
    }).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)

    # --- B. INVENTORY (Pivot SKU Level to Article) ---
    s_sku_col = next((c for c in df_s_raw.columns if 'SKU' in c.upper()), df_s_raw.columns[0])
    df_s_raw['Article'] = df_s_raw[s_sku_col].apply(to_article_id)
    
    df_s_raw['ZFS_Clean'] = clean_numeric(df_s_raw['ZFS_Stock']) if 'ZFS_Stock' in df_s_raw.columns else 0
    df_s_raw['PF_Clean'] = clean_numeric(df_s_raw['PF_Stock']) if 'PF_Stock' in df_s_raw.columns else 0
    
    # PIVOT: Summarize all size stock into Article
    df_s_pivot = df_s_raw.groupby('Article').agg({'ZFS_Clean':'sum', 'PF_Clean':'sum'}).reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot['ZFS_Clean'] + df_s_pivot['PF_Clean']

    # --- C. PROFIT (Pivot SKU Level to Article) ---
    p_sku_col = next((c for c in df_p_raw.columns if 'SKU' in c.upper()), df_p_raw.columns[0])
    p_prof_col = next((c for c in df_p_raw.columns if any(k in c.upper() for k in ['PROFIT', 'MARGIN'])), df_p_raw.columns[-1])
    
    df_p_raw['Article'] = df_p_raw[p_sku_col].apply(to_article_id)
    df_p_raw['Profit_Val'] = clean_numeric(df_p_raw[p_prof_col])
    
    # PIVOT: Average profit for the Article
    df_p_pivot = df_p_raw.groupby('Article').agg({'Profit_Val': 'mean'}).reset_index()

    # --- D. FINAL MERGE (Ensuring Match) ---
    # Convert merge keys to uppercase and strip again to be 100% safe
    df_m_agg['Article'] = df_m_agg['Article'].str.upper().str.strip()
    df_s_pivot['Article'] = df_s_pivot['Article'].str.upper().str.strip()
    df_p_pivot['Article'] = df_p_pivot['Article'].str.upper().str.strip()

    df = pd.merge(df_m_agg, df_s_pivot[['Article', 'Total_Stock']], on='Article', how='left')
    df = pd.merge(df, df_p_pivot[['Article', 'Profit_Val']], on='Article', how='left').fillna(0)

    # --- E. LOGIC & GENDER ---
    def categorize(row):
        if (row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas and row['Profit_Val'] >= t_profit):
            return 'TOP', 'Pass'
        elif (row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas and row['Profit_Val'] >= m_profit):
            return 'MEDIUM', 'Pass'
        else:
            reasons = []
            if row['Total_Stock'] < m_stock: reasons.append(f"Stock({int(row['Total_Stock'])})")
            if row['ROAS_Actual'] < m_roas: reasons.append(f"ROAS({row['ROAS_Actual']:.1f})")
            if row['Profit_Val'] < m_profit: reasons.append(f"Profit(€{row['Profit_Val']:.1f})")
            return 'LOW', " | ".join(reasons)

    df[['Tier', 'Reason']] = df.apply(lambda r: pd.Series(categorize(r)), axis=1)
    df['Campaign'] = df['Gender'].apply(lambda x: 'FEMALE' if str(x).strip().capitalize() == 'Damen' else 'MALE_UNISEX_KIDS')

    # --- 4. DASHBOARD: OUTPUT ---
    st.header("📊 Performance Summary")
    c1, c2, c3, c4 = st.columns(4)
    total_gmv = df['GMV_Val'].sum()
    total_spend = df['Spend_Val'].sum()
    c1.metric("Total GMV", f"€{total_gmv:,.0f}")
    c2.metric("Ad Spend", f"€{total_spend:,.0f}")
    c3.metric("ROAS", f"{(total_gmv/total_spend):.2f}" if total_spend > 0 else "0.00")
    c4.metric("Wishlist Adds", f"{df['Wish_Val'].sum():,.0f}")

    st.divider()
    
    # CAMPAIGN EXPORTS
    for g in ['FEMALE', 'MALE_UNISEX_KIDS']:
        st.subheader(f"📂 {g} Campaign Tiers")
        cols = st.columns(3)
        for i, t in enumerate(['TOP', 'MEDIUM', 'LOW']):
            with cols[i]:
                subset = df[(df['Campaign'] == g) & (df['Tier'] == t)]
                skus = subset['Article'].unique().tolist()
                st.markdown(f"**{t}** ({len(skus)})")
                st.text_area("SKUs", ",".join(skus), height=150, key=f"t_{g}_{t}", label_visibility="collapsed")
                csv = pd.DataFrame(skus).to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Export", csv, f"{g}_{t}.csv", key=f"d_{g}_{t}")

    # DATA DIAGNOSTIC
    with st.expander("🔍 Diagnostic: Why is stock/profit 0?"):
        st.write("If Stock is 0.0, the SKU in your Inventory file didn't match the Marketing file.")
        st.dataframe(df[['Article', 'Total_Stock', 'ROAS_Actual', 'Profit_Val', 'Tier', 'Reason']], use_container_width=True)

else:
    st.warning("⚠️ Action Required: Upload Marketing, Inventory, and Profit files.")
