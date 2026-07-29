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
st.title("Swedemount Expert: Global Performance & Sync")
st.markdown("### Integrated: Manual Country Clusters, Season Filtering, and Cluster Buckets")

# --- 1. UTILITIES ---
def clean_numeric(series):
    """Tvättar europeisk talformatering och konverterar till numeriska värden."""
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
    """Standardiserar SKU till Config-ID (13 tecken)."""
    s = str(sku).strip().upper().replace('.0', '')
    if '-' in s:
        parts = s.split('-')
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1][:3]}"
    return s

@st.cache_data(show_spinner=False)
def load_csv(file):
    """Läser in CSV-fil minnessnålt med cachenätverk."""
    if file is None: return None
    raw_data = file.read(40000)
    file.seek(0)
    try: sample = raw_data.decode('utf-8')
    except: sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    file.seek(0)
    
    # Läs in filen med low_memory=False för stabilitet
    df = pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1', low_memory=False)
    return optimize_memory(df)

def optimize_memory(df):
    """Reducerar RAM-förbrukning med upp till 70% genom att optimera datatyper."""
    for col in df.columns:
        col_type = df[col].dtype
        if col_type != object:
            c_min = df[col].min()
            c_max = df[col].max()
            if str(col_type).startswith('int'):
                if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                    df[col] = df[col].astype(np.int16)
                elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
            else:
                if c_min > np.finfo(np.float32).min and c_max < np.finfo(np.float32).max:
                    df[col] = df[col].astype(np.float32)
        else:
            # Konvertera textkolumner med få unika värden till kategorier (sparar enormt med RAM)
            num_unique = len(df[col].unique())
            num_total = len(df[col])
            if num_total > 0 and (num_unique / num_total) < 0.5:
                df[col] = df[col].astype('category')
    return df

# --- 2. MANUELL KLUSTER-MAPPING ---
# Här definieras ländernas tillhörighet manuellt utifrån din strategi
MANUAL_CLUSTER_MAPPING = {
    'IT': 'C1 (IT, FR, ES)',
    'FR': 'C1 (IT, FR, ES)',
    'ES': 'C1 (IT, FR, ES)',
    'DE': 'C2 (DE, NL, BE)',
    'NL': 'C2 (DE, NL, BE)',
    'BE': 'C2 (DE, NL, BE)',
    'AT': 'C3 (AT, FI, PL, CZ, DK, LUX)',
    'FI': 'C3 (AT, FI, PL, CZ, DK, LUX)',
    'PL': 'C3 (AT, FI, PL, CZ, DK, LUX)',
    'CZ': 'C3 (AT, FI, PL, CZ, DK, LUX)',
    'DK': 'C3 (AT, FI, PL, CZ, DK, LUX)',
    'LUX': 'C3 (AT, FI, PL, CZ, DK, LUX)',
    'LU': 'C3 (AT, FI, PL, CZ, DK, LUX)',
    'EE': 'C4 (East & Baltikum)',
    'LT': 'C4 (East & Baltikum)',
    'LV': 'C4 (East & Baltikum)',
    'SI': 'C4 (East & Baltikum)',
    'SK': 'C4 (East & Baltikum)',
    'HU': 'C4 (East & Baltikum)',
    'RO': 'C4 (East & Baltikum)',
    'BG': 'C4 (East & Baltikum)',
    'HR': 'C4 (East & Baltikum)',
    'SE': 'Standalone: Sverige (SE)',
    'CH': 'Standalone: Schweiz (CH)'
}

