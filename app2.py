import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Zalando Marketing expert", layout="wide")
st.title("📈 Zalando Campaign & Trend Dashboard")

# --- 1. SIDEBAR: DATA INPUT ---
with st.sidebar:
    st.header("📂 Upload Data")
    curr_attalos = st.file_uploader("Attalos Profit (This Week)", type="csv")
    prev_attalos = st.file_uploader("Attalos Profit (Last Week - Optional)", type="csv")
    stock_file = st.file_uploader("Zalando Stock (Current)", type="csv")
    
    st.divider()
    st.header("⚙️ Thresholds")
    top_stock = st.number_input("Min Stock for TOP", value=20)
    top_profit = st.number_input("Min Profit (€) for TOP", value=10.0)

# --- 2. LOGIC & PROCESSING ---
if curr_attalos and stock_file:
    df_curr = pd.read_csv(curr_attalos)
    df_stock = pd.read_csv(stock_file)
    
    # Standardize SKUs
    df_curr['SKU'] = df_curr['SKU'].astype(str).str.strip()
    df_stock['SKU'] = df_stock['SKU'].astype(str).str.strip()
    
    # Merge Current Data
    df = pd.merge(df_curr, df_stock, on='SKU', how='inner')
    df['Total_Stock'] = df.get('ZFS_Stock', 0) + df.get('PF_Stock', 0)

    # Trend Calculation (if previous file exists)
    if prev_attalos:
        df_prev = pd.read_csv(prev_attalos)
        df_prev['SKU'] = df_prev['SKU'].astype(str).str.strip()
        # Merge previous profit to calculate delta
        df = pd.merge(df, df_prev[['SKU', 'Net_Profit']], on='SKU', how='left', suffixes=('', '_prev'))
        df['Profit_Delta'] = df['Net_Profit'] - df['Net_Profit_prev']
    else:
        df['Profit_Delta'] = 0

    # Categorization Logic
    def assign_tier(row):
        if row['Total_Stock'] >= top_stock and row['Net_Profit'] >= top_profit:
            return 'TOP'
        elif row['Total_Stock'] >= 5 and row['Net_Profit'] > 0:
            return 'MEDIUM'
        else:
            return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)
    df['Group'] = df['Gender'].apply(lambda x: 'FEMALE' if 'FEM' in str(x).upper() else 'MALE_UNISEX')

    # --- 3. TREND VISUALIZATION ---
    st.header("📊 Weekly Performance Trends")
    t_col1, t_col2, t_col3 = st.columns(3)
    
    with t_col1:
        avg_profit = df['Net_Profit'].mean()
        delta_val = df['Profit_Delta'].mean() if prev_attalos else None
        st.metric("Avg. Profit per SKU", f"€{avg_profit:.2f}", delta=f"{delta_val:.2f}" if delta_val else None)

    with t_col2:
        top_count = len(df[df['Tier'] == 'TOP'])
        st.metric("TOP Tier Candidates", top_count)

    with t_col3:
        # Quick Chart of Profit vs Stock
        fig = px.scatter(df, x="Total_Stock", y="Net_Profit", color="Tier", 
                         hover_name="SKU", title="Profit vs Stock Distribution")
        st.plotly_chart(fig, use_container_width=True)

    # --- 4. CAMPAIGN EXPORTS ---
    st.divider()
    st.header("🎯 Campaign SKU Lists")
    
    for group in ['FEMALE', 'MALE_UNISEX']:
        st.subheader(f"Group: {group}")
        cols = st.columns(3)
        for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
            with cols[i]:
                subset = df[(df['Group'] == group) & (df['Tier'] == tier)]
                st.write(f"**{tier}** ({len(subset)} items)")
                
                # Copy-Paste String
                sku_str = ",".join(subset['SKU'].tolist())
                st.text_area(f"Copy {tier} {group}:", value=sku_str, height=80, key=f"{group}_{tier}")
                
                # Export Button
                csv = subset[['SKU']].to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Download CSV", csv, f"{group}_{tier}.csv", "text/csv", key=f"dl_{group}_{tier}")

else:
    st.warning("Please upload 'This Week's' Attalos and Stock files to generate the dashboard.")
