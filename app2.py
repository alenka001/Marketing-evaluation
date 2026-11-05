import streamlit as st
import pandas as pd
import io
import re
import numpy as np

try:
    import plotly.express as px
except ImportError:
    st.error("Biblioteket 'plotly' saknas. Installera det med: pip install plotly")

# --- Page Setup ---
st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("Swedemount Expert: Global Performance & Sync")
st.markdown("### Integrated: Cyber Week Kampanjer, Bereinigte Rest-Kampagnen & Kluster")

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

def map_gender(gender_val):
    if pd.isna(gender_val):
        return 'Undefined'
    g = str(gender_val).strip().lower()
    if 'damen' in g or g == 'women':
        return 'Women'
    elif 'kinder' in g or 'kids' in g or 'mädchen' in g or 'jungen' in g:
        return 'Kids'
    elif 'herren' in g or 'men' in g or 'unisex' in g:
        return 'Men'
    return 'Undefined'

def optimize_memory(df):
    for col in df.columns:
        try:
            col_type = df[col].dtype
            if pd.api.types.is_integer_dtype(col_type):
                c_min = df[col].min()
                c_max = df[col].max()
                if c_min >= np.iinfo(np.int8).min and c_max <= np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min >= np.iinfo(np.int16).min and c_max <= np.iinfo(np.int16).max:
                    df[col] = df[col].astype(np.int16)
                elif c_min >= np.iinfo(np.int32).min and c_max <= np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
            elif pd.api.types.is_float_dtype(col_type):
                c_min = df[col].min()
                c_max = df[col].max()
                if pd.notna(c_min) and pd.notna(c_max):
                    if c_min >= np.finfo(np.float32).min and c_max <= np.finfo(np.float32).max:
                        df[col] = df[col].astype(np.float32)
            elif pd.api.types.is_object_dtype(col_type) or isinstance(col_type, pd.CategoricalDtype):
                num_unique = len(df[col].unique())
                num_total = len(df[col])
                if num_total > 0 and (num_unique / num_total) < 0.5:
                    df[col] = df[col].astype('category')
        except Exception:
            continue
    return df

@st.cache_data(show_spinner=False)
def load_csv(file):
    if file is None: return None
    raw_data = file.read(40000)
    file.seek(0)
    try: sample = raw_data.decode('utf-8')
    except: sample = raw_data.decode('latin-1')
    sep = ';' if ';' in sample else ','
    file.seek(0)
    df = pd.read_csv(file, sep=sep, encoding='utf-8' if 'utf-8' in sample else 'latin-1', low_memory=False)
    return optimize_memory(df)

# --- 2. MANUELL KLUSTER-MAPPING & CW KONSTANTEN ---
CW_COUNTRIES = {'DE', 'CH', 'AT', 'DK', 'NL', 'IT', 'FR'}
CW_BRANDS = {'swedemount', 'denim factory'}