# --- 3. DATA PROCESSING ENGINE ---
if z_marketing := st.sidebar.file_uploader("1. SKU Report (Country Split)", type="csv"):
    stock_file = st.sidebar.file_uploader("2. Inventory File", type="csv")
    
    if stock_file:
        df_m_raw = load_csv(z_marketing)
        df_s_raw = load_csv(stock_file)

        # A. Kolumnmappning för Marknadsföringsfil
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

        # B. Grundtvätt av Marknadsföringsfil
        df_m_raw['Week_Num'] = clean_numeric(df_m_raw[m_cols['Week']]).astype(int)
        df_m_raw['Month_Num'] = clean_numeric(df_m_raw[m_cols['Month']]).astype(int)
        df_m_raw['Article'] = df_m_raw[m_cols['SKU']].apply(standardize_sku)
        df_m_raw['GMV_Val'] = clean_numeric(df_m_raw[m_cols['GMV']])
        df_m_raw['Spend_Val'] = clean_numeric(df_m_raw[m_cols['Spend']])
        df_m_raw['Sold_Val'] = clean_numeric(df_m_raw[m_cols['Sold']])
        df_m_raw['Clicks_Val'] = clean_numeric(df_m_raw[m_cols['Clicks']])
        df_m_raw['Impressions_Val'] = clean_numeric(df_m_raw[m_cols['Impressions']])

        # C. Tilldela Manuella Kluster till Rådatan
        df_m_raw['Cluster_Name'] = df_m_raw[country_col].map(MANUAL_CLUSTER_MAPPING).fillna('Övriga marknader')

        # --- SIDEBAR UI ---
        with st.sidebar:
            st.divider()
            st.header("🏆 TOP Tier Thresholds")
            t_stock = st.number_input("Min Stock (TOP)", value=100)
            t_roas = st.number_input("Min ROAS (TOP)", value=10.0)
    
            st.header("🥈 MEDIUM Tier Thresholds")
            m_stock = st.number_input("Min Stock (MED)", value=60)
            m_roas = st.number_input("Min ROAS (MED)", value=4.0)
            
            # --- Landsfilter ---
            st.divider()
            st.header("🏳️‍🌈 Landsval")
            all_countries = sorted(df_m_raw[country_col].dropna().unique().tolist())
            selected_countries = st.multiselect(
                "Inkludera/Exkludera marknader:",
                options=all_countries,
                default=all_countries,
                help="Ta bort länder härifrån för att exkludera dem från analysen."
            )

            # Sidomeny - Valfri fil för förra veckans synlighetsjämförelse
            st.divider()
            st.header("👁️ Synlighetsjämförelse")
            prev_vis_file = st.file_uploader("3. (Valfri) Förra veckans rapport", type="csv", help="Ladda upp förra veckans fil för att se om vidtagna åtgärder förbättrat synligheten.")

            # --- Kluster-val ---
            st.divider()
            st.header("🌍 Kluster-selection")
            all_clusters = sorted(df_m_raw['Cluster_Name'].unique().tolist())
            selected_clusters = st.multiselect(
                "Aktiva kluster i dashboard:",
                options=all_clusters,
                default=all_clusters
            )

            # --- Säsongsfilter (Kolumn I i lagerfilen) ---
            st.divider()
            st.header("🍂 Säsongsfilter")
            
            # 1. Konvertera kolumn I (index 8) till strängar och fyll i tomma värden säkert
            df_s_raw['Season'] = df_s_raw.iloc[:, 8].fillna('').astype(str).str.strip()
            
            # 2. Hämta unika säsonger och filtrera bort ogiltiga värden säkert
            all_seasons = sorted([
                s for s in df_s_raw['Season'].unique() 
                if s and s.lower() not in ['nan', 'none', '']
            ])
            
            selected_seasons = st.multiselect(
                "Välj säsonger att inkludera:",
                options=all_seasons,
                default=all_seasons,
                help="Välj t.ex. HW24, Year_Round_Basics eller exkludera äldre säsonger."
            )

        # D. Hantera Lagerfil & Filtrera på Säsong
        df_s_raw['Article'] = df_s_raw.iloc[:, 4].apply(standardize_sku)
        df_s_raw['brand'] = df_s_raw.iloc[:, 7].astype(str).str.strip()
        
        # Filtrera lagret baserat på valda säsonger i sidebaren
        df_s_filtered_season = df_s_raw[df_s_raw['Season'].isin(selected_seasons)].copy()
        
        # Identifiera ZFS-kolumner
        zfs_cols = [c for c in df_s_filtered_season.columns if 'ZFS' in c.upper()]
        if not zfs_cols: 
            zfs_cols = [c for c in df_s_filtered_season.columns if 'STOCK' in c.upper()] # Fallback
        
        for col in zfs_cols: 
            df_s_filtered_season[col] = clean_numeric(df_s_filtered_season[col])
            
        df_s_pivot = df_s_filtered_season.groupby('Article').agg({
            **{col: 'sum' for col in zfs_cols}, 
            'Season': 'first', 
            'brand': 'first'
        }).reset_index()
        
        df_s_pivot['Total_Stock'] = df_s_pivot[zfs_cols].sum(axis=1)
        df_s_valid = df_s_pivot[df_s_pivot['Total_Stock'] > 0].copy()

        # E. Processing för Senaste Veckan
        available_weeks = sorted(df_m_raw[df_m_raw['Week_Num'] > 0]['Week_Num'].unique())
        latest_week = max(available_weeks) if available_weeks else 0
        df_m_latest = df_m_raw[df_m_raw['Week_Num'] == latest_week].copy()

        # Filter på valda länder och kluster för senast vecka
        df_m_filtered = df_m_latest[
            df_m_latest['Cluster_Name'].isin(selected_clusters) & 
            df_m_latest[country_col].isin(selected_countries)
        ]

        # --- 4. TABS ---
        # ÄNDRA RADEN MED TABS TILL DETTA:
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🚀 Kampanjfördelning", 
        "🏷️ Varumärkesöversikt", 
        "🔄 Sync Status", 
        "🌍 Landsklustring", 
        "📈 Landsjämförelse",
        "👁️ Synlighetsanalys"
        ])

        # --- TAB 1: KAMPANJHINKAR PER KLUSTER ---
        with tab1:
            st.header(f"📊 Kampanjhinkar per Kluster (Vecka {latest_week})")
            
            # Globala mätetal över valda filter
            m_agg_global = df_m_filtered.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum'}).reset_index()
            df_global = pd.merge(m_agg_global, df_s_valid[['Article', 'Total_Stock']], on='Article', how='inner')
            
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Unika Matchade Artiklar", len(df_global))
            col_m2.metric("Overall ROAS (Senaste v.)", f"{(df_global['GMV_Val'].sum()/df_global['Spend_Val'].sum()):.2f}" if df_global['Spend_Val'].sum() > 0 else "0.0")
            col_m3.metric("Matchat ZFS-lager (Valda säsonger)", f"{df_global['Total_Stock'].sum():,.0f} enheter")
            st.divider()

            if not selected_clusters:
                st.info("Välj minst ett kluster i sidebaren för att se kampanjhinkarna.")
            else:
                for cluster in selected_clusters:
                    # Skapa en fällbar meny (expander) för varje aktivt kluster
                    with st.expander(f"📁 **Kampanjhinkar för {cluster}**", expanded=True):
                        # Filtrera data enbart för detta kluster
                        df_c_latest = df_m_latest[
                            (df_m_latest['Cluster_Name'] == cluster) & 
                            (df_m_latest[country_col].isin(selected_countries))
                        ]
                        
                        df_c_agg = df_c_latest.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum'}).reset_index()
                        df_c_agg['ROAS_Actual'] = df_c_agg['GMV_Val'] / df_c_agg['Spend_Val'].replace(0, 1)
                        
                        # Koppla ihop med lagret (som redan är säsongsfiltrerat)
                        df_c_merged = pd.merge(df_c_agg, df_s_valid[['Article', 'Total_Stock']], on='Article', how='inner')
                        
                        def assign_tier(row):
                            if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas: return 'TOP'
                            elif row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas: return 'MEDIUM'
                            return 'LOW'
                        
                        df_c_merged['Tier'] = df_c_merged.apply(assign_tier, axis=1)
                        
                        # Tre kolumner inuti varje klusters expander
                        c_cols = st.columns(3)
                        for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
                            with c_cols[i]:
                                subset = df_c_merged[df_c_merged['Tier'] == tier]
                                skus = subset['Article'].unique().tolist()
                                st.markdown(f"#### {tier}")
                                st.metric("Artiklar", len(skus))
                                st.text_area(
                                    "SKU List", 
                                    ",".join(skus), 
                                    height=200, 
                                    key=f"t_{cluster}_{tier}", 
                                    label_visibility="collapsed"
                                )
                                st.download_button(
                                    f"Export {tier} CSV", 
                                    pd.DataFrame(skus).to_csv(index=False, header=False).encode('utf-8'), 
                                    f"{cluster}_{tier}_articles.csv",
                                    key=f"d_{cluster}_{tier}"
                                )

        with tab2:
            st.header("🏷️ Varumärkesöversikt")
            df_m_agg_brand = df_m_filtered.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum', 'Sold_Val':'sum'}).reset_index()
            df_brand_merged = pd.merge(df_m_agg_brand, df_s_valid[['Article', 'brand']], on='Article', how='inner')
            brand_stats = df_brand_merged.groupby('brand').agg({'Spend_Val': 'sum', 'GMV_Val': 'sum', 'Sold_Val': 'sum'}).reset_index()
            brand_stats['ROAS'] = (brand_stats['GMV_Val'] / brand_stats['Spend_Val'].replace(0, 1)).round(2)
            st.dataframe(brand_stats.sort_values('GMV_Val', ascending=False), use_container_width=True, hide_index=True)

        with tab3:
            st.header("🔄 Sync Status & Clean-up")
            col_d, col_m = st.columns(2)
            with col_d:
                st.markdown("**Multi-Campaign Duplicates (Aktiv Spend)**")
                m_active = df_m_latest[(df_m_latest['Article'] != 'UNDEFINED') & (df_m_latest['Spend_Val'] > 0)]
                dupes = m_active.groupby('Article')[m_cols['Campaign']].nunique()
                multi_skus = dupes[dupes > 1].index.tolist()
                st.dataframe(m_active[m_active['Article'].isin(multi_skus)][['Article', m_cols['Campaign'], 'Spend_Val']], use_container_width=True)
            with col_m:
                st.markdown("**Missing from ZMS (ZFS-lager > 10, Valda Säsonger)**")
                inv_skus = set(df_s_valid['Article'])
                zms_skus = set(df_m_filtered['Article'])
                missing = list(inv_skus - zms_skus)
                st.dataframe(df_s_valid[(df_s_valid['Article'].isin(missing)) & (df_s_valid['Total_Stock'] > 10)][['Article', 'Total_Stock', 'Season']], use_container_width=True)

        with tab4:
            st.header("🌍 Manuella Landskluster - Översikt")
            # Sammanställ prestanda per land utifrån hela den uppladdade marknadsföringsfilen
            df_c_summary = df_m_raw.groupby([country_col, 'Cluster_Name']).agg({
                'Spend_Val': 'sum', 
                'Clicks_Val': 'sum', 
                'GMV_Val': 'sum',
                'Impressions_Val': 'sum'
            }).reset_index()
            
            df_c_summary['CPC'] = (df_c_summary['Spend_Val'] / df_c_summary['Clicks_Val'].replace(0, 1)).round(2)
            df_c_summary['ROAS'] = (df_c_summary['GMV_Val'] / df_c_summary['Spend_Val'].replace(0, 1)).round(2)
            
            st.dataframe(df_c_summary.sort_values('Cluster_Name'), use_container_width=True, hide_index=True)
            st.download_button("📥 Ladda ner Klusterdata CSV", df_c_summary.to_csv(index=False).encode('utf-8'), "manual_country_clusters.csv")

        with tab5:
            st.header("📈 Landsjämförelse & Trendanalys")
            if country_col:
                df_comp_raw = df_m_raw[df_m_raw[country_col].isin(selected_countries)]
                comp_type = st.radio("Välj tidsram för jämförelse:", ["Månad över Månad (MoM)", "Vecka för Vecka (Trend upp till 3 veckor)"])
                
                if comp_type == "Månad över Månad (MoM)":
                    months = sorted(df_comp_raw['Month_Num'].unique())
                    if len(months) >= 2:
                        sel_m = st.selectbox("Välj huvudmånad att analysera:", options=months, index=len(months)-1, key="comp_m_main")
                        prev_m = months[months.index(sel_m) - 1] if months.index(sel_m) > 0 else None
                        
                        if prev_m is not None:
                            st.info(f"Visar Månad {sel_m} jämfört med Månad {prev_m}")
                            
                            df_m_stats = df_comp_raw[df_comp_raw['Month_Num'].isin([sel_m, prev_m])].groupby([country_col, 'Month_Num']).agg({
                                'Spend_Val': 'sum', 'Impressions_Val': 'sum', 'Clicks_Val': 'sum', 'GMV_Val': 'sum'
                            }).reset_index()
                            
                            df_m_stats['ROAS'] = (df_m_stats['GMV_Val'] / df_m_stats['Spend_Val'].replace(0, 1)).round(2)
                            df_m_stats['COS (%)'] = ((df_m_stats['Spend_Val'] / df_m_stats['GMV_Val'].replace(0, 1)) * 100).round(1)
                            df_m_stats['CPC'] = (df_m_stats['Spend_Val'] / df_m_stats['Clicks_Val'].replace(0, 1)).round(2)
                            
                            metric_to_plot = st.selectbox("Välj mätetal för grafen:", ["ROAS", "COS (%)", "CPC", "Impressions", "GMV", "Budget Spent"], key="m_metric")
                            plot_map = {"ROAS": "ROAS", "COS (%)": "COS (%)", "CPC": "CPC", "Impressions": "Impressions_Val", "GMV": "GMV_Val", "Budget Spent": "Spend_Val"}
                            
                            df_plot = df_m_stats.copy()
                            df_plot['Tidsperiod'] = df_plot['Month_Num'].apply(lambda x: f"Månad {x}")
                            
                            fig = px.bar(df_plot, x=country_col, y=plot_map[metric_to_plot], color='Tidsperiod', barmode='group',
                                         color_discrete_sequence=["#999999", "#0b5394"],
                                         labels={plot_map[metric_to_plot]: metric_to_plot, country_col: "Land"})
                            st.plotly_chart(fig, use_container_width=True)
                            
                            st.subheader("📊 Sammanställning per marknad (Månadsvis)")
                            df_table_m = df_m_stats.rename(columns={
                                country_col: 'Land', 
                                'Month_Num': 'Månad', 
                                'Spend_Val': 'Budget spent', 
                                'Impressions_Val': 'Impressions', 
                                'Clicks_Val': 'Clicks',
                                'GMV_Val': 'GMV'
                            })[['Land', 'Månad', 'Budget spent', 'Impressions', 'Clicks', 'GMV', 'ROAS']]
                            
                            st.dataframe(df_table_m.sort_values(['Land', 'Månad']), use_container_width=True, hide_index=True)
                        else:
                            st.warning("Ingen föregående månad hittades i datan.")
                    else:
                        st.warning("Datan behöver innehålla minst två olika månader för MoM.")
                        
                else:  # --- VECKA FÖR VECKA (3 VECKOR) ---
                    weeks = sorted(df_comp_raw['Week_Num'].unique())
                    if len(weeks) >= 1:
                        selected_weeks = st.multiselect(
                            "Välj upp till 3 veckor att jämföra (visas i vald ordning):",
                            options=weeks,
                            default=weeks[-3:] if len(weeks) >= 3 else weeks,
                            max_selections=3
                        )
                        
                        if selected_weeks:
                            df_w_stats = df_comp_raw[df_comp_raw['Week_Num'].isin(selected_weeks)].groupby([country_col, 'Week_Num']).agg({
                                'Spend_Val': 'sum', 'Impressions_Val': 'sum', 'Clicks_Val': 'sum', 'GMV_Val': 'sum'
                            }).reset_index()
                            
                            df_w_stats['ROAS'] = (df_w_stats['GMV_Val'] / df_w_stats['Spend_Val'].replace(0, 1)).round(2)
                            df_w_stats['COS (%)'] = ((df_w_stats['Spend_Val'] / df_w_stats['GMV_Val'].replace(0, 1)) * 100).round(1)
                            df_w_stats['CPC'] = (df_w_stats['Spend_Val'] / df_w_stats['Clicks_Val'].replace(0, 1)).round(2)
                            
                            metric_to_plot = st.selectbox("Välj mätetal för grafen:", ["ROAS", "COS (%)", "CPC", "Impressions", "GMV", "Budget Spent"], key="w_metric")
                            plot_map = {"ROAS": "ROAS", "COS (%)": "COS (%)", "CPC": "CPC", "Impressions": "Impressions_Val", "GMV": "GMV_Val", "Budget Spent": "Spend_Val"}
                            
                            df_plot = df_w_stats.copy()
                            df_plot['Tidsperiod'] = df_plot['Week_Num'].apply(lambda x: f"Vecka {x}")
                            
                            df_plot['Tidsperiod'] = pd.Categorical(df_plot['Tidsperiod'], categories=[f"Vecka {w}" for w in selected_weeks], ordered=True)
                            df_plot = df_plot.sort_values('Tidsperiod')
                            
                            fig = px.bar(df_plot, x=country_col, y=plot_map[metric_to_plot], color='Tidsperiod', barmode='group',
                                         title=f"{metric_to_plot} utveckling över valda veckor",
                                         labels={plot_map[metric_to_plot]: metric_to_plot, country_col: "Land"})
                            st.plotly_chart(fig, use_container_width=True)
                            
                            st.subheader("📊 Sammanställning per marknad (Veckovis)")
                            df_table_w = df_w_stats.rename(columns={
                                country_col: 'Land', 
                                'Week_Num': 'Vecka', 
                                'Spend_Val': 'Budget spent', 
                                'Impressions_Val': 'Impressions', 
                                'Clicks_Val': 'Clicks', 
                                'GMV_Val': 'GMV'
                            })[['Land', 'Vecka', 'Budget spent', 'Impressions', 'Clicks', 'GMV', 'ROAS']]
                            
                            df_table_w['Vecka_Sort'] = pd.Categorical(df_table_w['Vecka'], categories=selected_weeks, ordered=True)
                            df_table_w = df_table_w.sort_values(['Land', 'Vecka_Sort']).drop(columns=['Vecka_Sort'])
                            
                            st.dataframe(df_table_w, use_container_width=True, hide_index=True)
                        else:
                            st.warning("Välj minst en vecka i listan för att generera analysen.")
                    else:
                        st.warning("Inga veckonummer hittades i den uppladdade filen.")
            else:
                st.error("Kunde inte hitta landskolumnen i marknadsföringsfilen.")

