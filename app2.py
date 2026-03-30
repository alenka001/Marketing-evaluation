import streamlit as st
import pandas as pd

st.set_page_config(page_title="Zalando Marketing Specialist", layout="wide")
st.title("📊 Zalando Campaign Optimizer")

# --- 1. SIDEBAR: DATA INPUT & COLUMN MAPPING ---
with st.sidebar:
    st.header("1. Upload Files")
    attalos_file = st.file_uploader("Attalos Profit CSV", type="csv")
    stock_file = st.file_uploader("Zalando Stock CSV", type="csv")
    
    st.divider()
    st.header("2. Logic Settings")
    min_stock_top = st.number_input("Min Stock for TOP", value=15)
    min_profit_top = st.number_input("Min Net Profit (€) for TOP", value=5.0)

# --- 2. DATA PROCESSING ---
if attalos_file and stock_file:
    df_p = pd.read_csv(attalos_file)
    df_s = pd.read_csv(stock_file)
    
    # DYNAMIC MAPPING: Let the user choose the columns if they differ
    st.sidebar.subheader("3. Map Columns")
    sku_col = st.sidebar.selectbox("SKU Column (Attalos)", df_p.columns, index=0)
    profit_col = st.sidebar.selectbox("Profit Column (Attalos)", df_p.columns)
    gender_col = st.sidebar.selectbox("Gender Column (Stock)", df_s.columns)
    
    # Merge and Clean
    df_p[sku_col] = df_p[sku_col].astype(str).str.strip()
    df_s['SKU'] = df_s['SKU'].astype(str).str.strip()
    
    df = pd.merge(df_p, df_s, left_on=sku_col, right_on='SKU', how='inner')
    
    # Logic: Total Stock (ZFS + PF)
    # Using .get() to avoid errors if one warehouse column is missing
    df['Total_Stock'] = df.get('ZFS_Stock', 0) + df.get('PF_Stock', 0)

    # Logic: Campaign Tiers
    def assign_tier(row):
        if row['Total_Stock'] >= min_stock_top and row[profit_col] >= min_profit_top:
            return 'TOP'
        elif row['Total_Stock'] >= 5 and row[profit_col] > 0:
            return 'MEDIUM'
        else:
            return 'LOW'

    # Logic: Gender Grouping (Female vs Combined Male/Unisex)
    def assign_group(val):
        val = str(val).upper()
        if 'FEMALE' in val or 'DAM' in val or 'WMS' in val:
            return 'FEMALE'
        else:
            return 'MALE_UNISEX'

    df['Tier'] = df.apply(assign_tier, axis=1)
    df['Group'] = df[gender_col].apply(assign_group)
    df['Campaign_Key'] = df['Group'] + "_" + df['Tier']

    # --- 3. DASHBOARD OUTPUT ---
    st.header("Weekly SKU Exports")
    
    # Define the 6 specific campaign buckets
    campaigns = [
        ('FEMALE', 'TOP'), ('FEMALE', 'MEDIUM'), ('FEMALE', 'LOW'),
        ('MALE_UNISEX', 'TOP'), ('MALE_UNISEX', 'MEDIUM'), ('MALE_UNISEX', 'LOW')
    ]

    # Display in a grid
    rows = [st.columns(3), st.columns(3)]
    for idx, (group, tier) in enumerate(campaigns):
        col_idx = idx % 3
        row_idx = idx // 3
        
        with rows[row_idx][col_idx]:
            key = f"{group}_{tier}"
            subset = df[df['Campaign_Key'] == key]
            
            st.subheader(f"{group} - {tier}")
            st.metric("Count", len(subset))
            
            # Formatted string for quick copy-paste into Zalando
            sku_string = ",".join(subset['SKU'].tolist())
            st.text_area("Copy SKUs:", value=sku_string, height=100, key=f"text_{key}")
            
            # Download Button
            csv = subset[['SKU']].to_csv(index=False, header=False).encode('utf-8')
            st.download_button(f"📥 Download {tier}", csv, f"{key}.csv", "text/csv")

    st.divider()
    with st.expander("🔍 View Raw Analysis Table"):
        st.dataframe(df[[sku_col, gender_col, 'Total_Stock', profit_col, 'Tier', 'Group']])

else:
    st.info("👋 Welcome! Please upload your Attalos and Zalando CSVs in the sidebar to generate your weekly campaigns.")
