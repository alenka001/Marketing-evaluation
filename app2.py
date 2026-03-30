import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("🚀 Zalando Campaign & Trend Dashboard")

# --- 1. SIDEBAR: DATA INPUT ---
with st.sidebar:
    st.header("📂 Data Upload")
    curr_attalos = st.file_uploader("Attalos Profit (Current Week)", type="csv")
    prev_attalos = st.file_uploader("Attalos Profit (Last Week)", type="csv")
    stock_file = st.file_uploader("Zalando Stock (Current)", type="csv")
    
    st.divider()
    st.header("⚙️ Strategy Thresholds")
    top_stock = st.number_input("Min Stock for TOP", value=20)
    top_profit = st.number_input("Min Profit (€) for TOP", value=10.0)
    test_period_days = st.sidebar.info("Items found only in 'Current Week' will be moved to TEST tier.")

# --- 2. LOGIC & PROCESSING ---
if curr_attalos and stock_file and prev_attalos:
    df_curr = pd.read_csv(curr_attalos)
    df_prev = pd.read_csv(prev_attalos)
    df_stock = pd.read_csv(stock_file)
    
    # Standardize SKUs to prevent merge errors
    for d in [df_curr, df_prev, df_stock]:
        d['SKU'] = d['SKU'].astype(str).str.strip()
    
    # Identify New Arrivals (In current, but not in previous)
    new_skus = set(df_curr['SKU']) - set(df_prev['SKU'])

    # Merge Current Profit + Stock
    df = pd.merge(df_curr, df_stock, on='SKU', how='inner')
    df['Total_Stock'] = df.get('ZFS_Stock', 0) + df.get('PF_Stock', 0)

    # Merge Previous Profit for Trend Analysis
    df = pd.merge(df, df_prev[['SKU', 'Net_Profit']], on='SKU', how='left', suffixes=('', '_prev'))
    df['Profit_Delta'] = df['Net_Profit'] - df['Net_Profit_prev'].fillna(0)

    # Categorization Logic including NEW Arrivals
    def assign_tier(row):
        if row['SKU'] in new_skus:
            return 'TEST (NEW)'
        if row['Total_Stock'] >= top_stock and row['Net_Profit'] >= top_profit:
            return 'TOP'
        elif row['Total_Stock'] >= 5 and row['Net_Profit'] > 0:
            return 'MEDIUM'
        else:
            return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)
    df['Group'] = df['Gender'].apply(lambda x: 'FEMALE' if 'FEM' in str(x).upper() else 'MALE_UNISEX')

    # --- 3. PERFORMANCE VISUALS ---
    st.header("📈 Inventory & Profit Health")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Avg. Profit", f"€{df['Net_Profit'].mean():.2f}", delta=f"{df['Profit_Delta'].mean():.2f}")
    m2.metric("New Arrivals", len(new_skus))
    m3.metric("TOP Tier SKUs", len(df[df['Tier'] == 'TOP']))
    m4.metric("LOW Tier (Dead Stock)", len(df[df['Tier'] == 'LOW']))

    # --- 4. THE 8 CAMPAIGN EXPORTS (4 per Gender Group) ---
    st.divider()
    all_tiers = ['TOP', 'MEDIUM', 'LOW', 'TEST (NEW)']
    
    for group in ['FEMALE', 'MALE_UNISEX']:
        st.subheader(f"📂 {group} Campaigns")
        cols = st.columns(4)
        for i, tier in enumerate(all_tiers):
            with cols[i]:
                subset = df[(df['Group'] == group) & (df['Tier'] == tier)]
                st.markdown(f"**{tier}**")
                st.caption(f"{len(subset)} Articles")
                
                # SKU String for Quick Copy
                sku_str = ",".join(subset['SKU'].tolist())
                st.text_area("SKU List:", value=sku_str, height=100, key=f"txt_{group}_{tier}", label_visibility="collapsed")
                
                # CSV Export
                csv = subset[['SKU']].to_csv(index=False, header=False).encode('utf-8')
                st.download_button("📥 Export", csv, f"{group}_{tier}.csv", "text/csv", key=f"dl_{group}_{tier}")

    # --- 5. PROFIT TREND TABLE ---
    st.divider()
    with st.expander("🔍 Deep Dive: SKU Trend Analysis"):
        st.dataframe(df[['SKU', 'Net_Profit', 'Profit_Delta', 'Total_Stock', 'Tier']].sort_values(by='Profit_Delta', ascending=False))

else:
    st.warning("⚠️ Action Required: Please upload all three files (This Week, Last Week, and Stock) to activate the Trend and New Arrival detection.")
