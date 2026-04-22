import streamlit as st
import pandas as pd
import io
import re

# --- Page Setup ---
st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("Swedemount Expert: Performance & Sync")
st.markdown("### Integrated: Article Sync, Stock Warnings, and Season Filtering")

# --- 1. UTILITIES ---
def clean_numeric(series):
    def fix_string(val):
        if pd.isna(val): return "0"
        val = str(val).strip()
        # Ta bort valutasymboler (€, SEK) och mellanslag
        val = re.sub(r'[^\d,.-]', '', val)
        if ',' in val and '.' in val: # Hantera format som 1.454,95
            val = val.replace('.', '').replace(',', '.')
        elif ',' in val: # Hantera format som 1454,95
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

    # A. Marketing Data Processing
    m_cols = {
        'Week': [c for c in df_m_raw.columns if 'Week' in c][0],
        'SKU': [c for c in df_m_raw.columns if 'SKU' in c][0],
        'GMV': [c for c in df_m_raw.columns if 'GMV' in c][0],
        'Spend': [c for c in df_m_raw.columns if 'Budget spent' in c or 'Budgetspent' in c][0],
        'Sold': [c for c in df_m_raw.columns if 'Items sold' in c or 'Itemssold' in c][0],
        'Campaign': [c for c in df_m_raw.columns if 'Campaign' in c][0]
    }

    df_m_raw['Week_Num'] = clean_numeric(df_m_raw[m_cols['Week']])
    df_m_raw['Article'] = df_m_raw[m_cols['SKU']].apply(standardize_sku)
    df_m_raw['GMV_Val'] = clean_numeric(df_m_raw[m_cols['GMV']])
    df_m_raw['Spend_Val'] = clean_numeric(df_m_raw[m_cols['Spend']])
    df_m_raw['Sold_Val'] = clean_numeric(df_m_raw[m_cols['Sold']])

    available_weeks = sorted(df_m_raw[df_m_raw['Week_Num'] > 0]['Week_Num'].unique().astype(int))
    latest_week = max(available_weeks) if available_weeks else 0
    
    # B. Latest Week Processing
    df_m_latest = df_m_raw[df_m_raw['Week_Num'] == latest_week].copy()
    
    def detect_group(val):
        """Strikt mappning baserad på exakta värden i Gender-kolumnen"""
        v = str(val).strip()
        # Endast dessa två kategorier tillåts i Female-gruppen
        if v in ['Damen', 'KinderMädchen']:
            return 'FEMALE'
        # Allt annat (Herren, Kinder, Unisex, KinderUnisex, KinderJungen) hamnar här
        return 'MALE_UNISEX_KIDS'
    
    gender_col = [c for c in df_m_raw.columns if 'Gender' in c][0]
    df_m_latest['Group_Draft'] = df_m_latest[gender_col].apply(detect_group)
    gender_lock = df_m_latest.sort_values('Group_Draft').groupby('Article')['Group_Draft'].first().reset_index()

    df_m_agg = df_m_latest.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum', 'Sold_Val':'sum'}).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)
    df_m_agg = pd.merge(df_m_agg, gender_lock, on='Article', how='left')

    # D. Inventory Processing
    df_s_raw['Article'] = df_s_raw.iloc[:, 4].apply(standardize_sku)
    df_s_raw['Season'] = df_s_raw.iloc[:, 8].astype(str).str.strip() 
    df_s_raw['brand'] = df_s_raw.iloc[:, 7].astype(str).str.strip()
    df_s_raw['Partner_Article_Variant'] = df_s_raw.iloc[:, 2].astype(str).str.strip() 
    
    stock_cols = [c for c in df_s_raw.columns if 'STOCK' in c.upper()]
    for col in stock_cols: 
        df_s_raw[col] = clean_numeric(df_s_raw[col])
    
    df_s_pivot = df_s_raw.groupby('Article').agg({
        **{col: 'sum' for col in stock_cols},
        'Season': 'first',
        'brand': 'first',
        'Partner_Article_Variant': 'first'
    }).reset_index()
    
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)
    
    df_s_valid = df_s_pivot[
        (df_s_pivot['Total_Stock'] > 0) & 
        (df_s_pivot['Partner_Article_Variant'].notna()) & 
        (df_s_pivot['Partner_Article_Variant'] != 'nan')
    ].copy()

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
    tab1, tab2 = st.tabs(["🚀 Kampanjfördelning", "🏷️ Varumärkesöversikt"])

    with tab1:
        if do_compare and len(available_weeks) >= 2:
            st.sidebar.subheader("Select Weeks to Compare")
            w1 = st.sidebar.selectbox("Base Week", available_weeks, index=len(available_weeks)-2)
            w2 = st.sidebar.selectbox("Comparison Week", available_weeks, index=len(available_weeks)-1)
            
            def get_week_agg(w):
                temp = df_m_raw[df_m_raw['Week_Num'] == w]
                return temp.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum', 'Sold_Val':'sum'}).reset_index()

            df_w1 = get_week_agg(w1)
            df_w2 = get_week_agg(w2)
            df_comp = pd.merge(df_w1, df_w2, on='Article', suffixes=(f'_w{w1}', f'_w{w2}'), how='outer').fillna(0)
            df_comp['GMV_Diff'] = df_comp[f'GMV_Val_w{w2}'] - df_comp[f'GMV_Val_w{w1}']

            st.header(f"📈 Performance Jämförelse: Vecka {w1} vs {w2}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Total GMV Change", f"{df_comp['GMV_Diff'].sum():,.0f}")
            c2.metric("New Articles", len(df_comp[df_comp[f'GMV_Val_w{w1}'] == 0]))
            c3.metric("Dropped Articles", len(df_comp[df_comp[f'GMV_Val_w{w2}'] == 0]))
            st.divider()

        st.header(f"📊 Kampanjfördelning (Vecka {latest_week})")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Unique Articles", len(df))
        m2.metric("Overall ROAS", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.0")
        m3.metric("Stock Alerts", len(df[(df['Tier'] == 'TOP') & (df['Days_Left'] < days_threshold) & (df['Sold_Val'] > 0)]))
        m4.metric("Matched Inventory", f"{df['Total_Stock'].sum():,.0f} units")

        st.divider()
        st.subheader("🔄 Sync Status & Clean-up")
        col_d, col_m = st.columns(2)
        
        with col_d:
            st.markdown("**Multi-Campaign Duplicates**")
            # LOGIK: Endast artiklar med Spend > 0 i den senaste veckan (df_m_latest)
            m_active_skus = df_m_latest[(df_m_latest['Article'] != 'UNDEFINED') & (df_m_latest['Spend_Val'] > 0)]
            
            # Räkna unika kampanjer per artikel
            dupe_counts = m_active_skus.groupby('Article')[m_cols['Campaign']].nunique()
            multi_skus = dupe_counts[dupe_counts > 1].index.tolist()
            
            # Skapa tabellen för export
            df_dupes_out = m_active_skus[m_active_skus['Article'].isin(multi_skus)][['Article', m_cols['Campaign'], 'GMV_Val', 'Spend_Val']].sort_values('Article')
            
            if not df_dupes_out.empty:
                st.dataframe(df_dupes_out, height=250, use_container_width=True)
                st.download_button("📥 Download Duplicates CSV", df_dupes_out.to_csv(index=False).encode('utf-8'), "multi_campaign_skus.csv")
            else:
                st.success("Inga aktiva dubbletter med spend hittades denna vecka.")
        
        with col_m:
            st.markdown("**Missing from ZMS (In Stock)**")
            inv_skus = set(df_s_valid[df_s_valid['Article'] != 'UNDEFINED']['Article'])
            zms_skus = set(df_m_agg[df_m_agg['Article'] != 'UNDEFINED']['Article'])
            missing_skus_list = list(inv_skus - zms_skus)
            
            # Ändra denna rad för att kräva mer än 10 i lager
            df_missing_raw = df_s_valid[df_s_valid['Article'].isin(missing_skus_list)][['Article', 'Total_Stock', 'Season', 'Partner_Article_Variant']]
            df_missing_raw = df_missing_raw[df_missing_raw['Total_Stock'] > 10] # Krav på > 10
            
            all_seasons = sorted(df_missing_raw['Season'].unique())
            selected_seasons = st.multiselect("Filter by Season", options=all_seasons, default=all_seasons)
            df_missing_filtered = df_missing_raw[df_missing_raw['Season'].isin(selected_seasons)]
            st.dataframe(df_missing_filtered, height=250, use_container_width=True)
            st.download_button("📥 Download Missing SKUs CSV", df_missing_filtered.to_csv(index=False).encode('utf-8'), "missing_from_zms.csv")

        st.divider()
        for group in ['FEMALE', 'MALE_UNISEX_KIDS']:
            st.subheader(f"📂 {group} Campaign Tiers")
            cols = st.columns(3)
            for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
                with cols[i]:
                    # VIKTIGT: Här filtrerar vi så att endast artiklar med lagersaldo > 0 inkluderas.
                    # Eftersom 'df' är byggd på 'df_m_agg' (som i sin tur kommer från 'df_m_latest'),
                    # så är detta automatiskt baserat på den senaste veckan.
                    subset = df[(df['Group_Draft'] == group) & (df['Tier'] == tier) & (df['Total_Stock'] > 0)]
                    
                    skus = subset['Article'].unique().tolist()
                    st.markdown(f"**{tier} {group}**")
                    st.metric("Articles", len(skus))
                    st.text_area("SKU List", ",".join(skus), height=150, key=f"t_{group}_{tier}", label_visibility="collapsed")
                    st.download_button("Export CSV", pd.DataFrame(skus).to_csv(index=False, header=False).encode('utf-8'), f"{group}_{tier}.csv", key=f"d_{group}_{tier}")

    with tab2:
        st.header("🏷️ Brand Performance Overview")
        brand_map = df_s_pivot[['Article', 'brand']].drop_duplicates('Article')
        df_m_total = df_m_raw.groupby('Article').agg({'Spend_Val': 'sum', 'GMV_Val': 'sum', 'Sold_Val': 'sum'}).reset_index()
        df_brand = pd.merge(df_m_total, brand_map, on='Article', how='left').fillna({'brand': 'Unknown'})
        
        brand_stats = df_brand.groupby('brand').agg({'Spend_Val': 'sum', 'GMV_Val': 'sum', 'Sold_Val': 'sum'}).reset_index()
        total_budget = brand_stats['Spend_Val'].sum()
        total_gmv = brand_stats['GMV_Val'].sum()

        brand_stats['Budget Share (%)'] = (brand_stats['Spend_Val'] / total_budget * 100).round(1) if total_budget > 0 else 0
        brand_stats['GMV Share (%)'] = (brand_stats['GMV_Val'] / total_gmv * 100).round(1) if total_gmv > 0 else 0
        brand_stats['ROAS'] = (brand_stats['GMV_Val'] / brand_stats['Spend_Val'].replace(0, 1)).round(2)
        brand_stats['COS (%)'] = (brand_stats['Spend_Val'] / brand_stats['GMV_Val'].replace(0, 1) * 100).round(1)

        brand_stats_display = brand_stats.rename(columns={'brand': 'Brand', 'Spend_Val': 'Total Budget', 'GMV_Val': 'Total GMV', 'Sold_Val': 'Items Sold'}).sort_values('Total GMV', ascending=False)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Budget", f"{total_budget:,.0f}")
        c2.metric("Total GMV", f"{total_gmv:,.0f}")
        c3.metric("Avg ROAS", f"{(total_gmv/total_budget if total_budget > 0 else 0):.2f}")
        c4.metric("Avg COS", f"{(total_budget/total_gmv*100 if total_gmv > 0 else 0):.1f}%")

        st.divider()
        st.dataframe(brand_stats_display, use_container_width=True, hide_index=True)
        st.download_button("📥 Exportera Varumärkesrapport", brand_stats_display.to_csv(index=False).encode('utf-8'), "brand_performance.csv")

else:
    st.info("👋 Everything is ready. Just upload your Marketing and Inventory files to begin.")
