import streamlit as st
import pandas as pd
from datetime import datetime, date
from pathlib import Path
import re
import streamlit_authenticator as stauth

# -------------------------------------------------------
# CONFIG
# -------------------------------------------------------
st.set_page_config(page_title="Repair Tracker", page_icon="🔧", layout="wide")

# -------------------------------------------------------
# LOGIN GUARD
# -------------------------------------------------------
def _to_plain(obj):
    # Convert Streamlit Secrets (and nested mappings) to normal dicts
    try:
        return {k: _to_plain(v) for k, v in obj.items()}
    except Exception:
        return obj

cfg_plain = _to_plain(st.secrets.get("auth", {}))
if not cfg_plain:
    st.error("No [auth] block found in secrets.toml")
    st.stop()

cookie_cfg = cfg_plain.get("cookie", {})
creds_cfg = cfg_plain.get("credentials", {})

required_cookie_keys = {"name", "key", "expiry_days"}
if not required_cookie_keys.issubset(cookie_cfg.keys()):
    st.error("Missing cookie settings in [auth.cookie]")
    st.stop()
if "usernames" not in creds_cfg:
    st.error("Missing usernames under [auth.credentials.usernames]")
    st.stop()

authenticator = stauth.Authenticate(
    creds_cfg,
    cookie_cfg["name"],
    cookie_cfg["key"],
    cookie_cfg["expiry_days"],
)

name, auth_status, username = authenticator.login(
    fields={
        "Form name": "Login",
        "Username": "Username",
        "Password": "Password",
        "Login": "Login",
    }
)

if not auth_status:
    st.stop()

authenticator.logout("Logout", "sidebar")
st.caption(f"Signed in as {name}")

# -------------------------------------------------------
# APP PATHS
# -------------------------------------------------------
st.title("🔧 Repair Tracker")
APP_DIR = Path(__file__).parent
REPAIRS_CSV = APP_DIR / "repairs_data.csv"
TRUCKS_CSV = APP_DIR / "trucks_data.csv"
ALERTS_CSV = APP_DIR / "alerts_data.csv"
BACKUPS_DIR = APP_DIR / "Backups"
BACKUPS_DIR.mkdir(exist_ok=True)

# Default alert types (used as seed only)
ALERT_TYPES = [
    "Oil Change - PM Service","Truck Inspection","Radiator","Electrical","Brakes","Tires",
    "Hydraulic / PTO","Tool Boxes","Winch Cable","Coolant Hose","Air Hose","Air Bags",
    "Shocks","CARB Smog Test","Transmission","Steering","Suspension","In-Cab","Misc.","Fuel",
    "Other (type below)"
]

# -------------------------------------------------------
# UTILS
# -------------------------------------------------------
def backup_df_csv(src_path: Path, df: pd.DataFrame):
    today = datetime.now().strftime("%Y-%m-%d")
    snap = BACKUPS_DIR / f"{src_path.stem}_{today}.csv"
    if not snap.exists():
        df.to_csv(snap, index=False)

def save_df_csv(path: Path, df: pd.DataFrame):
    df.to_csv(path, index=False)
    backup_df_csv(path, df)

def load_df_csv(path: Path, default_df: pd.DataFrame):
    if path.exists():
        df = pd.read_csv(path)
        for col in default_df.columns:
            if col not in df.columns:
                df[col] = "" if default_df[col].dtype == "object" else 0
        return df
    return default_df.copy()

def status_chip(s):
    s = (s or "").strip()
    mapping = {"Open":"🟡 Open","Scheduled":"🔵 Scheduled","Completed":"🟢 Completed"}
    return mapping.get(s,s)

def calc_table_height(n_rows, max_visible=30):
    return 40 + (min(n_rows,max_visible)*28)

