import streamlit as st
import pandas as pd
import io
import re
import numpy as np
# Vi använder plotly för snygga jämförelse-grafer
try:
    import plotly.express as px
except ImportError:
    st.error("Biblioteket 'plotly' saknas. Installera det med: pip install plotly")

# --- Page Setup ---
st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("🚀 Swedemount Expert: Global Performance & Sync")
st.markdown("### Integrated: Country Clustering, Article Sync, and MoM Comparison")

# --- 1. UTILITIES ---
def clean_numeric(series):
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
    s = str(sku).strip().upper().replace('.0', '')
    if '-' in s:
        parts = s.split('-')
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1][:3]}"
    return s

def load_csv(file):
    if file is None: return None
    raw_data = file.read(40000)
    file.seek(0)
    try: sample = raw_data.decode('utf-8')
    except: sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1')

def run_manual_kmeans(df, features, k=3, iterations=10):
    if len(df) < k: return np.zeros(len(df))
    data = df[features].values
    min_vals = data.min(axis=0)
    max_vals = data.max(axis=0)
    denom = (max_vals - min_vals)
    denom[denom == 0] = 1
    scaled_data = (data - min_vals) / denom
    np.random.seed(42)
    idx = np.random.choice(len(scaled_data), k, replace=False)
    centroids = scaled_data[idx]
    for _ in range(iterations):
        diff = scaled_data[:, np.newaxis] - centroids
        distances = np.sqrt((diff**2).sum(axis=2))
        labels = np.argmin(distances, axis=1)
        new_centroids = np.array([scaled_data[labels == i].mean(axis=0) if len(scaled_data[labels == i]) > 0 else centroids[i] for i in range(k)])
        if np.all(centroids == new_centroids): break
        centroids = new_centroids
    return labels

