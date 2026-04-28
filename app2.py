import streamlit as st
import pandas as pd
import io
import re
import numpy as np

# Försök importera maskininlärningsbibliotek för klustring
try:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import MinMaxScaler
except ImportError:
    st.error("Biblioteket 'scikit-learn' saknas. Installera det med: pip install scikit-learn")

# --- Page Setup ---
st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("🚀 Swedemount Expert: Performance & Sync")
st.markdown("### Integrated: Article Sync, Stock Warnings, Cluster Filtering & Brand Overview")

# --- 1. UTILITIES ---
def clean_numeric(series):
    """Hanterar europeisk formatering och fixar 'extra nolla'-problemet"""
    def fix_string(val):
        if pd.isna(val): return "0"
        val = str(val).strip()
        val = re.sub(r'[^\d,.-]', '', val)
        if ',' in val and '.' in val:
            val = val.replace('.', '').replace(',', '.')
        elif ',' in val:
            val = val.replace(',', '.')
        return val
    s = series.apply(fix_string)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def standardize_sku(sku):
    """Klipp SKU till 13 tecken (Config ID)"""
    s = str(sku).strip().upper().replace('.0', '')
    if '-' in s:
        parts = s.split('-')
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1][:3]}"
    return s

def load_csv(file):
    """Auto-detekterar format för europeiska CSV-filer"""
    if file is None: return None
    raw_data = file.read(40000)
    file.seek(0)
    try: sample = raw_data.decode('utf-8')
    except: sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1')

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("📂 Data Upload")
    z_marketing = st.file_uploader("1. Swedemount SKU Report (ZMS)", type="csv")
    stock_file = st.file_uploader("2. Inventory File", type="csv")
    
    st.divider()
    st.header("⚖️ Comparison Mode")
    do_compare = st.checkbox("Enable Week-over-Week Comparison")

    st.divider()
    st.header("🏆 TOP Tier Thresholds")
    t_stock = st.number_input("Min Stock (TOP)", value=100)
    t_roas = st.number_input("Min ROAS (TOP)", value=10.0)
    
    st.header("🥈 MEDIUM Tier Thresholds")
    m_stock = st.number_input("Min Stock (MED)", value=60)
    m_roas = st.number_input("Min ROAS (MED)", value=4.0)

    st.header("⚠️ Stock Warning")
    days_threshold = st.slider("Alert if Stock Days less than:", 1, 10, 3)

