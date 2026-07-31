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

def optimize_memory(df):
    """Reducerar RAM-förbrukning med upp till 70% genom att optimera datatyper på ett säkert sätt."""
    for col in df.columns:
        try:
            col_type = df[col].dtype
            
            # 1. Hantera heltalskolumner (integers)
            if pd.api.types.is_integer_dtype(col_type):
                c_min = df[col].min()
                c_max = df[col].max()
                if c_min >= np.iinfo(np.int8).min and c_max <= np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min >= np.iinfo(np.int16).min and c_max <= np.iinfo(np.int16).max:
                    df[col] = df[col].astype(np.int16)
                elif c_min >= np.iinfo(np.int32).min and c_max <= np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
            
            # 2. Hantera flyttalskolumner (floats) säkert
            elif pd.api.types.is_float_dtype(col_type):
                c_min = df[col].min()
                c_max = df[col].max()
                # Om min/max är giltiga tal (inte enbart NaN)
                if pd.notna(c_min) and pd.notna(c_max):
                    if c_min >= np.finfo(np.float32).min and c_max <= np.finfo(np.float32).max:
                        df[col] = df[col].astype(np.float32)
            
            # 3. Konvertera textkolumner (objects) med få unika värden till kategorier
            elif pd.api.types.is_object_dtype(col_type) or isinstance(col_type, pd.CategoricalDtype):
                num_unique = len(df[col].unique())
                num_total = len(df[col])
                if num_total > 0 and (num_unique / num_total) < 0.5:
                    df[col] = df[col].astype('category')
        except Exception:
            # Om en specifik kolumn misslyckas lämnar vi den orörd för att förhindra krasch
            continue
            
    return df

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
    
    df = pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1', low_memory=False)
    return optimize_memory(df)

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
            st.header("TOP Tier Thresholds")
            t_stock = st.number_input("Min Stock (TOP)", value=100)
            t_roas = st.number_input("Min ROAS (TOP)", value=10.0)
    
            st.header("MEDIUM Tier Thresholds")
            m_stock = st.number_input("Min Stock (MED)", value=60)
            m_roas = st.number_input("Min ROAS (MED)", value=4.0)
            
            # --- Landsfilter ---
            st.divider()
            st.header("Landsval")
            all_countries = sorted(df_m_raw[country_col].dropna().unique().tolist())
            selected_countries = st.multiselect(
                "Inkludera/Exkludera marknader:",
                options=all_countries,
                default=all_countries,
                help="Ta bort länder härifrån för att exkludera dem från analysen."
            )

            # --- Sidomeny: Dedikerad Synlighetsjämförelse ---
            st.divider()
            st.header("👁️ Synlighetsjämförelse")
            vis_file_curr = st.file_uploader(
                "3. Synlighetsrapport - Nuvarande vecka", 
                type="csv", 
                help="Ladda upp den senaste synlighetsfilen från Zalando."
            )
            vis_file_prev = st.file_uploader(
                "4. (Valfri) Synlighetsrapport - Föregående vecka", 
                type="csv", 
                help="Ladda upp en äldre synlighetsfil för att jämföra förändringar och effekter."
            )

            # --- Kluster-val ---
            st.divider()
            st.header("Kluster-selection")
            all_clusters = sorted(df_m_raw['Cluster_Name'].unique().tolist())
            selected_clusters = st.multiselect(
                "Aktiva kluster i dashboard:",
                options=all_clusters,
                default=all_clusters
            )

            # --- Säsongsfilter (Kolumn I i lagerfilen) ---
            st.divider()
            st.header("Säsongsfilter")
            
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
        "Kampanjfördelning", 
        "Varumärkesöversikt", 
        "Sync Status", 
        "Landsklustring", 
        "Landsjämförelse",
        "Synlighetsanalys"
        ])

        # --- TAB 1: KAMPANJHINKAR PER KLUSTER ---
        with tab1:
            st.header(f"Kampanjhinkar per Kluster (Vecka {latest_week})")
            
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
                    with st.expander(f"**Kampanjhinkar för {cluster}**", expanded=True):
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
            st.header("Varumärkesöversikt")
            df_m_agg_brand = df_m_filtered.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum', 'Sold_Val':'sum'}).reset_index()
            df_brand_merged = pd.merge(df_m_agg_brand, df_s_valid[['Article', 'brand']], on='Article', how='inner')
            brand_stats = df_brand_merged.groupby('brand').agg({'Spend_Val': 'sum', 'GMV_Val': 'sum', 'Sold_Val': 'sum'}).reset_index()
            brand_stats['ROAS'] = (brand_stats['GMV_Val'] / brand_stats['Spend_Val'].replace(0, 1)).round(2)
            st.dataframe(brand_stats.sort_values('GMV_Val', ascending=False), use_container_width=True, hide_index=True)

        with tab3:
            st.header("Sync Status & Clean-up")
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
            st.header("Manuella Landskluster - Översikt")
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
            st.download_button("Ladda ner Klusterdata CSV", df_c_summary.to_csv(index=False).encode('utf-8'), "manual_country_clusters.csv")

        with tab5:
            st.header("Landsjämförelse & Trendanalys")
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
                            
                            st.subheader("Sammanställning per marknad (Månadsvis)")
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
                            
                            st.subheader("Sammanställning per marknad (Veckovis)")
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
            st.header("👁️ Synlighetsanalys per Artikel & Marknad")
            st.markdown("Jämför två synlighetsrapporter för att följa upp om vidtagna åtgärder har förbättrat artiklarnas synlighet.")

            if vis_file_curr is not None:
                # 1. Läs in nuvarande synlighetsrapport
                df_curr_raw = load_csv(vis_file_curr)
                
                # Identifiera nyckelkolumner i nuvarande fil
                v_col_c = next((c for c in df_curr_raw.columns if 'visibility' in str(c).lower() and 'reason' not in str(c).lower()), None)
                if not v_col_c and len(df_curr_raw.columns) > 21: v_col_c = df_curr_raw.columns[21]
                
                r_col_c = next((c for c in df_curr_raw.columns if 'low_visibility_reason' in str(c).lower()), None)
                if not r_col_c and len(df_curr_raw.columns) > 22: r_col_c = df_curr_raw.columns[22]
                
                c_col_c = next((c for c in df_curr_raw.columns if 'country' in str(c).lower() or 'target' in str(c).lower()), None)
                if not c_col_c and len(df_curr_raw.columns) > 14: c_col_c = df_curr_raw.columns[14]
                
                s_col_c = next((c for c in df_curr_raw.columns if any(x in str(c).lower() for x in ['partner_article', 'sku', 'configsku', 'zalando_article'])), None)

                # Filtrera low_visibility för nuvarande vecka
                df_curr_raw['clean_vis'] = df_curr_raw[v_col_c].astype(str).str.strip().str.lower()
                df_curr_low = df_curr_raw[df_curr_raw['clean_vis'].str.contains('low_visibility', na=False)].copy()
                df_curr_low['Article'] = df_curr_low[s_col_c].apply(standardize_sku)

                # Gruppera nuvarande vecka per artikel
                agg_dict_curr = {
                    c_col_c: lambda x: ", ".join(sorted(set(str(v).upper() for v in x if pd.notna(v) and str(v) != '-'))),
                    s_col_c: 'first'
                }
                if 'article_name' in df_curr_raw.columns: agg_dict_curr['article_name'] = 'first'
                if r_col_c and r_col_c in df_curr_raw.columns:
                    agg_dict_curr[r_col_c] = lambda x: ", ".join(sorted(set(str(v) for v in x if pd.notna(v) and str(v).lower() != 'nan')))

                df_curr_summary = df_curr_low.groupby('Article').agg(agg_dict_curr).reset_index()
                df_curr_summary.rename(columns={c_col_c: 'Påverkade Marknader (Nu)'}, inplace=True)

                # 2. Om en föregående rapport har laddats upp -> Utför jämförelsen
                if vis_file_prev is not None:
                    df_prev_raw = load_csv(vis_file_prev)
                    
                    v_col_p = next((c for c in df_prev_raw.columns if 'visibility' in str(c).lower() and 'reason' not in str(c).lower()), None)
                    if not v_col_p and len(df_prev_raw.columns) > 21: v_col_p = df_prev_raw.columns[21]
                    
                    c_col_p = next((c for c in df_prev_raw.columns if 'country' in str(c).lower() or 'target' in str(c).lower()), None)
                    if not c_col_p and len(df_prev_raw.columns) > 14: c_col_p = df_prev_raw.columns[14]
                    
                    s_col_p = next((c for c in df_prev_raw.columns if any(x in str(c).lower() for x in ['partner_article', 'sku', 'configsku', 'zalando_article'])), None)

                    df_prev_raw['Article'] = df_prev_raw[s_col_p].apply(standardize_sku)
                    df_prev_raw['clean_vis'] = df_prev_raw[v_col_p].astype(str).str.strip().str.lower()
                    df_prev_low = df_prev_raw[df_prev_raw['clean_vis'].str.contains('low_visibility', na=False)].copy()

                    # Ordbok med länder per artikel från föregående rapport
                    prev_countries = df_prev_low.groupby('Article')[c_col_p].apply(
                        lambda x: set(str(v).upper() for v in x if pd.notna(v) and str(v) != '-')
                    ).to_dict()

                    # Beräkna förbättrade vs påverkade
                    improved_list = []
                    still_affected_list = []

                    # Kolla nuvarande artiklar
                    for _, row in df_curr_summary.iterrows():
                        article = row['Article']
                        curr_set = set(row['Påverkade Marknader (Nu)'].split(", ")) if row['Påverkade Marknader (Nu)'] else set()
                        
                        if article in prev_countries:
                            prev_set = prev_countries[article]
                            recovered = prev_set - curr_set
                            
                            if recovered: # Delvis förbättrad
                                row_imp = row.to_dict()
                                row_imp['Förbättring'] = f"🟢 Löst i: {', '.join(sorted(recovered))}"
                                improved_list.append(row_imp)
                            
                            row_aff = row.to_dict()
                            row_aff['Status'] = "🔴 Oförändrad"
                            still_affected_list.append(row_aff)
                        else:
                            row_aff = row.to_dict()
                            row_aff['Status'] = "🟡 Ny drabbad artikel"
                            still_affected_list.append(row_aff)

                    # Kolla artiklar från förra veckan som är HELT återställda
                    curr_articles_set = set(df_curr_summary['Article'])
                    for art, prev_set in prev_countries.items():
                        if art not in curr_articles_set and prev_set:
                            improved_list.append({
                                'Article': art,
                                'Påverkade Marknader (Nu)': "Inga (Helt återställd)",
                                'Förbättring': f"🟢 Helt Återställd (Löst i: {', '.join(sorted(prev_set))})"
                            })

                    df_improved = pd.DataFrame(improved_list)
                    df_still_affected = pd.DataFrame(still_affected_list)

                    # KPI-kort
                    kpi1, kpi2, kpi3 = st.columns(3)
                    kpi1.metric("Förbättrade / Återställda Artiklar", len(df_improved))
                    kpi2.metric("Fortfarande Påverkade Artiklar", len(df_still_affected))
                    kpi3.metric("Nya Drabbade Artiklar", len([x for x in still_affected_list if x.get('Status') == "🟡 Ny drabbad artikel"]))
                    st.divider()

                    # Skapa undertabbar för strukturerad visning
                    sub_tab1, sub_tab2 = st.tabs(["🟢 Detaljerad Lista: Förbättrade Artiklar", "🔴 Detaljerad Lista: Fortfarande Påverkade"])

                    with sub_tab1:
                        st.subheader("🟢 Artiklar med Förbättrad Synlighet")
                        if not df_improved.empty:
                            cols_imp = ['Article']
                            if 'article_name' in df_improved.columns: cols_imp.append('article_name')
                            cols_imp.extend(['Påverkade Marknader (Nu)', 'Förbättring'])
                            
                            st.dataframe(df_improved[cols_imp], use_container_width=True, hide_index=True)
                            st.download_button(
                                "📥 Ladda ner Förbättrade Artiklar (CSV)",
                                df_improved[cols_imp].to_csv(index=False).encode('utf-8'),
                                "improved_visibility.csv"
                            )
                        else:
                            st.info("Inga artiklar har uppvisat förbättrad synlighet sedan förra rapporten.")

                    with sub_tab2:
                        st.subheader("🔴 Artiklar som fortfarande har Låg Synlighet")
                        if not df_still_affected.empty:
                            cols_aff = ['Article']
                            if 'article_name' in df_still_affected.columns: cols_aff.append('article_name')
                            cols_aff.extend(['Påverkade Marknader (Nu)', 'Status'])
                            if r_col_c and r_col_c in df_still_affected.columns: cols_aff.append(r_col_c)

                            st.dataframe(df_still_affected[cols_aff], use_container_width=True, hide_index=True)
                            st.download_button(
                                "📥 Ladda ner Påverkade Artiklar (CSV)",
                                df_still_affected[cols_aff].to_csv(index=False).encode('utf-8'),
                                "still_affected_visibility.csv"
                            )
                        else:
                            st.success("🎉 Inga artiklar är för närvarande drabbade!")

                else:
                    # Endast en fil uppladdad
                    st.info("💡 Ladda även upp en föregående rapport i sidebaren (Fält 4) för att se vilka artiklar som har förbättrats!")
                    st.subheader("📋 Alla Artiklar med Låg Synlighet (Nuvarande rapport)")
                    
                    cols_aff = ['Article']
                    if 'article_name' in df_curr_summary.columns: cols_aff.append('article_name')
                    cols_aff.append('Påverkade Marknader (Nu)')
                    if r_col_c and r_col_c in df_curr_summary.columns: cols_aff.append(r_col_c)

                    st.dataframe(df_curr_summary[cols_aff], use_container_width=True, hide_index=True)
                    st.download_button(
                        "📥 Ladda ner Rapport (CSV)",
                        df_curr_summary[cols_aff].to_csv(index=False).encode('utf-8'),
                        "visibility_current.csv"
                    )
            else:
                st.info("👋 Ladda upp din senast synlighetsfil i sidebaren under **'3. Synlighetsrapport - Nuvarande vecka'** för att starta analysen.")
else:
    st.info("Everything is ready. Just upload your SKU Report and Inventory file to begin.")