# --- 2. DATA PROCESSING ENGINE ---
if z_marketing := st.sidebar.file_uploader("1. SKU Report (Country Split)", type="csv"):
    stock_file = st.sidebar.file_uploader("2. Inventory File", type="csv")
    
    if stock_file:
        df_m_raw = load_csv(z_marketing)
        df_s_raw = load_csv(stock_file)

        # A. Kolumnmappning
        m_cols_list = df_m_raw.columns.tolist()
        m_cols = {
            'Month': [c for c in m_cols_list if 'Month' in c][0],
            'Week': [c for c in m_cols_list if 'Week' in c][0],
            'SKU': [c for c in m_cols_list if 'SKU' in c or 'ConfigSKU' in c][0],
            'GMV': [c for c in m_cols_list if 'GMV' in c][0],
            'Spend': [c for c in m_cols_list if 'Budget' in c and 'spent' in c.lower() or 'Budgetspent' in c][0],
            'Sold': [c for c in m_cols_list if 'Items' in c and 'sold' in c.lower() or 'Itemssold' in c][0],
            'Campaign': [c for c in m_cols_list if 'Campaign' in c][0],
            'Clicks': [c for c in m_cols_list if 'Clicks' in c][0],
            'Gender': [c for c in m_cols_list if 'Gender' in c][0],
            'Impressions': [c for c in m_cols_list if 'ad impressions' in c.lower()][0]
        }
        country_col = next((c for c in m_cols_list if 'Target' in c and 'Country' in c or 'Country' in c), None)

        # B. Grundtvätt
        df_m_raw['Week_Num'] = clean_numeric(df_m_raw[m_cols['Week']])
        df_m_raw['Month_Num'] = clean_numeric(df_m_raw[m_cols['Month']]).astype(int)
        df_m_raw['Article'] = df_m_raw[m_cols['SKU']].apply(standardize_sku)
        df_m_raw['GMV_Val'] = clean_numeric(df_m_raw[m_cols['GMV']])
        df_m_raw['Spend_Val'] = clean_numeric(df_m_raw[m_cols['Spend']])
        df_m_raw['Sold_Val'] = clean_numeric(df_m_raw[m_cols['Sold']])
        df_m_raw['Clicks_Val'] = clean_numeric(df_m_raw[m_cols['Clicks']])
        df_m_raw['Impressions_Val'] = clean_numeric(df_m_raw[m_cols['Impressions']])

        # --- SIDEBAR UI ---
        with st.sidebar:
            st.divider()
            st.header("🏆 TOP Tier Thresholds")
            t_stock = st.number_input("Min Stock (TOP)", value=100)
            t_roas = st.number_input("Min ROAS (TOP)", value=10.0)
    
            st.header("🥈 MEDIUM Tier Thresholds")
            m_stock = st.number_input("Min Stock (MED)", value=60)
            m_roas = st.number_input("Min ROAS (MED)", value=4.0)
            
            st.divider()
            st.header("📅 Kluster-månader")
            all_months = sorted(df_m_raw[df_m_raw['Month_Num'] > 0]['Month_Num'].unique())
            selected_months = st.multiselect("Basera kluster på:", options=all_months, default=all_months)

        # --- 🌍 GLOBAL LANDSKLUSTRING ---
        cluster_mapping = {}
        df_country_summary = pd.DataFrame()
        if country_col and selected_months:
            df_c_filtered = df_m_raw[df_m_raw['Month_Num'].isin(selected_months)]
            df_c_logic = df_c_filtered.groupby(country_col).agg({'Spend_Val':'sum', 'Clicks_Val':'sum', 'GMV_Val':'sum'}).reset_index()
            df_c_logic['ROAS'] = df_c_logic['GMV_Val'] / df_c_logic['Spend_Val'].replace(0, 1)
            df_c_logic['COS'] = df_c_logic['Spend_Val'] / df_c_logic['GMV_Val'].replace(0, 1)
            df_c_logic['CPC'] = df_c_logic['Spend_Val'] / df_c_logic['Clicks_Val'].replace(0, 1)
            df_c_input = df_c_logic[df_c_logic['Spend_Val'] > 0].copy()
            if len(df_c_input) >= 3:
                df_c_input['Cluster_ID'] = run_manual_kmeans(df_c_input, ['ROAS', 'COS', 'CPC'], k=3)
                cluster_mapping = dict(zip(df_c_input[country_col], df_c_input['Cluster_ID']))
                df_country_summary = df_c_input

        df_m_raw['Cluster_ID'] = df_m_raw[country_col].map(cluster_mapping).fillna(-1).astype(int)

        with st.sidebar:
            st.header("🌍 Cluster Selection")
            unique_cl = sorted(df_m_raw['Cluster_ID'].unique())
            selected_clusters = st.multiselect("Aktiva kluster i dashboard:", options=unique_cl, default=unique_cl, format_func=lambda x: f"Kluster {x}" if x != -1 else "Unknown")

        # C. Senaste Veckan Processing
        available_weeks = sorted(df_m_raw[df_m_raw['Week_Num'] > 0]['Week_Num'].unique().astype(int))
        latest_week = max(available_weeks) if available_weeks else 0
        df_m_latest = df_m_raw[df_m_raw['Week_Num'] == latest_week].copy()

        def detect_group(val):
            v = str(val).strip()
            return 'FEMALE' if v in ['Damen', 'KinderMädchen'] else 'MALE_UNISEX_KIDS'
        
        df_m_latest['Group_Draft'] = df_m_latest[m_cols['Gender']].apply(detect_group)
        gender_lock = df_m_latest.sort_values('Group_Draft').groupby('Article')['Group_Draft'].first().reset_index()

        df_m_filtered = df_m_latest[df_m_latest['Cluster_ID'].isin(selected_clusters)]
        df_m_agg = df_m_filtered.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum', 'Sold_Val':'sum'}).reset_index()
        df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)
        df_m_agg = pd.merge(df_m_agg, gender_lock, on='Article', how='left')

        # D. Inventory
        df_s_raw['Article'] = df_s_raw.iloc[:, 4].apply(standardize_sku)
        df_s_raw['Season'] = df_s_raw.iloc[:, 8].astype(str).str.strip() 
        df_s_raw['brand'] = df_s_raw.iloc[:, 7].astype(str).str.strip()
        stock_cols = [c for c in df_s_raw.columns if 'STOCK' in c.upper()]
        for col in stock_cols: df_s_raw[col] = clean_numeric(df_s_raw[col])
        df_s_pivot = df_s_raw.groupby('Article').agg({**{col: 'sum' for col in stock_cols}, 'Season': 'first', 'brand': 'first'}).reset_index()
        df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)
        df_s_valid = df_s_pivot[df_s_pivot['Total_Stock'] > 0].copy()

        # E. Merge & Tiering
        df = pd.merge(df_m_agg, df_s_valid[['Article', 'Total_Stock', 'Season', 'brand']], on='Article', how='left').fillna({'Total_Stock': 0, 'brand': 'Unknown'})
        def assign_tier(row):
            if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas: return 'TOP'
            elif row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas: return 'MEDIUM'
            return 'LOW'
        df['Tier'] = df.apply(assign_tier, axis=1)

        # --- 4. TABS ---
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🚀 Kampanjfördelning", "🏷️ Varumärkesöversikt", "🔄 Sync Status", "🌍 Landsklustring", "📈 Landsjämförelse"])

        with tab1:
            st.header(f"📊 Kampanjhinkar (Vecka {latest_week})")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Unique Articles", len(df))
            m2.metric("Overall ROAS", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.0")
            m3.metric("Stock Alerts", len(df[(df['Tier'] == 'TOP') & (df['Total_Stock'] < 20)]))
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
                st.markdown("**Multi-Campaign Duplicates (Active Spend)**")
                m_active = df_m_latest[(df_m_latest['Article'] != 'UNDEFINED') & (df_m_latest['Spend_Val'] > 0)]
                dupes = m_active.groupby('Article')[m_cols['Campaign']].nunique()
                multi_skus = dupes[dupes > 1].index.tolist()
                st.dataframe(m_active[m_active['Article'].isin(multi_skus)][['Article', m_cols['Campaign'], 'Spend_Val']], use_container_width=True)
            with col_m:
                st.markdown("**Missing from ZMS (Stock > 10)**")
                inv_skus = set(df_s_valid['Article'])
                zms_skus = set(df_m_agg['Article'])
                missing = list(inv_skus - zms_skus)
                st.dataframe(df_s_valid[(df_s_valid['Article'].isin(missing)) & (df_s_valid['Total_Stock'] > 10)][['Article', 'Total_Stock', 'Season']], use_container_width=True)

        with tab4:
            st.header("🌍 Automated Country Clusters")
            if not df_country_summary.empty:
                st.dataframe(df_country_summary.sort_values('Cluster_ID'), use_container_width=True)
                st.download_button("📥 Download Country Data", df_country_summary.to_csv(index=False).encode('utf-8'), "country_clusters.csv")

        with tab5:
            st.header("📈 Landsjämförelse (Månad över Månad)")
            if country_col:
                months = sorted(df_m_raw['Month_Num'].unique())
                if len(months) >= 2:
                    sel_m = st.selectbox("Välj månad att analysera:", options=months, index=len(months)-1)
                    prev_m = months[months.index(sel_m) - 1] if months.index(sel_m) > 0 else None
                    
                    if prev_m is not None:
                        st.info(f"Jämför Månad {sel_m} (Nuvarande) mot Månad {prev_m} (Föregående)")
                        
                        df_m_stats = df_m_raw[df_m_raw['Month_Num'].isin([sel_m, prev_m])].groupby([country_col, 'Month_Num']).agg({
                            'GMV_Val': 'sum', 'Spend_Val': 'sum', 'Clicks_Val': 'sum', 'Impressions_Val': 'sum'
                        }).reset_index()
                        
                        df_m_stats['ROAS'] = df_m_stats['GMV_Val'] / df_m_stats['Spend_Val'].replace(0, 1)
                        df_m_stats['COS'] = (df_m_stats['Spend_Val'] / df_m_stats['GMV_Val'].replace(0, 1)) * 100
                        df_m_stats['CPC'] = df_m_stats['Spend_Val'] / df_m_stats['Clicks_Val'].replace(0, 1)
                        
                        metric_to_plot = st.selectbox("Välj mätetal för grafen:", 
                                                      ["ROAS", "COS (%)", "CPC", "Impressions", "GMV", "Budget Spent"])
                        
                        plot_map = {"ROAS": "ROAS", "COS (%)": "COS", "CPC": "CPC", 
                                    "Impressions": "Impressions_Val", "GMV": "GMV_Val", "Budget Spent": "Spend_Val"}
                        
                        df_plot = df_m_stats.copy()
                        df_plot['Månad'] = df_plot['Month_Num'].apply(lambda x: "Nuvarande" if x == sel_m else "Föregående")
                        
                        fig = px.bar(df_plot, x=country_col, y=plot_map[metric_to_plot], color='Månad', barmode='group',
                                     title=f"{metric_to_plot} per land - Månadsjämförelse",
                                     labels={plot_map[metric_to_plot]: metric_to_plot, country_col: "Land"},
                                     color_discrete_map={"Nuvarande": "#0b5394", "Föregående": "#999999"})
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Ingen föregående månad hittades.")
                else:
                    st.warning("Datan behöver innehålla minst två olika månader.")
            else:
                st.error("Land-kolumn saknas i filen.")

else:
    st.info("👋 Everything is ready. Just upload your SKU Report and Inventory file to begin.")
