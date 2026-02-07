import streamlit as st
import pandas as pd
import numpy as np
import random
from datetime import datetime, date

st.set_page_config(layout="wide", page_title="Modern Table Interactions")

st.title("⚡ Modern Streamlit Table Interactions")
st.caption("Demonstrating column pinning, validation, rich types, and selection events.")

# 1. Setup Dummy Data
# -------------------
def get_data():
    categories = ["Technology", "Finance", "Healthcare", "Energy"]
    data = []
    for i in range(1, 21):
        data.append({
            "id": f"ORD-{1000+i}",
            "active": random.choice([True, False]),
            "customer_email": f"user{i}@example.com",
            "category": random.choice(categories),
            "priority": random.randint(1, 5),
            "completion": random.randint(0, 100),
            "sales_history": [random.randint(10, 100) for _ in range(10)], # For Sparkline
            "avatar": f"https://api.dicebear.com/9.x/avataaars/svg?seed={i}",
            "website": f"https://example.com/user{i}",
            "notes": f"Notes for order {1000+i}..." if i % 3 == 0 else None
        })
    return pd.DataFrame(data)

if "df" not in st.session_state:
    st.session_state.df = get_data()

# 2. Define Column Configuration
# ------------------------------
# This determines how every column looks and behaves
column_config = {
    "id": st.column_config.TextColumn(
        "Order ID",
        help="Unique Identifier",
        width="small",
        disabled=True, # Prevent editing IDs
    ),
    "avatar": st.column_config.ImageColumn(
        "User",
        help="User Avatar",
        width="small",
    ),
    "active": st.column_config.CheckboxColumn(
        "Status",
        default=False,
    ),
    "customer_email": st.column_config.TextColumn(
        "Email (Validated)",
        help="Must end in @example.com",
        validate=r"^[a-zA-Z0-9._%+-]+@example\.com$", # Regex validation
        required=True,
    ),
    "category": st.column_config.SelectboxColumn(
        "Category",
        options=["Technology", "Finance", "Healthcare", "Energy", "Retail"],
        width="medium",
    ),
    "priority": st.column_config.NumberColumn(
        "Priority",
        min_value=1,
        max_value=5,
        step=1,
        format="%d ⭐", # Format with emoji
    ),
    "completion": st.column_config.ProgressColumn(
        "Progress",
        min_value=0,
        max_value=100,
        format="%f%%",
    ),
    "sales_history": st.column_config.LineChartColumn(
        "Sales Trend",
        y_min=0,
        y_max=100,
        width="medium",
        help="Last 10 days of sales activity"
    ),
    "website": st.column_config.LinkColumn(
        "Profile Link",
        display_text="Open Profile"
    )
}

# 3. Selectable Data Table (st.dataframe)
# ----------------------------------------
st.subheader("Selectable Data Grid")
st.caption("Click rows to select them. Selection details appear below.")

event = st.dataframe(
    st.session_state.df,
    column_config=column_config,
    column_order=["id", "avatar", "active", "customer_email", "category", "completion", "sales_history", "priority", "website", "notes"],
    hide_index=True,
    use_container_width=True,
    on_select="rerun",
    selection_mode="multi-row",
    key="viewer"
)

# 4. Handle Selections
# --------------------
selection = event.selection

col1, col2 = st.columns([1, 2])

with col1:
    st.info("💡 **Tip:** Click rows to select them. Hold Ctrl/Cmd for multi-select.")
    
    if selection and selection.rows:
        selected_indices = selection.rows
        st.write(f"**Selected {len(selected_indices)} row(s):**")

        selected_data = st.session_state.df.iloc[selected_indices]

        for _, row in selected_data.iterrows():
            with st.expander(f"Order {row['id']}", expanded=True):
                st.write(f"**Category:** {row['category']}")
                st.write(f"**Email:** {row['customer_email']}")
                st.metric("Completion", f"{row['completion']}%")
    else:
        st.write("No rows selected.")

with col2:
    st.write("**Live Data Analysis:**")

    current_df = st.session_state.df
    active_count = current_df[current_df["active"] == True].shape[0]
    avg_progress = current_df["completion"].mean()

    m1, m2, m3 = st.columns(3)
    m1.metric("Active Orders", active_count)
    m2.metric("Avg Progress", f"{avg_progress:.1f}%")
    m3.metric("Total Rows", len(current_df))

    if not current_df.empty:
        cat_counts = current_df["category"].value_counts()
        st.bar_chart(cat_counts, horizontal=True, height=200)

st.divider()

# 5. Editable Data Table (st.data_editor)
# ----------------------------------------
st.subheader("Editable Data Grid")
st.caption("Double-click cells to edit. Try an invalid email to see validation.")

edited_df = st.data_editor(
    st.session_state.df,
    column_config=column_config,
    column_order=["id", "avatar", "active", "customer_email", "category", "completion", "sales_history", "priority", "website", "notes"],
    hide_index=True,
    num_rows="dynamic",
    use_container_width=True,
    key="editor"
)

# 6. Save Changes
# ----------------
if st.button("Save Changes to Database", type="primary"):
    st.session_state.df = edited_df
    st.success(f"Successfully saved {len(edited_df)} rows!")