MANUAL_CLUSTER_MAPPING = {
    'IT': 'C1 (IT, FR, ES)', 'FR': 'C1 (IT, FR, ES)', 'ES': 'C1 (IT, FR, ES)',
    'DE': 'C2 (DE, NL, BE)', 'NL': 'C2 (DE, NL, BE)', 'BE': 'C2 (DE, NL, BE)',
    'AT': 'C3 (AT, FI, PL, CZ, DK, LUX)', 'FI': 'C3 (AT, FI, PL, CZ, DK, LUX)',
    'PL': 'C3 (AT, FI, PL, CZ, DK, LUX)', 'CZ': 'C3 (AT, FI, PL, CZ, DK, LUX)',
    'DK': 'C3 (AT, FI, PL, CZ, DK, LUX)', 'LUX': 'C3 (AT, FI, PL, CZ, DK, LUX)', 'LU': 'C3 (AT, FI, PL, CZ, DK, LUX)',
    'EE': 'C4 (East & Baltikum)', 'LT': 'C4 (East & Baltikum)', 'LV': 'C4 (East & Baltikum)',
    'SI': 'C4 (East & Baltikum)', 'SK': 'C4 (East & Baltikum)', 'HU': 'C4 (East & Baltikum)',
    'RO': 'C4 (East & Baltikum)', 'BG': 'C4 (East & Baltikum)', 'HR': 'C4 (East & Baltikum)',
    'SE': 'Standalone: Sverige (SE)', 'CH': 'Standalone: Schweiz (CH)'
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
            'Month': [c for c in m_cols_list if 'month' in str(c).lower()][0] if any('month' in str(c).lower() for c in m_cols_list) else m_cols_list[0],
            'Week': [c for c in m_cols_list if 'week' in str(c).lower()][0] if any('week' in str(c).lower() for c in m_cols_list) else m_cols_list[1],
            'SKU': [c for c in m_cols_list if any(x in str(c).lower() for x in ['partner_article', 'sku', 'configsku', 'config sku'])][0],
            'GMV': [c for c in m_cols_list if 'gmv' in str(c).lower()][0] if any('gmv' in str(c).lower() for c in m_cols_list) else m_cols_list[3],
            'Spend': [c for c in m_cols_list if 'budget' in str(c).lower() and 'spent' in str(c).lower() or 'budgetspent' in str(c).lower()][0] if any('spent' in str(c).lower() for c in m_cols_list) else m_cols_list[4],
            'Sold': [c for c in m_cols_list if 'items' in str(c).lower() and 'sold' in str(c).lower() or 'itemssold' in str(c).lower()][0] if any('sold' in str(c).lower() for c in m_cols_list) else m_cols_list[5],
            'Campaign': [c for c in m_cols_list if 'campaign' in str(c).lower()][0] if any('campaign' in str(c).lower() for c in m_cols_list) else m_cols_list[6],
            'Clicks': [c for c in m_cols_list if 'clicks' in str(c).lower()][0] if any('clicks' in str(c).lower() for c in m_cols_list) else m_cols_list[7],
            'Gender': [c for c in m_cols_list if 'gender' in str(c).lower()][0] if any('gender' in str(c).lower() for c in m_cols_list) else m_cols_list[4],
            'Impressions': [c for c in m_cols_list if 'ad impressions' in str(c).lower() or 'impressions' in str(c).lower()][0] if any('impressions' in str(c).lower() for c in m_cols_list) else m_cols_list[8]
        }
        
        country_col = next((c for c in m_cols_list if 'country' in str(c).lower() or 'target' in str(c).lower()), None)
        if not country_col and len(m_cols_list) > 7: country_col = m_cols_list[7]

        # B. Grundtvätt av Marknadsföringsfil
        df_m_raw['Week_Num'] = clean_numeric(df_m_raw[m_cols['Week']]).astype(int)
        df_m_raw['Month_Num'] = clean_numeric(df_m_raw[m_cols['Month']]).astype(int)
        df_m_raw['Article'] = df_m_raw[m_cols['SKU']].apply(standardize_sku)
        df_m_raw['GMV_Val'] = clean_numeric(df_m_raw[m_cols['GMV']])
        df_m_raw['Spend_Val'] = clean_numeric(df_m_raw[m_cols['Spend']])
        df_m_raw['Sold_Val'] = clean_numeric(df_m_raw[m_cols['Sold']])
        df_m_raw['Clicks_Val'] = clean_numeric(df_m_raw[m_cols['Clicks']])
        df_m_raw['Impressions_Val'] = clean_numeric(df_m_raw[m_cols['Impressions']])
        df_m_raw['Target_Country'] = df_m_raw[country_col].astype(str).str.strip().str.upper()
        df_m_raw['Mapped_Gender'] = df_m_raw[m_cols['Gender']].apply(map_gender)
        df_m_raw['Cluster_Name'] = df_m_raw['Target_Country'].map(MANUAL_CLUSTER_MAPPING).fillna('Övriga marknader')

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
            st.header("🏳️‍🌈 Landsval")
            all_countries = sorted(df_m_raw['Target_Country'].dropna().unique().tolist())
            selected_countries = st.multiselect("Inkludera/Exkludera marknader:", options=all_countries, default=all_countries)

            st.divider()
            st.header("👁️ Synlighetsjämförelse")
            vis_file_curr = st.file_uploader("3. Synlighetsrapport - Nuvarande vecka", type="csv")
            vis_file_prev = st.file_uploader("4. (Valfri) Synlighetsrapport - Föregående vecka", type="csv")

            st.divider()
            st.header("🌍 Kluster-selection")
            all_clusters = sorted(df_m_raw['Cluster_Name'].unique().tolist())
            selected_clusters = st.multiselect("Aktiva kluster i dashboard:", options=all_clusters, default=all_clusters)

            st.divider()
            st.header("🍂 Säsongsfilter")
            df_s_raw['Season'] = df_s_raw.iloc[:, 8].fillna('').astype(str).str.strip()
            all_seasons = sorted([s for s in df_s_raw['Season'].unique() if s and s.lower() not in ['nan', 'none', '']])
            selected_seasons = st.multiselect("Välj säsonger att inkludera:", options=all_seasons, default=all_seasons)

        # D. Hantera Lagerfil & Säsong
        df_s_raw['Article'] = df_s_raw.iloc[:, 4].apply(standardize_sku)
        df_s_raw['brand'] = df_s_raw.iloc[:, 7].astype(str).str.strip()
        df_s_filtered_season = df_s_raw[df_s_raw['Season'].isin(selected_seasons)].copy()
        
        zfs_cols = [c for c in df_s_filtered_season.columns if 'ZFS' in c.upper()]
        if not zfs_cols: zfs_cols = [c for c in df_s_filtered_season.columns if 'STOCK' in c.upper()]
        for col in zfs_cols: df_s_filtered_season[col] = clean_numeric(df_s_filtered_season[col])
            
        df_s_pivot = df_s_filtered_season.groupby('Article').agg({
            **{col: 'sum' for col in zfs_cols}, 
            'Season': 'first', 
            'brand': 'first'
        }).reset_index()
        df_s_pivot['Total_Stock'] = df_s_pivot[zfs_cols].sum(axis=1)
        df_s_valid = df_s_pivot[df_s_pivot['Total_Stock'] > 0].copy()

        # E. Processing Senaste Veckan
        available_weeks = sorted(df_m_raw[df_m_raw['Week_Num'] > 0]['Week_Num'].unique())
        latest_week = max(available_weeks) if available_weeks else 0
        df_m_latest = df_m_raw[df_m_raw['Week_Num'] == latest_week].copy()

        # Brand Mapping & Gender Lock
        sku_to_brand = df_s_valid.set_index('Article')['brand'].to_dict()
        df_m_latest['Brand_Clean'] = df_m_latest['Article'].map(sku_to_brand).fillna('Other')
        art_gender_lock = df_m_latest.groupby('Article')['Mapped_Gender'].agg(lambda x: x.mode()[0] if not x.empty else 'Men').to_dict()

        # --- TABS ---
        tab_cw, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "🖤 Cyber Week Kampanjer",
            "🚀 Kampanjfördelning (Befintliga)", 
            "🏷️ Varumärkesöversikt", 
            "🔄 Sync Status", 
            "🌍 Landsklustring", 
            "📈 Landsjämförelse",
            "👁️ Synlighetsanalys"
        ])

        # =========================================================================
        # 🖤 TAB: CYBER WEEK KAMPANJER (27 DEDIZIERTE BUCKETS)
        # =========================================================================
        with tab_cw:
            st.header("🖤 Cyber Week / Black Week Kampagnen (Fokus DE, CH, AT, DK, NL, IT, FR)")
            st.markdown("""
            * **Fokus-Marken:** Swedemount & Denim Factory (exklusiv für diese 7 Länder).
            * **Deduplizierung:** Ein Artikel existiert im jeweiligen Land nur in genau einem Women-, Men- oder Kids-Bucket.
            """)
            
            cw_stock_skus = set(df_s_valid['Article'])
            df_cw_pool = df_m_latest[df_m_latest['Article'].isin(cw_stock_skus)].copy()
            df_cw_pool['Final_Gender'] = df_cw_pool['Article'].map(art_gender_lock).fillna('Men')
            
            cw_campaigns_def = [
                ('DE', ['Swedemount'], 'Women', 'CW Swedemount DE Women'),
                ('DE', ['Swedemount'], 'Men', 'CW Swedemount DE Men'),
                ('DE', ['Swedemount'], 'Kids', 'CW Swedemount DE Kids'),
                ('DE', ['Denim Factory'], 'Women', 'CW Denim Factory DE Women'),
                ('DE', ['Denim Factory'], 'Men', 'CW Denim Factory DE Men'),
                ('DE', ['Denim Factory'], 'Kids', 'CW Denim Factory DE Kids'),
                
                ('CH', ['Swedemount'], 'Women', 'CW Swedemount CH Women'),
                ('CH', ['Swedemount'], 'Men', 'CW Swedemount CH Men'),
                ('CH', ['Swedemount'], 'Kids', 'CW Swedemount CH Kids'),
                ('CH', ['Denim Factory'], 'Women', 'CW Denim Factory CH Women'),
                ('CH', ['Denim Factory'], 'Men', 'CW Denim Factory CH Men'),
                ('CH', ['Denim Factory'], 'Kids', 'CW Denim Factory CH Kids'),

                ('AT', ['Swedemount', 'Denim Factory'], 'Women', 'CW Swedemount/Denim Factory AT Women'),
                ('AT', ['Swedemount', 'Denim Factory'], 'Men', 'CW Swedemount/Denim Factory AT Men'),
                ('AT', ['Swedemount', 'Denim Factory'], 'Kids', 'CW Swedemount/Denim Factory AT Kids'),

                ('DK', ['Swedemount', 'Denim Factory'], 'Women', 'CW Swedemount/Denim Factory DK Women'),
                ('DK', ['Swedemount', 'Denim Factory'], 'Men', 'CW Swedemount/Denim Factory DK Men'),
                ('DK', ['Swedemount', 'Denim Factory'], 'Kids', 'CW Swedemount/Denim Factory DK Kids'),

                ('NL', ['Swedemount', 'Denim Factory'], 'Women', 'CW Swedemount/Denim Factory NL Women'),
                ('NL', ['Swedemount', 'Denim Factory'], 'Men', 'CW Swedemount/Denim Factory NL Men'),
                ('NL', ['Swedemount', 'Denim Factory'], 'Kids', 'CW Swedemount/Denim Factory NL Kids'),

                ('IT', ['Swedemount', 'Denim Factory'], 'Women', 'CW Swedemount/Denim Factory IT Women'),
                ('IT', ['Swedemount', 'Denim Factory'], 'Men', 'CW Swedemount/Denim Factory IT Men'),
                ('IT', ['Swedemount', 'Denim Factory'], 'Kids', 'CW Swedemount/Denim Factory IT Kids'),

                ('FR', ['Swedemount', 'Denim Factory'], 'Women', 'CW Swedemount/Denim Factory FR Women'),
                ('FR', ['Swedemount', 'Denim Factory'], 'Men', 'CW Swedemount/Denim Factory FR Men'),
                ('FR', ['Swedemount', 'Denim Factory'], 'Kids', 'CW Swedemount/Denim Factory FR Kids'),
            ]
            
            countries_cw = ['DE', 'CH', 'AT', 'DK', 'NL', 'IT', 'FR']
            cw_results = {}
            total_cw_skus = 0

            for c_country, c_brands, c_gender, c_name in cw_campaigns_def:
                brand_filter = df_cw_pool['Brand_Clean'].str.lower().isin([b.lower() for b in c_brands])
                country_filter = df_cw_pool['Target_Country'] == c_country
                gender_filter = df_cw_pool['Final_Gender'] == c_gender
                
                matched = df_cw_pool[brand_filter & country_filter & gender_filter]['Article'].unique().tolist()
                cw_results[c_name] = matched
                total_cw_skus += len(matched)

            kpi_cw1, kpi_cw2, kpi_cw3 = st.columns(3)
            kpi_cw1.metric("CW Kampagnen", len(cw_campaigns_def))
            kpi_cw2.metric("Zugewiesene Artikel (Dedupliziert)", total_cw_skus)
            kpi_cw3.metric("Fokus-Länder", len(countries_cw))
            st.divider()

            for country in countries_cw:
                with st.expander(f"📍 **Cyber Week Kampagnen für {country}**", expanded=(country in ['DE', 'CH'])):
                    country_camps = [item for item in cw_campaigns_def if item[0] == country]
                    cols_cw = st.columns(len(country_camps))
                    for idx, (c_country, c_brands, c_gender, c_name) in enumerate(country_camps):
                        with cols_cw[idx]:
                            skus = cw_results.get(c_name, [])
                            st.markdown(f"**{c_name}**")
                            st.metric("Artikel", len(skus))
                            st.text_area("SKU-Liste", ",".join(skus), height=180, key=f"txt_cw_{c_name}", label_visibility="collapsed")
                            st.download_button(
                                "📥 Export CSV", 
                                pd.DataFrame(skus).to_csv(index=False, header=False).encode('utf-8'), 
                                f"{c_name.replace(' ', '_')}.csv", 
                                key=f"btn_cw_{c_name}"
                            )

        # =========================================================================
        # 🚀 TAB 1: KAMPANJFÖRDELNING (BEREINIGTE BESTEHENDE KAMPAGNEN)
        # =========================================================================
        with tab1:
            st.header(f"📊 Reguläre Kampagnenhinker (Vecka {latest_week})")
            st.info("""
            **Deduplizierungs- und Sponsoring-Regel:**
            * In **CW-Ländern** (`DE, CH, AT, DK, NL, IT, FR`) wurden Swedemount & Denim Factory entfernt. Dort laufen nur die **übrigen Marken** (Slade, Seaside, Ellen New York etc.).
            * In **Nicht-CW-Ländern** (`SE, ES, BE, FI, PL, CZ` etc.) verbleiben **alle Marken** (inkl. Swedemount & Denim Factory) in den Hinkern.
            """)

            # Filterlogik für bestehende Kampagnen:
            # Wenn Land in CW_COUNTRIES und Marke in CW_BRANDS -> AUSSCHLIESSEN!
            is_in_cw_country = df_m_latest['Target_Country'].isin(CW_COUNTRIES)
            is_cw_brand = df_m_latest['Brand_Clean'].str.lower().isin(CW_BRANDS)
            
            # Maske: Zeige nur Artikel, die NICHT bereits in der Cyber Week des Landes gebucht sind
            df_m_regular = df_m_latest[~(is_in_cw_country & is_cw_brand)].copy()
            
            df_m_regular_filtered = df_m_regular[
                df_m_regular['Cluster_Name'].isin(selected_clusters) & 
                df_m_regular['Target_Country'].isin(selected_countries)
            ]

            m_agg_reg = df_m_regular_filtered.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum'}).reset_index()
            df_reg_global = pd.merge(m_agg_reg, df_s_valid[['Article', 'Total_Stock']], on='Article', how='inner')

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Reguläre Artikel im Umlauf", len(df_reg_global))
            col_m2.metric("Regulärer ROAS", f"{(df_reg_global['GMV_Val'].sum()/df_reg_global['Spend_Val'].sum()):.2f}" if df_reg_global['Spend_Val'].sum() > 0 else "0.0")
            col_m3.metric("ZFS-Lager (Regulär)", f"{df_reg_global['Total_Stock'].sum():,.0f} Stk.")
            st.divider()

            if not selected_clusters:
                st.info("Välj minst ett kluster i sidebaren.")
            else:
                for cluster in selected_clusters:
                    with st.expander(f"📁 **Kampanjhinkar för {cluster}**", expanded=True):
                        df_c_latest = df_m_regular[
                            (df_m_regular['Cluster_Name'] == cluster) & 
                            (df_m_regular['Target_Country'].isin(selected_countries))
                        ]
                        
                        # Kennzeichnung, welche Länder im Kluster CW sind und welche Nicht-CW
                        cluster_countries = df_c_latest['Target_Country'].unique().tolist()
                        cw_in_cluster = [c for c in cluster_countries if c in CW_COUNTRIES]
                        non_cw_in_cluster = [c for c in cluster_countries if c not in CW_COUNTRIES]
                        
                        st.caption(f"Status in diesem Kluster: CW-Länder (nur Rest-Marken): `{', '.join(cw_in_cluster) if cw_in_cluster else 'Keine'}` | Nicht-CW (alle Marken inkl. Swedemount): `{', '.join(non_cw_in_cluster) if non_cw_in_cluster else 'Keine'}`")

                        df_c_agg = df_c_latest.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum'}).reset_index()
                        df_c_agg['ROAS_Actual'] = df_c_agg['GMV_Val'] / df_c_agg['Spend_Val'].replace(0, 1)
                        df_c_merged = pd.merge(df_c_agg, df_s_valid[['Article', 'Total_Stock']], on='Article', how='inner')

                        def assign_tier(row):
                            if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas: return 'TOP'
                            elif row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas: return 'MEDIUM'
                            return 'LOW'

                        df_c_merged['Tier'] = df_c_merged.apply(assign_tier, axis=1)

                        c_cols = st.columns(3)
                        for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
                            with c_cols[i]:
                                subset = df_c_merged[df_c_merged['Tier'] == tier]
                                skus = subset['Article'].unique().tolist()
                                st.markdown(f"#### {tier}")
                                st.metric("Artiklar", len(skus))
                                st.text_area("SKU List", ",".join(skus), height=200, key=f"t_{cluster}_{tier}", label_visibility="collapsed")
                                st.download_button(
                                    f"Export {tier} CSV", 
                                    pd.DataFrame(skus).to_csv(index=False, header=False).encode('utf-8'), 
                                    f"{cluster}_{tier}_articles.csv", 
                                    key=f"d_{cluster}_{tier}"
                                )

        # =========================================================================
        # TAB 2: VARUMÄRKESÖVERSIKT
        # =========================================================================
        with tab2:
            st.header("🏷️ Varumärkesöversikt")
            df_m_agg_brand = df_m_latest.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum', 'Sold_Val':'sum'}).reset_index()
            df_brand_merged = pd.merge(df_m_agg_brand, df_s_valid[['Article', 'brand']], on='Article', how='inner')
            brand_stats = df_brand_merged.groupby('brand').agg({'Spend_Val': 'sum', 'GMV_Val': 'sum', 'Sold_Val': 'sum'}).reset_index()
            brand_stats['ROAS'] = (brand_stats['GMV_Val'] / brand_stats['Spend_Val'].replace(0, 1)).round(2)
            st.dataframe(brand_stats.sort_values('GMV_Val', ascending=False), use_container_width=True, hide_index=True)

        # =========================================================================
        # TAB 3: SYNC STATUS
        # =========================================================================
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
                zms_skus = set(df_m_latest['Article'])
                missing = list(inv_skus - zms_skus)
                st.dataframe(df_s_valid[(df_s_valid['Article'].isin(missing)) & (df_s_valid['Total_Stock'] > 10)][['Article', 'Total_Stock', 'Season']], use_container_width=True)

        # =========================================================================
        # TAB 4: LANDSKLUSTRING
        # =========================================================================
        with tab4:
            st.header("🌍 Manuella Landskluster - Översikt")
            df_c_summary = df_m_raw.groupby(['Target_Country', 'Cluster_Name']).agg({'Spend_Val': 'sum', 'Clicks_Val': 'sum', 'GMV_Val': 'sum', 'Impressions_Val': 'sum'}).reset_index()
            df_c_summary['CPC'] = (df_c_summary['Spend_Val'] / df_c_summary['Clicks_Val'].replace(0, 1)).round(2)
            df_c_summary['ROAS'] = (df_c_summary['GMV_Val'] / df_c_summary['Spend_Val'].replace(0, 1)).round(2)
            df_c_summary['Cyber_Week_Sponsoring'] = df_c_summary['Target_Country'].apply(lambda x: 'Ja (200k Pool)' if x in CW_COUNTRIES else 'Nein (Regulär)')
            st.dataframe(df_c_summary.sort_values('Cluster_Name'), use_container_width=True, hide_index=True)
            st.download_button("📥 Ladda ner Klusterdata CSV", df_c_summary.to_csv(index=False).encode('utf-8'), "manual_country_clusters.csv")

        # =========================================================================
        # TAB 5: LANDSJÄMFÖRELSE
        # =========================================================================
        with tab5:
            st.header("📈 Landsjämförelse & Trendanalys")
            if country_col:
                df_comp_raw = df_m_raw[df_m_raw['Target_Country'].isin(selected_countries)]
                comp_type = st.radio("Välj tidsram:", ["Månad över Månad (MoM)", "Vecka för Vecka (Trend upp till 3 veckor)"])
                if comp_type == "Månad över Månad (MoM)":
                    months = sorted(df_comp_raw['Month_Num'].unique())
                    if len(months) >= 2:
                        sel_m = st.selectbox("Huvudmånad:", options=months, index=len(months)-1, key="comp_m_main")
                        prev_m = months[months.index(sel_m) - 1] if months.index(sel_m) > 0 else None
                        if prev_m is not None:
                            st.info(f"Månad {sel_m} jämfört med Månad {prev_m}")
                            df_m_stats = df_comp_raw[df_comp_raw['Month_Num'].isin([sel_m, prev_m])].groupby(['Target_Country', 'Month_Num']).agg({'Spend_Val': 'sum', 'Impressions_Val': 'sum', 'Clicks_Val': 'sum', 'GMV_Val': 'sum'}).reset_index()
                            df_m_stats['ROAS'] = (df_m_stats['GMV_Val'] / df_m_stats['Spend_Val'].replace(0, 1)).round(2)
                            df_m_stats['COS (%)'] = ((df_m_stats['Spend_Val'] / df_m_stats['GMV_Val'].replace(0, 1)) * 100).round(1)
                            df_m_stats['CPC'] = (df_m_stats['Spend_Val'] / df_m_stats['Clicks_Val'].replace(0, 1)).round(2)
                            metric_to_plot = st.selectbox("Mätetal för grafen:", ["ROAS", "COS (%)", "CPC", "Impressions", "GMV", "Budget Spent"], key="m_metric")
                            plot_map = {"ROAS": "ROAS", "COS (%)": "COS (%)", "CPC": "CPC", "Impressions": "Impressions_Val", "GMV": "GMV_Val", "Budget Spent": "Spend_Val"}
                            df_plot = df_m_stats.copy()
                            df_plot['Tidsperiod'] = df_plot['Month_Num'].apply(lambda x: f"Månad {x}")
                            fig = px.bar(df_plot, x='Target_Country', y=plot_map[metric_to_plot], color='Tidsperiod', barmode='group', color_discrete_sequence=["#999999", "#0b5394"], labels={plot_map[metric_to_plot]: metric_to_plot, 'Target_Country': "Land"})
                            st.plotly_chart(fig, use_container_width=True)
                            df_table_m = df_m_stats.rename(columns={'Target_Country': 'Land', 'Month_Num': 'Månad', 'Spend_Val': 'Budget spent', 'Impressions_Val': 'Impressions', 'Clicks_Val': 'Clicks', 'GMV_Val': 'GMV'})[['Land', 'Månad', 'Budget spent', 'Impressions', 'Clicks', 'GMV', 'ROAS']]
                            st.dataframe(df_table_m.sort_values(['Land', 'Månad']), use_container_width=True, hide_index=True)
                else:
                    weeks = sorted(df_comp_raw['Week_Num'].unique())
                    if len(weeks) >= 1:
                        selected_weeks = st.multiselect("Välj veckor:", options=weeks, default=weeks[-3:] if len(weeks) >= 3 else weeks, max_selections=3)
                        if selected_weeks:
                            df_w_stats = df_comp_raw[df_comp_raw['Week_Num'].isin(selected_weeks)].groupby(['Target_Country', 'Week_Num']).agg({'Spend_Val': 'sum', 'Impressions_Val': 'sum', 'Clicks_Val': 'sum', 'GMV_Val': 'sum'}).reset_index()
                            df_w_stats['ROAS'] = (df_w_stats['GMV_Val'] / df_w_stats['Spend_Val'].replace(0, 1)).round(2)
                            df_w_stats['COS (%)'] = ((df_w_stats['Spend_Val'] / df_w_stats['GMV_Val'].replace(0, 1)) * 100).round(1)
                            df_w_stats['CPC'] = (df_w_stats['Spend_Val'] / df_w_stats['Clicks_Val'].replace(0, 1)).round(2)
                            metric_to_plot = st.selectbox("Mätetal för grafen:", ["ROAS", "COS (%)", "CPC", "Impressions", "GMV", "Budget Spent"], key="w_metric")
                            plot_map = {"ROAS": "ROAS", "COS (%)": "COS (%)", "CPC": "CPC", "Impressions": "Impressions_Val", "GMV": "GMV_Val", "Budget Spent": "Spend_Val"}
                            df_plot = df_w_stats.copy()
                            df_plot['Tidsperiod'] = df_plot['Week_Num'].apply(lambda x: f"Vecka {x}")
                            df_plot['Tidsperiod'] = pd.Categorical(df_plot['Tidsperiod'], categories=[f"Vecka {w}" for w in selected_weeks], ordered=True)
                            df_plot = df_plot.sort_values('Tidsperiod')
                            fig = px.bar(df_plot, x='Target_Country', y=plot_map[metric_to_plot], color='Tidsperiod', barmode='group', title=f"{metric_to_plot} utveckling", labels={plot_map[metric_to_plot]: metric_to_plot, 'Target_Country': "Land"})
                            st.plotly_chart(fig, use_container_width=True)
                            df_table_w = df_w_stats.rename(columns={'Target_Country': 'Land', 'Week_Num': 'Vecka', 'Spend_Val': 'Budget spent', 'Impressions_Val': 'Impressions', 'Clicks_Val': 'Clicks', 'GMV_Val': 'GMV'})[['Land', 'Vecka', 'Budget spent', 'Impressions', 'Clicks', 'GMV', 'ROAS']]
                            df_table_w['Vecka_Sort'] = pd.Categorical(df_table_w['Vecka'], categories=selected_weeks, ordered=True)
                            df_table_w = df_table_w.sort_values(['Land', 'Vecka_Sort']).drop(columns=['Vecka_Sort'])
                            st.dataframe(df_table_w, use_container_width=True, hide_index=True)

        # =========================================================================
        # TAB 6: SYNLIGHETSANALYS (VARIANT NIVÅ)
        # =========================================================================
        with tab6:
            st.header("👁️ Synlighetsanalys per Variant (Färg) & Marknad")
            if vis_file_curr is not None:
                df_curr_raw = load_csv(vis_file_curr)
                v_col_c = next((c for c in df_curr_raw.columns if 'visibility' in str(c).lower() and 'reason' not in str(c).lower()), None)
                if not v_col_c and len(df_curr_raw.columns) > 21: v_col_c = df_curr_raw.columns[21]
                r_col_c = next((c for c in df_curr_raw.columns if 'low_visibility_reason' in str(c).lower()), None)
                if not r_col_c and len(df_curr_raw.columns) > 22: r_col_c = df_curr_raw.columns[22]
                c_col_c = next((c for c in df_curr_raw.columns if 'country' in str(c).lower() or 'target' in str(c).lower()), None)
                if not c_col_c and len(df_curr_raw.columns) > 14: c_col_c = df_curr_raw.columns[14]
                var_col_c = next((c for c in df_curr_raw.columns if any(x in str(c).lower() for x in ['partner_article_variant', 'zalando_article_variant', 'variant_sku'])), None)
                sku_col_c = next((c for c in df_curr_raw.columns if any(x in str(c).lower() for x in ['partner_article', 'configsku', 'sku'])), None)
                if not var_col_c: var_col_c = sku_col_c if sku_col_c else df_curr_raw.columns[1]

                df_curr_raw['clean_vis'] = df_curr_raw[v_col_c].astype(str).str.strip().str.lower()
                df_curr_low = df_curr_raw[df_curr_raw['clean_vis'].str.contains('low_visibility', na=False)].copy()
                df_curr_low['Variant_ID'] = df_curr_low[var_col_c].astype(str).str.strip().str.upper()
                df_curr_low['Article'] = df_curr_low[sku_col_c].apply(standardize_sku) if sku_col_c else df_curr_low['Variant_ID']

                agg_dict_curr = {
                    c_col_c: lambda x: ", ".join(sorted(set(str(v).upper() for v in x if pd.notna(v) and str(v) != '-'))),
                    'Article': 'first'
                }
                if 'article_name' in df_curr_raw.columns: agg_dict_curr['article_name'] = 'first'
                if r_col_c and r_col_c in df_curr_raw.columns:
                    agg_dict_curr[r_col_c] = lambda x: ", ".join(sorted(set(str(v) for v in x if pd.notna(v) and str(v).lower() != 'nan')))

                df_curr_summary = df_curr_low.groupby('Variant_ID').agg(agg_dict_curr).reset_index()
                df_curr_summary.rename(columns={c_col_c: 'Påverkade Marknader (Nu)'}, inplace=True)

                if vis_file_prev is not None:
                    df_prev_raw = load_csv(vis_file_prev)
                    v_col_p = next((c for c in df_prev_raw.columns if 'visibility' in str(c).lower() and 'reason' not in str(c).lower()), None)
                    if not v_col_p and len(df_prev_raw.columns) > 21: v_col_p = df_prev_raw.columns[21]
                    c_col_p = next((c for c in df_prev_raw.columns if 'country' in str(c).lower() or 'target' in str(c).lower()), None)
                    if not c_col_p and len(df_prev_raw.columns) > 14: c_col_p = df_prev_raw.columns[14]
                    var_col_p = next((c for c in df_prev_raw.columns if any(x in str(c).lower() for x in ['partner_article_variant', 'zalando_article_variant', 'variant_sku'])), None)
                    if not var_col_p: var_col_p = var_col_c

                    df_prev_raw['Variant_ID'] = df_prev_raw[var_col_p].astype(str).str.strip().str.upper()
                    df_prev_raw['clean_vis'] = df_prev_raw[v_col_p].astype(str).str.strip().str.lower()
                    df_prev_low = df_prev_raw[df_prev_raw['clean_vis'].str.contains('low_visibility', na=False)].copy()

                    prev_countries = df_prev_low.groupby('Variant_ID')[c_col_p].apply(
                        lambda x: set(str(v).upper() for v in x if pd.notna(v) and str(v) != '-')
                    ).to_dict()

                    improved_list = []
                    still_affected_list = []

                    for _, row in df_curr_summary.iterrows():
                        variant = row['Variant_ID']
                        curr_set = set(row['Påverkade Marknader (Nu)'].split(", ")) if row['Påverkade Marknader (Nu)'] else set()
                        if variant in prev_countries:
                            prev_set = prev_countries[variant]
                            recovered = prev_set - curr_set
                            if recovered:
                                row_imp = row.to_dict()
                                row_imp['Förbättring'] = f"🟢 Löst i: {', '.join(sorted(recovered))}"
                                improved_list.append(row_imp)
                            row_aff = row.to_dict()
                            row_aff['Status'] = "🔴 Oförändrad"
                            still_affected_list.append(row_aff)
                        else:
                            row_aff = row.to_dict()
                            row_aff['Status'] = "🟡 Ny drabbad variant"
                            still_affected_list.append(row_aff)

                    curr_variants_set = set(df_curr_summary['Variant_ID'])
                    for var_id, prev_set in prev_countries.items():
                        if var_id not in curr_variants_set and prev_set:
                            improved_list.append({
                                'Variant_ID': var_id,
                                'Article': standardize_sku(var_id),
                                'Påverkade Marknader (Nu)': "Inga (Helt återställd)",
                                'Förbättring': f"🟢 Helt Återställd (Löst i: {', '.join(sorted(prev_set))})"
                            })

                    df_improved = pd.DataFrame(improved_list)
                    df_still_affected = pd.DataFrame(still_affected_list)

                    kpi1, kpi2, kpi3 = st.columns(3)
                    kpi1.metric("Förbättrade Varianter", len(df_improved))
                    kpi2.metric("Fortfarande Påverkade", len(df_still_affected))
                    kpi3.metric("Nya Drabbade", len([x for x in still_affected_list if x.get('Status') == "🟡 Ny drabbad variant"]))
                    st.divider()

                    sub_tab1, sub_tab2 = st.tabs(["🟢 Förbättrade Varianter", "🔴 Fortfarande Påverkade Varianter"])
                    with sub_tab1:
                        if not df_improved.empty:
                            cols_imp = ['Variant_ID', 'Article']
                            if 'article_name' in df_improved.columns: cols_imp.append('article_name')
                            cols_imp.extend(['Påverkade Marknader (Nu)', 'Förbättring'])
                            st.dataframe(df_improved[cols_imp], use_container_width=True, hide_index=True)
                            st.download_button("📥 Export CSV", df_improved[cols_imp].to_csv(index=False).encode('utf-8'), "improved_variants.csv")
                        else:
                            st.info("Inga förbättringar hittades.")
                    with sub_tab2:
                        if not df_still_affected.empty:
                            cols_aff = ['Variant_ID', 'Article']
                            if 'article_name' in df_still_affected.columns: cols_aff.append('article_name')
                            cols_aff.extend(['Påverkade Marknader (Nu)', 'Status'])
                            if r_col_c and r_col_c in df_still_affected.columns: cols_aff.append(r_col_c)
                            st.dataframe(df_still_affected[cols_aff], use_container_width=True, hide_index=True)
                            st.download_button("📥 Export CSV", df_still_affected[cols_aff].to_csv(index=False).encode('utf-8'), "still_affected_variants.csv")
                else:
                    st.info("💡 Ladda upp föregående rapport i sidebaren för att jämföra förändringar.")
                    cols_aff = ['Variant_ID', 'Article']
                    if 'article_name' in df_curr_summary.columns: cols_aff.append('article_name')
                    cols_aff.append('Påverkade Marknader (Nu)')
                    if r_col_c and r_col_c in df_curr_summary.columns: cols_aff.append(r_col_c)
                    st.dataframe(df_curr_summary[cols_aff], use_container_width=True, hide_index=True)
            else:
                st.info("👋 Ladda upp synlighetsrapporten under Fält 3 i sidebaren.")
else:
    st.info("👋 Everything is ready. Just upload your SKU Report and Inventory file to begin.")