# -------------------------------------------------------
# CSS HIGHLIGHTING (Dark/Light Safe)
# -------------------------------------------------------
st.markdown("""
<style>
.status-open td {background-color: rgba(255,230,140,0.25) !important;}
.status-scheduled td {background-color: rgba(135,206,250,0.25) !important;}
.status-completed td {background-color: rgba(144,238,144,0.25) !important;}
[data-testid="stDataFrame"] tbody tr:hover td {background-color: rgba(200,200,200,0.15) !important;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------
# SEED DATA
# -------------------------------------------------------
initial_trucks = {
    "Truck #": ["S1","S2","FB-2","FB-3","FB-4","FB-6","FB-7"],
    "Truck Type": ["2022 FORD F150","2025 FORD F150","2023 INTERNATIONAL","2020 FREIGHTLINER","2023 ISUZU NRR","2023 PETERBILT 337","2022 HINO L6"],
    "Service Type": ["SERVICE","SERVICE","FLATBED","FLATBED","FLATBED","FLATBED","FLATBED"]
}
default_trucks_df = pd.DataFrame(initial_trucks)

sample_repairs = pd.DataFrame({
    "Ticket ID":[1,1,2],
    "Unit #":["FB-3","FB-3","S1"],
    "YMM":["2020 FREIGHTLINER","2020 FREIGHTLINER","2022 FORD F150"],
    "Alert Type/Issue":["Brakes","Transmission","Oil Change - PM Service"],
    "Description":["Front pads worn","Transmission leak","Oil + filter change"],
    "Mileage":[32000,32000,28000],
    "Date":[datetime.now().strftime("%m/%d/%Y")]*3,
    "Scheduled":["","",""],
    "Priority Tier (1/2/3)":["Tier 2 (High)","Tier 2 (High)","Tier 3 (PM)"],
    "Assigned to":["Rigo","Rigo","Rigo"],
    "Status":["Open","Scheduled","Completed"],
    "Open/Miles at":[datetime.now().strftime("%m/%d/%Y")]*3,
    "Downtime (Days)":[0,0,0],
    "Cost":[0,0,0],
    "Completed Date":["","",""],
    "Notes":["","",""]
})

default_alerts_df = pd.DataFrame({"Alert Type": ALERT_TYPES})

# -------------------------------------------------------
# STATE INIT
# -------------------------------------------------------
if "df_trucks" not in st.session_state:
    st.session_state.df_trucks = load_df_csv(TRUCKS_CSV, default_trucks_df)

if "df_repairs" not in st.session_state:
    st.session_state.df_repairs = load_df_csv(REPAIRS_CSV, sample_repairs)

if "df_alerts" not in st.session_state:
    st.session_state.df_alerts = load_df_csv(ALERTS_CSV, default_alerts_df)

df_trucks = st.session_state.df_trucks
df_repairs = st.session_state.df_repairs
df_alerts = st.session_state.df_alerts

truck_to_ymm = dict(zip(df_trucks["Truck #"], df_trucks["Truck Type"]))
alert_options = df_alerts["Alert Type"].dropna().astype(str).tolist()

# -------------------------------------------------------
# SIDEBAR NAV
# -------------------------------------------------------
st.sidebar.title("Actions")
action = st.sidebar.selectbox(
    "Choose Action",
    ["View & Edit Repairs","Add & Update Ticket","Manage Trucks","Manage Alerts","Trend"]
)

# -------------------------------------------------------
# VIEW + EDIT (Unified - Inline Editable using Ticket ID)
# -------------------------------------------------------
if action == "View & Edit Repairs":
    st.subheader("View & Edit Repairs")

    # Filters
    with st.expander("Filters", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            f_status = st.multiselect("Status", sorted(df_repairs["Status"].dropna().unique()))
            f_assigned = st.multiselect("Assigned To", sorted(df_repairs["Assigned to"].dropna().unique()))
        with c2:
            f_unit = st.multiselect("Unit #", sorted(df_repairs["Unit #"].dropna().unique()))
            f_priority = st.multiselect("Priority", sorted(df_repairs["Priority Tier (1/2/3)"].dropna().unique()))
        with c3:
            query = st.text_input("Search text (Desc / Notes / Issue)").strip()

    # Filter logic
    view_df = df_repairs.copy()
    if f_status:
        view_df = view_df[view_df["Status"].isin(f_status)]
    if f_assigned:
        view_df = view_df[view_df["Assigned to"].isin(f_assigned)]
    if f_unit:
        view_df = view_df[view_df["Unit #"].isin(f_unit)]
    if f_priority:
        view_df = view_df[view_df["Priority Tier (1/2/3)"].isin(f_priority)]
    if query:
        patt = re.compile(re.escape(query), re.IGNORECASE)
        mask = (
            view_df["Description"].fillna("").str.contains(patt)
            | view_df["Alert Type/Issue"].fillna("").str.contains(patt)
            | view_df["Notes"].fillna("").str.contains(patt)
        )
        view_df = view_df[mask]

    # Status chip column
    view_df.insert(1, "Status ⬤", view_df["Status"].map(status_chip).fillna(""))

    # Prepare clean unique columns
    editable_source = view_df.loc[:, ~view_df.columns.duplicated()].reset_index(drop=True)

    # Editable table
    st.caption("Click directly in any cell to edit - changes save automatically.")
    edited_df = st.data_editor(
        editable_source,
        use_container_width=True,
        hide_index=True,
        height=calc_table_height(len(view_df)),
        column_config={
            "Ticket ID": st.column_config.NumberColumn("Ticket ID", disabled=True),
            "Status ⬤": st.column_config.TextColumn("Status ⬤", disabled=True),
            "Status": st.column_config.SelectboxColumn("Status", options=["Open", "Scheduled", "Completed"]),
            "Priority Tier (1/2/3)": st.column_config.SelectboxColumn(
                "Priority Tier (1/2/3)",
                options=[
                    "Tier 1 (Critical)",
                    "Tier 2 (High)",
                    "Tier 3 (PM)",
                    "Tier 4 (Non-Critical)",
                ],
            ),
            "Assigned to": st.column_config.TextColumn("Assigned to"),
            "Alert Type/Issue": st.column_config.TextColumn("Alert Type/Issue"),
            "Downtime (Days)": st.column_config.NumberColumn("Downtime (Days)", min_value=0, step=1),
            "Cost": st.column_config.NumberColumn("Cost", min_value=0.0, step=1.0, format="$%.2f"),
            "Notes": st.column_config.TextColumn("Notes"),
        },
        key="editable_repairs",
    )

    # Auto-save changes
    if not edited_df.equals(view_df.reset_index(drop=True)):
        for _, row in edited_df.iterrows():
            ticket_id = row["Ticket ID"]
            mask = (
                (st.session_state.df_repairs["Ticket ID"] == ticket_id)
                & (st.session_state.df_repairs["Alert Type/Issue"] == row["Alert Type/Issue"])
            )
            if mask.any():
                for col in [
                    "Status",
                    "Priority Tier (1/2/3)",
                    "Assigned to",
                    "Alert Type/Issue",
                    "Downtime (Days)",
                    "Cost",
                    "Notes",
                ]:
                    st.session_state.df_repairs.loc[mask, col] = row[col]

                # Completed date logic
                if row["Status"] == "Completed":
                    st.session_state.df_repairs.loc[mask, "Completed Date"] = date.today().strftime("%m/%d/%Y")
                else:
                    st.session_state.df_repairs.loc[mask, "Completed Date"] = ""

        save_df_csv(REPAIRS_CSV, st.session_state.df_repairs)
        st.toast("Changes saved automatically", icon="💾")

    # Totals (Downtime counted once per Ticket ID)
    total_repairs = len(view_df)
    total_cost = pd.to_numeric(view_df["Cost"], errors="coerce").sum()
    unique_tickets = view_df.drop_duplicates(subset=["Ticket ID"])
    total_down = pd.to_numeric(unique_tickets["Downtime (Days)"], errors="coerce").sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Repairs", total_repairs)
    c2.metric("Downtime (Days)", int(total_down))
    c3.metric("Total Cost", f"${total_cost:,.2f}")

# -------------------------------------------------------
# ADD & UPDATE TICKET (with custom alert, no delete here)
# -------------------------------------------------------
elif action == "Add & Update Ticket":
    st.subheader("Add & Update Ticket")

    tickets = sorted(st.session_state.df_repairs["Ticket ID"].dropna().unique().tolist())
    ticket_choice = st.selectbox("Select Ticket", ["Create New Ticket"] + [str(t) for t in tickets])

    if ticket_choice == "Create New Ticket":
        next_id = (st.session_state.df_repairs["Ticket ID"].max() + 1) if not st.session_state.df_repairs.empty else 1
        ticket_id = next_id
    else:
        ticket_id = int(ticket_choice)

    c1,c2 = st.columns(2)
    with c1:
        unit = st.selectbox("Unit #", [""] + df_trucks["Truck #"].tolist())
        ymm = truck_to_ymm.get(unit,"")
        st.text_input("YMM", value=ymm, disabled=True)
        assigned = st.text_input("Assigned To")
    with c2:
        priority = st.selectbox("Priority", ["Tier 1 (Critical)","Tier 2 (High)","Tier 3 (PM)","Tier 4 (Non-Critical)"])
        overall_status = st.selectbox("Overall Ticket Status", ["Open","Scheduled","Completed"])
        notes_main = st.text_area("Notes (applies to all)")

    st.caption("Add Multiple Alerts to This Ticket")

    # Editable alert table with custom type support (uses managed alert_options)
    new_alerts = st.data_editor(
        pd.DataFrame(columns=["Alert Type/Issue","Custom Type","Description","Mileage","Status"]),
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Alert Type/Issue": st.column_config.SelectboxColumn("Alert Type/Issue", options=alert_options),
            "Custom Type": st.column_config.TextColumn("Custom Type (if Other selected)"),
            "Description": st.column_config.TextColumn("Description"),
            "Mileage": st.column_config.NumberColumn("Mileage", min_value=0, step=1),
            "Status": st.column_config.SelectboxColumn("Status", options=["Open","Scheduled","Completed"])
        },
        height=280
    )

    if st.button("💾 Save Ticket & Alerts"):
        for _, row in new_alerts.iterrows():
            alert_type = str(row["Alert Type/Issue"]).strip()
            if not alert_type:
                continue
            # Allow custom text if "Other (type below)" is selected
            if alert_type == "Other (type below)" and str(row.get("Custom Type", "")).strip():
                alert_type = str(row["Custom Type"]).strip()

            completed_date = date.today().strftime("%m/%d/%Y") if row["Status"] == "Completed" else ""
            new_row = {
                "Ticket ID": ticket_id,
                "Unit #": unit,
                "YMM": ymm,
                "Alert Type/Issue": alert_type,
                "Description": row["Description"],
                "Mileage": int(row["Mileage"] or 0),
                "Date": date.today().strftime("%m/%d/%Y"),
                "Scheduled": date.today().strftime("%m/%d/%Y") if row["Status"]=="Scheduled" else "",
                "Priority Tier (1/2/3)": priority,
                "Assigned to": assigned,
                "Status": row["Status"],
                "Open/Miles at": date.today().strftime("%m/%d/%Y"),
                "Downtime (Days)": 0,
                "Cost": 0.0,
                "Completed Date": completed_date,
                "Notes": notes_main
            }
            st.session_state.df_repairs = pd.concat(
                [st.session_state.df_repairs, pd.DataFrame([new_row])],
                ignore_index=True
            )
        save_df_csv(REPAIRS_CSV, st.session_state.df_repairs)
        st.success(f"Ticket {ticket_id} saved with {len(new_alerts)} alerts!")

    # Show existing alerts for this ticket (edit only, no delete)
    existing = st.session_state.df_repairs[st.session_state.df_repairs["Ticket ID"] == ticket_id]
    if not existing.empty:
        st.divider()
        st.caption("Existing Alerts for This Ticket")
        edit_existing = st.data_editor(
            existing.reset_index().rename(columns={"index":"RowID"}),
            use_container_width=True,
            hide_index=True,
            column_config={
                "RowID": st.column_config.NumberColumn("RowID", disabled=True),
                "Status": st.column_config.SelectboxColumn("Status", options=["Open","Scheduled","Completed"]),
                "Cost": st.column_config.NumberColumn("Cost", min_value=0.0, step=1.0, format="$%.2f"),
                "Notes": st.column_config.TextColumn("Notes")
            },
            height=calc_table_height(len(existing),20)
        )
        if st.button("💾 Update Existing Alerts"):
            for _, row in edit_existing.iterrows():
                rid = row["RowID"]
                st.session_state.df_repairs.loc[rid, edit_existing.columns] = row.values
                if row["Status"] == "Completed" and not str(row["Completed Date"]).strip():
                    st.session_state.df_repairs.at[rid,"Completed Date"] = date.today().strftime("%m/%d/%Y")
                elif row["Status"] != "Completed":
                    st.session_state.df_repairs.at[rid,"Completed Date"] = ""
            save_df_csv(REPAIRS_CSV, st.session_state.df_repairs)
            st.success("Existing alerts updated!")

# -------------------------------------------------------
# MANAGE TRUCKS
# -------------------------------------------------------
elif action == "Manage Trucks":
    st.subheader("Manage Trucks")
    opt = st.selectbox("Action", ["View Trucks","Add Truck","Delete Truck"])
    if opt=="View Trucks":
        st.dataframe(df_trucks,use_container_width=True)
    elif opt=="Add Truck":
        c1,c2 = st.columns(2)
        with c1:
            tnum = st.text_input("Truck #")
            ttype = st.text_input("Truck Type")
        with c2:
            stype = st.selectbox("Service Type", ["SERVICE","FLATBED","AUTO LOADER","TRACTOR","TRAILER","WRECKER"])
        if st.button("Add Truck"):
            if not tnum or not ttype:
                st.error("Truck # and Type required.")
            else:
                new = pd.DataFrame({"Truck #":[tnum],"Truck Type":[ttype],"Service Type":[stype]})
                st.session_state.df_trucks = pd.concat([st.session_state.df_trucks,new],ignore_index=True)
                save_df_csv(TRUCKS_CSV,st.session_state.df_trucks)
                st.success("Truck added!")
    elif opt=="Delete Truck":
        st.dataframe(df_trucks,use_container_width=True)
        idx = st.number_input("Row index to delete",0,len(df_trucks)-1)
        if st.button("Delete"):
            st.session_state.df_trucks = df_trucks.drop(index=idx).reset_index(drop=True)
            save_df_csv(TRUCKS_CSV,st.session_state.df_trucks)
            st.success("Truck deleted!")

# -------------------------------------------------------
# MANAGE ALERTS (master list of Alert Types)
# -------------------------------------------------------
elif action == "Manage Alerts":
    st.subheader("Manage Alert Types")
    opt = st.selectbox("Action", ["View Alerts","Add Alert","Delete Alert"])

    df_alerts = st.session_state.df_alerts

    if opt == "View Alerts":
        st.dataframe(df_alerts, use_container_width=True)

    elif opt == "Add Alert":
        new_alert = st.text_input("New Alert Type")
        if st.button("Add Alert Type"):
            alert_clean = new_alert.strip()
            if not alert_clean:
                st.error("Alert Type cannot be empty.")
            elif alert_clean in df_alerts["Alert Type"].astype(str).tolist():
                st.warning("That alert type already exists.")
            else:
                new_row = pd.DataFrame({"Alert Type":[alert_clean]})
                st.session_state.df_alerts = pd.concat([df_alerts, new_row], ignore_index=True)
                save_df_csv(ALERTS_CSV, st.session_state.df_alerts)
                st.success(f"Added alert type: {alert_clean}")

    elif opt == "Delete Alert":
        if df_alerts.empty:
            st.info("No alert types to delete.")
        else:
            current_alerts = df_alerts["Alert Type"].astype(str).tolist()
            to_delete = st.selectbox("Select Alert Type to delete", current_alerts)
            if st.button("Delete Alert Type", type="primary"):
                st.session_state.df_alerts = df_alerts[df_alerts["Alert Type"] != to_delete].reset_index(drop=True)
                save_df_csv(ALERTS_CSV, st.session_state.df_alerts)
                st.success(f"Deleted alert type: {to_delete}")

# -------------------------------------------------------
# TREND
# -------------------------------------------------------
elif action == "Trend":
    st.subheader("Trend")
    if df_repairs.empty:
        st.info("No repair data yet.")
    else:
        units = sorted(df_repairs["Unit #"].dropna().unique().tolist())
        u = st.selectbox("Unit #", units)
        u_df = df_repairs[df_repairs["Unit #"]==u].copy()
        if u_df.empty:
            st.info("No data for this unit.")
        else:
            u_df["Date_dt"] = pd.to_datetime(u_df["Date"],errors="coerce")
            st.metric("Total Repairs",len(u_df))
            top = u_df["Alert Type/Issue"].value_counts().head(5).reset_index()
            st.dataframe(top,use_container_width=True)