# --- 3. DATA PROCESSING ENGINE ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    # A. Kolumnmappning
    m_cols_list = df_m_raw.columns.tolist()
    m_cols = {
        'Week': [c for c in m_cols_list if 'Week' in c][0],
        'SKU': [c for c in m_cols_list if 'SKU' in c or 'ConfigSKU' in c][0],
        'GMV': [c for c in m_cols_list if 'GMV' in c][0],
        'Spend': [c for c in m_cols_list if 'Budget spent' in c or 'Budgetspent' in c][0],
        'Sold': [c for c in m_cols_list if 'Items sold' in c or 'Itemssold' in c][0],
        'Campaign': [c for c in m_cols_list if 'Campaign' in c or 'ZMSCampaign' in c][0],
        'Clicks': [c for c in m_cols_list if 'Clicks' in c][0],
        'Gender': [c for c in m_cols_list if 'Gender' in c][0]
    }
    
    country_col = next((c for c in m_cols_list if 'TargetCountry' in c or 'Country' in c), None)

    # B. Grundtvätt
    df_m_raw['Week_Num'] = clean_numeric(df_m_raw[m_cols['Week']])
    df_m_raw['Article'] = df_m_raw[m_cols['SKU']].apply(standardize_sku)
    df_m_raw['GMV_Val'] = clean_numeric(df_m_raw[m_cols['GMV']])
    df_m_raw['Spend_Val'] = clean_numeric(df_m_raw[m_cols['Spend']])
    df_m_raw['Sold_Val'] = clean_numeric(df_m_raw[m_cols['Sold']])
    df_m_raw['Clicks_Val'] = clean_numeric(df_m_raw[m_cols['Clicks']])

    # --- 🌍 GLOBAL LANDSKLUSTRING ---
    cluster_mapping = {}
    df_country_summary = pd.DataFrame()

    if country_col:
        df_c_logic = df_m_raw.groupby(country_col).agg({
            'Spend_Val': 'sum', 'Clicks_Val': 'sum', 'GMV_Val': 'sum'
        }).reset_index()
        
        df_c_logic['ROAS'] = df_c_logic['GMV_Val'] / df_c_logic['Spend_Val'].replace(0, 1)
        df_c_logic['COS'] = df_c_logic['Spend_Val'] / df_c_logic['GMV_Val'].replace(0, 1)
        df_c_logic['CPC'] = df_c_logic['Spend_Val'] / df_c_logic['Clicks_Val'].replace(0, 1)
        
        df_c_input = df_c_logic[df_c_logic['Spend_Val'] > 0].copy()
        
        if len(df_c_input) >= 3:
            scaler = MinMaxScaler()
            scaled_data = scaler.fit_transform(df_c_input[['ROAS', 'COS', 'CPC']])
            kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
            df_c_input['Cluster_ID'] = kmeans.fit_predict(scaled_data)
            cluster_mapping = dict(zip(df_c_input[country_col], df_c_input['Cluster_ID']))
            df_country_summary = df_c_input

    df_m_raw['Cluster_ID'] = df_m_raw[country_col].map(cluster_mapping).fillna(-1).astype(int)

    # Sidebar Cluster Filter
    with st.sidebar:
        st.divider()
        st.header("🌍 Kluster-filter")
        unique_clusters = sorted(df_m_raw['Cluster_ID'].unique())
        selected_clusters = st.multiselect(
            "Visa prestanda för kluster:",
            options=unique_clusters,
            default=unique_clusters,
            format_func=lambda x: f"Kluster {x}" if x != -1 else "Okända länder"
        )

    # C. Senaste Veckan & Gender Lock
    available_weeks = sorted(df_m_raw[df_m_raw['Week_Num'] > 0]['Week_Num'].unique().astype(int))
    latest_week = max(available_weeks) if available_weeks else 0
    df_m_latest = df_m_raw[df_m_raw['Week_Num'] == latest_week].copy()

    def detect_group(val):
        v = str(val).strip()
        return 'FEMALE' if v in ['Damen', 'KinderMädchen'] else 'MALE_UNISEX_KIDS'
    
    df_m_latest['Group_Draft'] = df_m_latest[m_cols['Gender']].apply(detect_group)
    gender_lock = df_m_latest.sort_values('Group_Draft').groupby('Article')['Group_Draft'].first().reset_index()

    # Filtrering baserat på kluster
    df_m_filtered = df_m_latest[df_m_latest['Cluster_ID'].isin(selected_clusters)]

    df_m_agg = df_m_filtered.groupby('Article').agg({
        'GMV_Val':'sum', 'Spend_Val':'sum', 'Sold_Val':'sum'
    }).reset_index()
    
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)
    df_m_agg = pd.merge(df_m_agg, gender_lock, on='Article', how='left')

    # D. Inventory Processing
    df_s_raw['Article'] = df_s_raw.iloc[:, 4].apply(standardize_sku)
    df_s_raw['Season'] = df_s_raw.iloc[:, 8].astype(str).str.strip() 
    df_s_raw['brand'] = df_s_raw.iloc[:, 7].astype(str).str.strip()
    df_s_raw['Partner_Article_Variant'] = df_s_raw.iloc[:, 2].astype(str).str.strip() 
    
    stock_cols = [c for c in df_s_raw.columns if 'STOCK' in c.upper()]
    for col in stock_cols: df_s_raw[col] = clean_numeric(df_s_raw[col])
    
    df_s_pivot = df_s_raw.groupby('Article').agg({
        **{col: 'sum' for col in stock_cols},
        'Season': 'first',
        'brand': 'first',
        'Partner_Article_Variant': 'first'
    }).reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)
    df_s_valid = df_s_pivot[df_s_pivot['Total_Stock'] > 0].copy()

    # E. Merge & Tiering
    df = pd.merge(df_m_agg, df_s_valid[['Article', 'Total_Stock', 'Season', 'brand']], on='Article', how='left').fillna({'Total_Stock': 0, 'brand': 'Unknown'})
    df['Daily_Velocity'] = df['Sold_Val'] / 7
    df['Days_Left'] = df['Total_Stock'] / df['Daily_Velocity'].replace(0, 0.001)

    def assign_tier(row):
        if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas: return 'TOP'
        elif row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas: return 'MEDIUM'
        return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)

    # --- 4. TABS SETUP ---
    tab1, tab2, tab3, tab4 = st.tabs(["🚀 Kampanjfördelning", "🏷️ Varumärkesöversikt", "🔄 Sync Status", "🌍 Landsklustring"])

    with tab1:
        st.header(f"📊 Kampanjfördelning (Vecka {latest_week})")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Unique Articles", len(df))
        m2.metric("Overall ROAS", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.0")
        m3.metric("Stock Alerts", len(df[(df['Tier'] == 'TOP') & (df['Days_Left'] < days_threshold) & (df['Sold_Val'] > 0)]))
        m4.metric("Matched Inventory", f"{df['Total_Stock'].sum():,.0f} units")

        st.divider()
        for group in ['FEMALE', 'MALE_UNISEX_KIDS']:
            st.subheader(f"📂 {group} Campaign Tiers")
            cols = st.columns(3)
            for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
                with cols[i]:
                    subset = df[(df['Group_Draft'] == group) & (df['Tier'] == tier) & (df['Total_Stock'] > 0)]
                    skus = subset['Article'].unique().tolist()
                    st.markdown(f"**{tier} {group}**")
                    st.metric("Articles", len(skus))
                    st.text_area("SKU List", ",".join(skus), height=150, key=f"t_{group}_{tier}", label_visibility="collapsed")
                    st.download_button("Export CSV", pd.DataFrame(skus).to_csv(index=False, header=False).encode('utf-8'), f"{group}_{tier}.csv", key=f"d_{group}_{tier}")

    with tab2:
        st.header("🏷️ Brand Performance Overview")
        brand_stats = df.groupby('brand').agg({'Spend_Val': 'sum', 'GMV_Val': 'sum', 'Sold_Val': 'sum'}).reset_index()
        brand_stats['ROAS'] = (brand_stats['GMV_Val'] / brand_stats['Spend_Val'].replace(0, 1)).round(2)
        st.dataframe(brand_stats.sort_values('GMV_Val', ascending=False), use_container_width=True, hide_index=True)

    with tab3:
        st.header("🔄 Sync Status & Clean-up")
        col_d, col_m = st.columns(2)
        with col_d:
            st.markdown("**Multi-Campaign Duplicates (Latest Week & Spend > 0)**")
            m_active = df_m_latest[(df_m_latest['Article'] != 'UNDEFINED') & (df_m_latest['Spend_Val'] > 0)]
            dupes = m_active.groupby('Article')[m_cols['Campaign']].nunique()
            multi_skus = dupes[dupes > 1].index.tolist()
            df_dupes = m_active[m_active['Article'].isin(multi_skus)][['Article', m_cols['Campaign'], 'Spend_Val']].sort_values('Article')
            st.dataframe(df_dupes, use_container_width=True)
        
        with col_m:
            st.markdown("**Missing from ZMS (Stock > 10)**")
            inv_skus = set(df_s_valid['Article'])
            zms_skus = set(df_m_agg['Article'])
            missing = list(inv_skus - zms_skus)
            df_missing = df_s_valid[(df_s_valid['Article'].isin(missing)) & (df_s_valid['Total_Stock'] > 10)]
            st.dataframe(df_missing[['Article', 'Total_Stock', 'Season']], use_container_width=True)

    with tab4:
        st.header("🌍 Landsklustring (K-Means)")
        if not df_country_summary.empty:
            st.dataframe(df_country_summary.sort_values('Cluster_ID'), use_container_width=True)
            st.download_button("📥 Ladda ner landsklustring", df_country_summary.to_csv(index=False).encode('utf-8'), "country_clusters.csv")
        else:
            st.warning("Ingen landsinformation tillgänglig.")

else:
    st.info("👋 Ladda upp dina filer för att börja.")