# --- TAB 6: SYNLIGHETSANALYS (VISIBILITY) ---
        with tab6:
            st.header("Synlighetsanalys per Artikel & Marknad")
            st.markdown("Översikt över artiklar drabbade av **låg synlighet** (`low_visibility`) och uppföljning av vidtagna åtgärder.")

            # Hämta endast de relevanta kolumnerna för att spara minne
            vis_cols_needed = [c for c in df_m_raw.columns if any(x in str(c).lower() for x in ['visibility', 'country', 'target', 'partner_article', 'sku', 'article_name', 'low_visibility_reason'])]
            df_m_vis_light = df_m_raw[vis_cols_needed].copy()

            # Bestäm vilken dataframe som innehåller synlighetsdatan
            # Kollar först i huvudfilen (df_m_raw), därefter i jämförelsefilen (prev_vis_file)
            target_df = None
            source_name = ""

            # Sök efter visibility-kolumnen i huvudfilen
            vis_col_main = next((c for c in df_m_raw.columns if 'visibility' in str(c).lower() and 'reason' not in str(c).lower()), None)
            
            if vis_col_main and (df_m_raw[vis_col_main].astype(str).str.contains('low_visibility', case=False).any()):
                target_df = df_m_raw
                source_name = "Huvudfilen (Fil 1)"
            elif prev_vis_file is not None:
                df_prev_temp = load_csv(prev_vis_file)
                vis_col_prev = next((c for c in df_prev_temp.columns if 'visibility' in str(c).lower() and 'reason' not in str(c).lower()), None)
                if vis_col_prev and (df_prev_temp[vis_col_prev].astype(str).str.contains('low_visibility', case=False).any()):
                    target_df = df_prev_temp
                    source_name = "Jämförelsefilen (Fil 3)"

            if target_df is not None:
                # 1. Identifiera alla nyckelkolumner i den funna filen
                v_col = next((c for c in target_df.columns if 'visibility' in str(c).lower() and 'reason' not in str(c).lower()), None)
                if not v_col and len(target_df.columns) > 21:
                    v_col = target_df.columns[21] # Kolumn V

                r_col = next((c for c in target_df.columns if 'low_visibility_reason' in str(c).lower()), None)
                if not r_col and len(target_df.columns) > 22:
                    r_col = target_df.columns[22] # Kolumn W

                c_col = next((c for c in target_df.columns if 'country' in str(c).lower() or 'target' in str(c).lower()), None)
                if not c_col and len(target_df.columns) > 14:
                    c_col = target_df.columns[14] # Kolumn O

                s_col = next((c for c in target_df.columns if any(x in str(c).lower() for x in ['partner_article', 'sku', 'configsku', 'zalando_article'])), None)

                # 2. Filtrera rader med low_visibility
                target_df['clean_vis'] = target_df[v_col].astype(str).str.strip().str.lower()
                df_low_curr = target_df[target_df['clean_vis'].str.contains('low_visibility', na=False)].copy()
                df_low_curr['Article'] = df_low_curr[s_col].apply(standardize_sku)

                # 3. Gruppera per artikel
                agg_dict = {
                    c_col: lambda x: ", ".join(sorted(set(str(v).upper() for v in x if pd.notna(v) and str(v) != '-'))),
                    s_col: 'first'
                }
                if 'article_name' in target_df.columns:
                    agg_dict['article_name'] = 'first'
                if r_col and r_col in target_df.columns:
                    agg_dict[r_col] = lambda x: ", ".join(sorted(set(str(v) for v in x if pd.notna(v) and str(v).lower() != 'nan')))

                df_vis_summary = df_low_curr.groupby('Article').agg(agg_dict).reset_index()
                df_vis_summary.rename(columns={c_col: 'Påverkade Marknader (Nu)'}, inplace=True)

                # 4. Om förra veckans fil också har laddats upp -> Kör vecka-för-vecka-jämförelse
                if prev_vis_file is not None and target_df is df_m_raw:
                    df_m_prev = load_csv(prev_vis_file)
                    p_v_col = next((c for c in df_m_prev.columns if 'visibility' in str(c).lower() and 'reason' not in str(c).lower()), None)
                    p_s_col = next((c for c in df_m_prev.columns if any(x in str(c).lower() for x in ['partner_article', 'sku', 'configsku', 'zalando_article'])), None)
                    p_c_col = next((c for c in df_m_prev.columns if 'country' in str(c).lower() or 'target' in str(c).lower()), None)

                    if p_v_col:
                        df_m_prev['Article'] = df_m_prev[p_s_col].apply(standardize_sku)
                        df_m_prev['clean_vis'] = df_m_prev[p_v_col].astype(str).str.strip().str.lower()
                        df_low_prev = df_m_prev[df_m_prev['clean_vis'].str.contains('low_visibility', na=False)].copy()

                        prev_countries = df_low_prev.groupby('Article')[p_c_col].apply(
                            lambda x: set(str(v).upper() for v in x if pd.notna(v) and str(v) != '-')
                        ).to_dict()

                        def calculate_status(row):
                            article = row['Article']
                            curr_set = set(row['Påverkade Marknader (Nu)'].split(", ")) if row['Påverkade Marknader (Nu)'] else set()
                            if article in prev_countries:
                                prev_set = prev_countries[article]
                                recovered = prev_set - curr_set
                                if recovered:
                                    return f"🟢 Förbättrad (Löst i: {', '.join(sorted(recovered))})"
                                else:
                                    return "🔴 Oförändrad (Ingen förbättring)"
                            else:
                                return "🟡 Ny drabbad artikel"

                        df_vis_summary['Status / Trend'] = df_vis_summary.apply(calculate_status, axis=1)

                        # Lägg till artiklar som blivit helt återställda (fanns förra veckan men saknas helt denna vecka)
                        curr_articles = set(df_vis_summary['Article'])
                        resolved = []
                        for art, prev_set in prev_countries.items():
                            if art not in curr_articles and prev_set:
                                resolved.append({
                                    'Article': art,
                                    'Påverkade Marknader (Nu)': "Inga (Helt återställd)",
                                    'Status / Trend': f"🟢 Helt Återställd (Löst i: {', '.join(sorted(prev_set))})"
                                })
                        if resolved:
                            df_vis_summary = pd.concat([df_vis_summary, pd.DataFrame(resolved)], ignore_index=True)
                else:
                    df_vis_summary['Status / Trend'] = "ℹ️ Ingen jämförelsefil uppladdad"

                # 5. Visa Resultat
                st.subheader(f"📊 Sammanfattning av Synlighet ({source_name})")
                kpi1, kpi2, kpi3 = st.columns(3)
                kpi1.metric("Artiklar med Låg Synlighet (Nu)", len(df_vis_summary[df_vis_summary['Påverkade Marknader (Nu)'] != "Inga (Helt återställd)"]))
                
                if prev_vis_file is not None and target_df is df_m_raw:
                    improved_count = len(df_vis_summary[df_vis_summary['Status / Trend'].str.startswith("🟢")])
                    unchanged_count = len(df_vis_summary[df_vis_summary['Status / Trend'].str.startswith("🔴")])
                    kpi2.metric("🟢 Artiklar med Förbättrad Synlighet", improved_count)
                    kpi3.metric("🔴 Oförändrade Artiklar", unchanged_count)

                st.divider()

                st.subheader("📋 Detaljerad Synlighetslista per Artikel")
                cols_to_show = ['Article']
                if 'article_name' in df_vis_summary.columns:
                    cols_to_show.append('article_name')
                cols_to_show.extend(['Påverkade Marknader (Nu)', 'Status / Trend'])
                if r_col and r_col in df_vis_summary.columns:
                    cols_to_show.append(r_col)

                st.dataframe(
                    df_vis_summary[cols_to_show].sort_values('Status / Trend'),
                    use_container_width=True,
                    hide_index=True
                )

                st.download_button(
                    "📥 Ladda ner Synlighetsrapport (CSV)",
                    df_vis_summary[cols_to_show].to_csv(index=False).encode('utf-8'),
                    "visibility_analysis.csv"
                )
            else:
                st.error("Kunde inte hitta kolumnen 'visibility' (Kolumn V) i den uppladdade filen. Kontrollera att filen du laddat upp innehåller synlighetsdata.")
else:
    st.info("👋 Everything is ready. Just upload your SKU Report and Inventory file to begin.")
