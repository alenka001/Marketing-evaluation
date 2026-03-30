import streamlit as st
import pandas as pd

# Page Config
st.set_page_config(page_title="Zalando Tier Manager", layout="wide")
st.title("👗 Zalando Marketing: Tier Segmentation Tool")
st.info("Upload your weekly reports to re-calculate TOP, MEDIUM, and LOW tiers.")

# --- 1. SIDEBAR: DATA INPUT ---
with st.sidebar:
    st.header("Data Sources")
    attalos_file = st.file_uploader("Attalos Profit CSV", type="csv")
    stock_file = st.file_uploader("Zalando Stock CSV (ZFS/PF)", type="csv")
    
    st.divider()
    st.header("Threshold Settings")
    min_stock_top = st.number_input("Min Stock for TOP", value=15)
    min_profit_top = st.number_input("Min Net Profit (€) for TOP", value=5.0)
    min_stock_med = st.number_input("Min Stock for MED", value=5)

# --- 2. DATA PROCESSING ---
if attalos_file and stock_file:
    # Load and Merge
    df_p = pd.read_csv(attalos_file)
    df_s = pd.read_csv(stock_file)
    
    # Ensure SKUs are strings to avoid scientific notation
    df_p['SKU'] = df_p['SKU'].astype(str)
    df_s['SKU'] = df_s['SKU'].astype(str)
    
    # Merge on SKU
    df = pd.merge(df_p, df_s, on='SKU', how='inner')
    
    # Calculate Total Stock across both warehouses
    df['Total_Stock'] = df['ZFS_Stock'] + df['PF_Stock']

    # Logic: Categorize Tiers
    def assign_tier(row):
        if row['Total_Stock'] >= min_stock_top and row['Net_Profit'] >= min_profit_top:
            return 'TOP'
        elif row['Total_Stock'] >= min_stock_med and row['Net_Profit'] > 0:
            return 'MEDIUM'
        else:
            return 'LOW'

    # Logic: Group Genders (Female vs. Male/Unisex)
    def assign_group(gender):
        g = str(gender).lower()
        if 'female' in g or 'dam' in g:
            return 'FEMALE'
        else:
            return 'MALE_UNISEX'

    df['Tier'] = df.apply(assign_tier, axis=1)
    df['Group'] = df['Gender'].apply(assign_group)

    # --- 3. DASHBOARD DISPLAY ---
    groups = ['FEMALE', 'MALE_UNISEX']
    tiers = ['TOP', 'MEDIUM', 'LOW']

    for group in groups:
        st.header(f"📂 {group} Campaigns")
        cols = st.columns(3)
        
        for i, tier in enumerate(tiers):
            with cols[i]:
                # Filter data for this specific bucket
                subset = df[(df['Group'] == group) & (df['Tier'] == tier)]
                sku_list_str = ",".join(subset['SKU'].tolist())
                
                st.subheader(f"{tier} Tier")
                st.metric("SKU Count", len(subset))
                
                # Option A: Download Button
                csv = subset[['SKU']].to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=f"📥 Download {tier} CSV",
                    data=csv,
                    file_name=f"{group}_{tier}_skus.csv",
                    mime="text/csv",
                    key=f"dl_{group}_{tier}"
                )
                
                # Option B: Quick Copy (Great for small updates)
                st.text_area(f"Copy {tier} SKUs:", value=sku_list_str, height=100, key=f"txt_{group}_{tier}")

    st.divider()
    st.subheader("Full Inventory Analysis Preview")
    st.dataframe(df[['SKU', 'Gender', 'Total_Stock', 'Net_Profit', 'Tier', 'Group']], use_container_width=True)

else:
    st.warning("Please upload both the Attalos Profit CSV and the Zalando Stock CSV in the sidebar to begin.")