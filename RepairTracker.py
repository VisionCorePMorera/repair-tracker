import streamlit as st
import pandas as pd
from datetime import datetime, date
from pathlib import Path
import re
import streamlit_authenticator as stauth

# ------------------ App setup ------------------
st.set_page_config(page_title="Repair Tracker", page_icon="🔧", layout="wide")

# ---- Login guard ----
cfg = st.secrets.get("auth")
if not cfg:
    st.error("No [auth] block found in .streamlit/secrets.toml")
    st.stop()

# Validate required keys early
required_cookie_keys = {"name", "key", "expiry_days"}
if "cookie" not in cfg or not required_cookie_keys.issubset(cfg["cookie"].keys()):
    st.error("Missing cookie settings in secrets.toml under [auth.cookie]")
    st.stop()
if "credentials" not in cfg or "usernames" not in cfg["credentials"]:
    st.error("Missing credentials in secrets.toml under [auth.credentials.usernames]")
    st.stop()

try:
    authenticator = stauth.Authenticate(
        cfg["credentials"],
        cfg["cookie"]["name"],
        cfg["cookie"]["key"],
        cfg["cookie"]["expiry_days"],
    )
except Exception as e:
    st.error(f"Authenticator init error: {e}")
    st.stop()

name, auth_status, username = authenticator.login("Login", "main")
if not auth_status:
    st.stop()

authenticator.logout("Logout", "sidebar")
st.caption(f"Signed in as {name}")

st.title("🔧 Repair Tracker")

APP_DIR = Path(__file__).parent
REPAIRS_CSV = APP_DIR / "repairs_data.csv"
TRUCKS_CSV  = APP_DIR / "trucks_data.csv"
ALERTS_CSV  = APP_DIR / "alerts_data.csv"
BACKUPS_DIR = APP_DIR / "Backups"
BACKUPS_DIR.mkdir(exist_ok=True)

# ------------------ Config / defaults ------------------
DEFAULT_ALERT_TYPES = [
    "Oil Change- PM Service","Truck Inspection","Radiator","Electrical","Brakes","Tires",
    "Hydraulic/ PTO","Tool Boxes","Winch Cable","Coolant Hose","Air Hose","Air Bags",
    "Shocks","CARB smog test","Transmission","Steering","Suspension","In-Cab","Misc.","Fuel"
]

def status_chip(s: str) -> str:
    s = (s or "").strip()
    mapping = {"Open": "🟡 Open", "Scheduled": "🔵 Scheduled", "Completed": "🟢 Completed"}
    return mapping.get(s, s)

def calc_table_height(n_rows: int, max_visible: int = 30) -> int:
    """Calculate table height to show all rows up to max_visible without scrolling; scroll beyond that."""
    if n_rows <= max_visible:
        return 40 + n_rows * 28
    else:
        return 40 + max_visible * 28

# ------------------ CSV helpers ------------------
def backup_df_csv(src_path: Path, df: pd.DataFrame):
    """Write a once-per-day snapshot to Backups folder."""
    today = datetime.now().strftime("%Y-%m-%d")
    snap = BACKUPS_DIR / f"{src_path.stem}_{today}.csv"
    if not snap.exists():
        try:
            df.to_csv(snap, index=False)
        except Exception:
            pass  # best-effort

def save_df_csv(path: Path, df: pd.DataFrame) -> None:
    try:
        df.to_csv(path, index=False)
        backup_df_csv(path, df)
    except Exception as e:
        st.warning(f"Couldn’t save {path.name}: {e}")

def load_df_csv(path: Path, default_df: pd.DataFrame) -> pd.DataFrame:
    """
    Load CSV with gentle schema migration:
    - If missing: return default copy.
    - Rename old 'YYMM' -> 'YMM'.
    - Ensure all default columns exist; order consistent.
    """
    try:
        if path.exists():
            df = pd.read_csv(path)
            if "YYMM" in df.columns and "YMM" not in df.columns:
                df.rename(columns={"YYMM": "YMM"}, inplace=True)
            for col in default_df.columns:
                if col not in df.columns:
                    df[col] = "" if default_df[col].dtype == "object" else 0
            df = df[[c for c in default_df.columns if c in df.columns]]
            return df
    except Exception as e:
        st.warning(f"Couldn’t read {path.name}: {e}")
    return default_df.copy()

def load_alerts_csv(path: Path) -> pd.DataFrame:
    """Load/seed alert types as a single-column DataFrame: ['Alert Type/Issue']"""
    try:
        if path.exists():
            df = pd.read_csv(path)
            if "Alert Type/Issue" not in df.columns:
                # try to coerce first column name
                df.columns = ["Alert Type/Issue"] + list(df.columns[1:])
                df = df[["Alert Type/Issue"]]
            df["Alert Type/Issue"] = df["Alert Type/Issue"].astype(str)
            df = df.dropna().drop_duplicates().reset_index(drop=True)
            return df
    except Exception as e:
        st.warning(f"Couldn’t read {path.name}: {e}")
    return pd.DataFrame({"Alert Type/Issue": DEFAULT_ALERT_TYPES})

# ------------------ Seed data ------------------
initial_trucks = {
    "Truck #": ["S1","S2","S3","FB-2","FB-3","FB-4","WL-5","FB-6","FB-7","FB-8","FB-9","FB-10","FB-11",
                "MD-15","16","17","25","26","27","LD1","LD2","LD3","LD4","LD5","18","19","21","23","24"],
    "Truck Type": ["2022 FORD F150- SERVICE TRUCK","2025 FORD F150- SERVICE TRUCK","2025 FORD F150- SERVICE TRUCK",
                   "2023 INTERNATIONAL- FLATBED","2020 FREIGHTLINER- FLATBED","2023 ISUZU NRR- FLATBED",
                   "2017 FORD F-450- WHEEL LIFT","2023 PETERBILT 337- FLATBED","2022 HINO L6- FLATBED",
                   "2024 FREIGHTLINER M2","2021 FREIGHTLINER M2","2023 HINO L6","2024 HINO L6",
                   "2018 INTERNATIONAL FLATBED","2016 KENWORTH T680","2019 INTERNATIONAL LT625",
                   "2016 FREIGHTLINER CASCADIA","2020 WESTERN STAR","2016 INTERNATIONAL LF687",
                   "2021 LANDOLL 440B","2015 TRAILEZE","2017 TRAILEZE","2017 TRAILEZE","2017 TRAILEZE",
                   "2018 PETERBILT 567","2024 PETERBUILT 567","2021 PETERBILT 389","2023 PETERBILT 389","2023 PETERBILT 389"],
    "Service Type": ["SERVICE TRUCKS","SERVICE TRUCKS","SERVICE TRUCKS","FLATBED","FLATBED","FLATBED",
                     "AUTO LOADER","FLATBED","FLATBED","FLATBED","FLATBED","FLATBED","FLATBED",
                     "Landoll Tractors/ Medium","TRACTOR","TRACTOR","TRACTOR","TRACTOR","TRACTOR",
                     "Landoll Tractors/ Medium","TRAILER","TRAILER","TRAILER","TRAILER",
                     "Heavy Wreckers","WRECKER","TRACTOR/ WRECKER","WRECKER","WRECKER"]
}
default_trucks_df = pd.DataFrame(initial_trucks)

# Seed repairs (first run)
seed_map = dict(zip(default_trucks_df["Truck #"], default_trucks_df["Truck Type"]))
today_str = datetime.now().strftime("%m/%d/%Y")
sample_repairs = pd.DataFrame({
    "Ticket ID": [1, 2],
    "Unit #": ["FB-10","FB-11"],
    "YMM": [seed_map.get("FB-10",""), seed_map.get("FB-11","")],
    "Alert Type/Issue": ["PM Service","Water pump"],
    "Description": ["Oil + filters","Replace water pump"],
    "Mileage": [31984, 32046],
    "Date": [today_str, today_str],
    "Scheduled": [today_str, ""],
    "Priority Tier (1/2/3)": ["Tier 3 (PM)","Tier 2 (High)"],
    "Assigned to": ["Rigo",""],
    "Status": ["Scheduled","Open"],
    "Open/Miles at": [today_str, today_str],
    "Downtime (Days)": [0,1],
    "Cost": [0.0,0.0],
    "Completed Date": ["",""],
    "Notes": ["",""]
})

# ------------------ State init ------------------
if "df_trucks" not in st.session_state:
    st.session_state.df_trucks = load_df_csv(TRUCKS_CSV, default_trucks_df)
if "df_alerts" not in st.session_state:
    st.session_state.df_alerts = load_alerts_csv(ALERTS_CSV)
if "df_repairs" not in st.session_state:
    st.session_state.df_repairs = load_df_csv(REPAIRS_CSV, sample_repairs)

df_trucks = st.session_state.df_trucks
df_alerts = st.session_state.df_alerts
df_repairs = st.session_state.df_repairs

# Ensure Ticket ID exists & is int
if "Ticket ID" not in df_repairs.columns:
    df_repairs.insert(0, "Ticket ID", range(1, len(df_repairs) + 1))
df_repairs["Ticket ID"] = pd.to_numeric(df_repairs["Ticket ID"], errors="coerce").fillna(0).astype(int)

# Ensure Completed Date exists
if "Completed Date" not in df_repairs.columns:
    df_repairs["Completed Date"] = ""

# Normalize in state
st.session_state.df_repairs = df_repairs

# Map Unit# -> YMM from live trucks table
truck_to_ymm = dict(zip(df_trucks["Truck #"], df_trucks["Truck Type"]))

# --- state for Unit -> YMM autofill ---
if "selected_unit" not in st.session_state:
    st.session_state.selected_unit = ""
if "ymm_input" not in st.session_state:
    st.session_state.ymm_input = ""

def sync_ymm_from_unit():
    st.session_state.ymm_input = truck_to_ymm.get(st.session_state.selected_unit, "")

def alert_options(include_other=True):
    opts = st.session_state.df_alerts["Alert Type/Issue"].dropna().astype(str).tolist()
    # de-dupe + sort for clean UI
    opts = sorted(list(dict.fromkeys([o.strip() for o in opts if o.strip()])))
    return (opts + ["Other (type below)"]) if include_other else opts

# ------------------ Sidebar ------------------
st.sidebar.title("Actions")
action = st.sidebar.selectbox(
    "Choose Action",
    ["View Repairs", "Add Repair", "Edit/Delete", "Manage Trucks", "Manage Alert Types", "Trend"]
)

# ------------------ View Repairs (chip layout + filters + taller table) ------------------
if action == "View Repairs":
    with st.expander("Filters", expanded=True):
        colf1, colf2, colf3 = st.columns(3)
        with colf1:
            sel_status = st.multiselect("Status", sorted(df_repairs["Status"].dropna().unique().tolist()))
            sel_assigned = st.multiselect("Assigned To", sorted([x for x in df_repairs["Assigned to"].dropna().unique().tolist() if str(x).strip()]))
        with colf2:
            sel_priority = st.multiselect("Priority", sorted(df_repairs["Priority Tier (1/2/3)"].dropna().unique().tolist()))
            sel_unit = st.multiselect("Unit #", sorted(df_repairs["Unit #"].dropna().unique().tolist()))
        with colf3:
            sel_ymm = st.multiselect("YMM", sorted([x for x in df_repairs["YMM"].dropna().unique().tolist() if str(x).strip()]))
            q = st.text_input("Search text (Desc / Notes / Issue)").strip()

    view_df = df_repairs.copy()
    if sel_status:   view_df = view_df[view_df["Status"].isin(sel_status)]
    if sel_assigned: view_df = view_df[view_df["Assigned to"].isin(sel_assigned)]
    if sel_priority: view_df = view_df[view_df["Priority Tier (1/2/3)"].isin(sel_priority)]
    if sel_unit:     view_df = view_df[view_df["Unit #"].isin(sel_unit)]
    if sel_ymm:      view_df = view_df[view_df["YMM"].isin(sel_ymm)]
    if q:
        patt = re.compile(re.escape(q), re.IGNORECASE)
        mask = (
            view_df["Description"].fillna("").str.contains(patt) |
            view_df["Notes"].fillna("").str.contains(patt) |
            view_df["Alert Type/Issue"].fillna("").str.contains(patt)
        )
        view_df = view_df[mask]

    display_df = view_df.copy()
    display_df.insert(1, "Status ⬤", display_df["Status"].map(status_chip).fillna(""))

    st.dataframe(
        display_df,
        use_container_width=True,
        height=calc_table_height(len(display_df), max_visible=30)
    )

    total_repairs = len(view_df)
    total_downtime = pd.to_numeric(view_df["Downtime (Days)"], errors="coerce").fillna(0).sum()
    total_cost = pd.to_numeric(view_df["Cost"], errors="coerce").fillna(0.0).sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Filtered Repairs", int(total_repairs))
    c2.metric("Total Downtime (Days)", int(total_repairs and total_downtime or 0))
    c3.metric("Total Cost", f"{float(total_cost):,.2f}")

# ------------------ Add Repair (Unit -> YMM autofill) ------------------
elif action == "Add Repair":
    st.subheader("New Repair")

    st.selectbox(
        "Unit #",
        [""] + df_trucks["Truck #"].tolist(),
        key="selected_unit",
        on_change=sync_ymm_from_unit,
    )

    with st.form("add_repair"):
        col1, col2 = st.columns(2)
        with col1:
            ymm = st.text_input("YMM (auto from Unit #; editable)", key="ymm_input")
            alert_pick = st.selectbox("Alert Type/Issue (pick)", alert_options(), index=0 if alert_options() else None)
            alert_type_other = ""
            if alert_pick == "Other (type below)":
                alert_type_other = st.text_input("Specify Alert Type/Issue")
            description = st.text_area("Description")
            mileage = st.number_input("Mileage", min_value=0, step=1)
        with col2:
            date_val = st.date_input("Date", value=date.today())
            sched_val = st.date_input("Scheduled", value=date.today())
            priority = st.selectbox("Priority Tier", [
                "Tier 1 (Critical)", "Tier 2 (High)", "Tier 3 (PM)", "Tier 4 (Non-Critical)"
            ])
            assigned_to = st.text_input("Assigned to")
            status = st.selectbox("Status", ["Open", "Scheduled", "Completed"])
            downtime = st.number_input("Downtime (Days)", min_value=0, step=1)
            cost = st.number_input("Cost", min_value=0.0, step=1.0)

        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Repair")

        if submitted:
            unit = st.session_state.selected_unit
            if not unit or not description:
                st.error("Unit # and Description are required.")
            else:
                next_id = (st.session_state.df_repairs["Ticket ID"].max() + 1) if not st.session_state.df_repairs.empty else 1
                alert_final = alert_type_other.strip() if alert_pick == "Other (type below)" else alert_pick
                completed_date = date_val.strftime('%m/%d/%Y') if status == "Completed" else ""
                new_row = {
                    'Ticket ID': int(next_id),
                    'Unit #': unit,
                    'YMM': st.session_state.ymm_input.strip(),
                    'Alert Type/Issue': alert_final,
                    'Description': description,
                    'Mileage': int(mileage),
                    'Date': date_val.strftime('%m/%d/%Y'),
                    'Scheduled': sched_val.strftime('%m/%d/%Y'),
                    'Priority Tier (1/2/3)': priority,
                    'Assigned to': assigned_to,
                    'Status': status,
                    'Open/Miles at': date_val.strftime('%m/%d/%Y'),
                    'Downtime (Days)': int(downtime),
                    'Cost': float(cost),
                    'Completed Date': completed_date,
                    'Notes': notes
                }
                st.session_state.df_repairs = pd.concat(
                    [st.session_state.df_repairs, pd.DataFrame([new_row])],
                    ignore_index=True
                )
                save_df_csv(REPAIRS_CSV, st.session_state.df_repairs)
                st.success(f"Repair added (Ticket {next_id})!")

# ------------------ Edit/Delete Repairs (bulk-select + bulk actions) ------------------
elif action == "Edit/Delete":
    if st.session_state.df_repairs.empty:
        st.info("No data to edit.")
    else:
        st.subheader("Edit / Delete (Bulk)")

        # Build editor view with a Select checkbox and stable RowID
        editor_df = st.session_state.df_repairs.reset_index().rename(columns={"index": "RowID"}).copy()
        editor_df.insert(1, "Select", False)
        editor_df["Scheduled"] = pd.to_datetime(editor_df["Scheduled"], errors="coerce", format="%m/%d/%Y")

        # Display editable grid
        alerts_opts = alert_options(include_other=False)  # in-grid: just the managed list
        edited = st.data_editor(
            editor_df,
            use_container_width=True,
            hide_index=True,
            height=calc_table_height(len(editor_df), max_visible=30),
            column_config={
                "Select": st.column_config.CheckboxColumn("Select"),
                "RowID": st.column_config.NumberColumn("RowID", help="Internal index", disabled=True),
                "Scheduled": st.column_config.DateColumn("Scheduled", format="MM/DD/YYYY"),
                "Priority Tier (1/2/3)": st.column_config.SelectboxColumn(
                    "Priority Tier (1/2/3)",
                    options=["Tier 1 (Critical)", "Tier 2 (High)", "Tier 3 (PM)", "Tier 4 (Non-Critical)"]
                ),
                "Assigned to": st.column_config.TextColumn("Assigned to"),
                "Status": st.column_config.SelectboxColumn(
                    "Status",
                    options=["Open", "Scheduled", "Completed"]
                ),
                # Use managed options in the grid
                "Alert Type/Issue": st.column_config.SelectboxColumn("Alert Type/Issue", options=alerts_opts),
                "Downtime (Days)": st.column_config.NumberColumn("Downtime (Days)", min_value=0, step=1),
                "Cost": st.column_config.NumberColumn("Cost", min_value=0.0, step=1.0, format="$%.2f")
            }
        )

        selected_ids = edited.loc[edited["Select"] == True, "RowID"].tolist()
        st.caption(f"Selected rows: {len(selected_ids)}")

        # Bulk controls
        b1, b2, b3 = st.columns([1,1,2])
        with b1:
            new_status = st.selectbox("Bulk Status", ["(no change)","Open","Scheduled","Completed"])
        with b2:
            bulk_alert_choice = st.selectbox("Bulk Alert Type", ["(no change)"] + alert_options())
        with b3:
            notes_text = st.text_input("Bulk Notes (append/replace)")

        bulk_alert_other = ""
        if bulk_alert_choice == "Other (type below)":
            bulk_alert_other = st.text_input("Specify Bulk Alert Type")

        append_notes = st.checkbox("Append to Notes", value=True)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Apply Update to Selected"):
                if not selected_ids:
                    st.warning("Select one or more rows first.")
                else:
                    for rid in selected_ids:
                        scheduled_date = edited.loc[edited["RowID"] == rid, "Scheduled"].iloc[0]
                        st.session_state.df_repairs.at[rid, "Scheduled"] = scheduled_date.strftime('%m/%d/%Y') if pd.notnull(scheduled_date) else ""
                        st.session_state.df_repairs.at[rid, "Priority Tier (1/2/3)"] = edited.loc[edited["RowID"] == rid, "Priority Tier (1/2/3)"].iloc[0]
                        st.session_state.df_repairs.at[rid, "Assigned to"] = edited.loc[edited["RowID"] == rid, "Assigned to"].iloc[0]
                        st.session_state.df_repairs.at[rid, "Status"] = edited.loc[edited["RowID"] == rid, "Status"].iloc[0]
                        st.session_state.df_repairs.at[rid, "Downtime (Days)"] = edited.loc[edited["RowID"] == rid, "Downtime (Days)"].iloc[0]
                        st.session_state.df_repairs.at[rid, "Cost"] = edited.loc[edited["RowID"] == rid, "Cost"].iloc[0]
                        # Per-row Alert Type from grid
                        st.session_state.df_repairs.at[rid, "Alert Type/Issue"] = edited.loc[edited["RowID"] == rid, "Alert Type/Issue"].iloc[0]
                        # Bulk Status override
                        if new_status != "(no change)":
                            st.session_state.df_repairs.at[rid, "Status"] = new_status
                        # Completed date logic
                        if st.session_state.df_repairs.at[rid, "Status"] == "Completed" and not str(st.session_state.df_repairs.at[rid, "Completed Date"]).strip():
                            st.session_state.df_repairs.at[rid, "Completed Date"] = date.today().strftime('%m/%d/%Y')
                        elif st.session_state.df_repairs.at[rid, "Status"] != "Completed":
                            st.session_state.df_repairs.at[rid, "Completed Date"] = ""
                        # Bulk Alert override
                        if bulk_alert_choice != "(no change)":
                            st.session_state.df_repairs.at[rid, "Alert Type/Issue"] = (
                                bulk_alert_other.strip() if bulk_alert_choice == "Other (type below)" else bulk_alert_choice
                            )
                        # Bulk notes
                        if notes_text.strip():
                            if append_notes:
                                existing = str(st.session_state.df_repairs.at[rid, "Notes"]).strip()
                                st.session_state.df_repairs.at[rid, "Notes"] = (existing + (" | " if existing else "") + notes_text.strip())
                            else:
                                st.session_state.df_repairs.at[rid, "Notes"] = notes_text.strip()
                    save_df_csv(REPAIRS_CSV, st.session_state.df_repairs)
                    st.success(f"Updated {len(selected_ids)} row(s).")
        with c2:
            if st.button("Delete Selected", type="primary"):
                if not selected_ids:
                    st.warning("Select one or more rows first.")
                else:
                    st.session_state.df_repairs = st.session_state.df_repairs.drop(index=selected_ids).reset_index(drop=True)
                    save_df_csv(REPAIRS_CSV, st.session_state.df_repairs)
                    st.success(f"Deleted {len(selected_ids)} row(s).")

# ------------------ Manage Trucks ------------------
elif action == "Manage Trucks":
    st.subheader("Manage Trucks")
    action_truck = st.selectbox("Choose Action", ["View Trucks", "Add Truck", "Delete Truck"])
    if action_truck == "View Trucks":
        st.dataframe(df_trucks, use_container_width=True)
    elif action_truck == "Add Truck":
        with st.form("add_truck"):
            col1, col2 = st.columns(2)
            with col1:
                truck_num = st.text_input("Truck #")
                truck_type = st.text_input("YMM (Year Make Model / Type)")
            with col2:
                service_type = st.selectbox("Service Type", [
                    "SERVICE TRUCKS","FLATBED","AUTO LOADER","TRACTOR","TRAILER","WRECKER",
                    "Landoll Tractors/ Medium","Landoll Trailers","Heavy Wreckers","TRACTOR/ WRECKER"
                ])
            submitted = st.form_submit_button("Add Truck")
            if submitted:
                if not truck_num or not truck_type:
                    st.error("Truck # and YMM are required.")
                else:
                    new_row = pd.DataFrame({
                        "Truck #": [truck_num],
                        "Truck Type": [truck_type],
                        "Service Type": [service_type]
                    })
                    st.session_state.df_trucks = pd.concat([st.session_state.df_trucks, new_row], ignore_index=True)
                    save_df_csv(TRUCKS_CSV, st.session_state.df_trucks)
                    st.success("Truck added!")
    elif action_truck == "Delete Truck":
        if not df_trucks.empty:
            row_index = st.number_input(
                "Select Row Index to Delete",
                min_value=0, max_value=len(df_trucks)-1, value=0, key="truck_del_idx"
            )
            st.dataframe(df_trucks.iloc[[row_index]], use_container_width=True)
            if st.button("Delete Truck", type="primary", key="btn_delete_truck"):
                st.session_state.df_trucks = df_trucks.drop(index=row_index).reset_index(drop=True)
                save_df_csv(TRUCKS_CSV, st.session_state.df_trucks)
                st.success("Truck deleted!")
        else:
            st.info("No trucks to delete.")

# ------------------ Manage Alert Types ------------------
elif action == "Manage Alert Types":
    st.subheader("Manage Alert Types")
    action_alert = st.selectbox("Choose Action", ["View Alert Types", "Add Alert Type", "Delete Alert Type"])

    if action_alert == "View Alert Types":
        st.dataframe(st.session_state.df_alerts, use_container_width=True, height=calc_table_height(len(st.session_state.df_alerts), 30))

    elif action_alert == "Add Alert Type":
        with st.form("add_alert_type"):
            new_alert = st.text_input("Alert Type/Issue (e.g., 'Brakes')")
            submitted = st.form_submit_button("Add Alert Type")
            if submitted:
                val = (new_alert or "").strip()
                if not val:
                    st.error("Alert Type/Issue is required.")
                else:
                    cur = st.session_state.df_alerts["Alert Type/Issue"].astype(str).str.strip().tolist()
                    if val in cur:
                        st.warning("That alert type already exists.")
                    else:
                        st.session_state.df_alerts = pd.concat(
                            [st.session_state.df_alerts, pd.DataFrame({"Alert Type/Issue": [val]})],
                            ignore_index=True
                        ).drop_duplicates().reset_index(drop=True)
                        save_df_csv(ALERTS_CSV, st.session_state.df_alerts)
                        st.success("Alert type added!")

    elif action_alert == "Delete Alert Type":
        if st.session_state.df_alerts.empty:
            st.info("No alert types to delete.")
        else:
            idx = st.number_input("Select Row Index to Delete", min_value=0, max_value=len(st.session_state.df_alerts)-1, value=0, key="alert_del_idx")
            st.dataframe(st.session_state.df_alerts.iloc[[idx]], use_container_width=True)
            if st.button("Delete Alert Type", type="primary", key="btn_delete_alert"):
                st.session_state.df_alerts = st.session_state.df_alerts.drop(index=idx).reset_index(drop=True)
                save_df_csv(ALERTS_CSV, st.session_state.df_alerts)
                st.success("Alert type deleted!")

# ------------------ Trend (per-truck insights) ------------------
elif action == "Trend":
    st.subheader("Trend Analysis")
    if df_repairs.empty:
        st.info("No repair data yet.")
    else:
        units_available = sorted(df_repairs["Unit #"].dropna().unique().tolist())
        sel_unit = st.selectbox("Select Unit #", units_available, index=0 if units_available else None)
        unit_df = df_repairs[df_repairs["Unit #"] == sel_unit].copy()
        if unit_df.empty:
            st.info("No records for this unit.")
        else:
            unit_df["Date_dt"] = pd.to_datetime(unit_df["Date"], errors="coerce")
            unit_df["Completed_dt"] = pd.to_datetime(unit_df["Completed Date"], errors="coerce")
            ymm_value = str(unit_df["YMM"].dropna().iloc[0]) if not unit_df["YMM"].dropna().empty else ""
            year_match = re.search(r"\b(20\d{2}|19\d{2})\b", ymm_value)
            ymm_year = int(year_match.group(0)) if year_match else None
            current_year = datetime.now().year
            truck_age = (current_year - ymm_year) if ymm_year else None
            last_90 = datetime.now() - pd.Timedelta(days=90)
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Total Repairs", len(unit_df))
            k2.metric("Repairs (Last 90d)", int((unit_df["Date_dt"] >= last_90).sum()))
            k3.metric("Total Cost", f"{pd.to_numeric(unit_df['Cost'], errors='coerce').fillna(0).sum():,.2f}")
            k4.metric("Downtime (Days)", int(pd.to_numeric(unit_df["Downtime (Days)"], errors="coerce").fillna(0).sum()))
            k5.metric("YMM Year / Age", f"{ymm_year or '—'} / {truck_age if truck_age is not None else '—'}")
            colA, colB = st.columns(2)
            with colA:
                st.caption("Top Issues (Alert Type/Issue)")
                top_issues = (unit_df["Alert Type/Issue"].fillna("Unknown").value_counts().reset_index())
                top_issues.columns = ["Alert Type/Issue", "Count"]
                st.dataframe(top_issues, use_container_width=True, height=240)
            with colB:
                st.caption("Assignments Breakdown")
                assn = (unit_df["Assigned to"].fillna("Unassigned").replace("", "Unassigned").value_counts().reset_index())
                assn.columns = ["Assigned to", "Count"]
                st.dataframe(assn, use_container_width=True, height=240)
            monthly = unit_df.copy()
            monthly["YearMonth"] = monthly["Date_dt"].dt.to_period("M").astype(str)
            monthly_cost = (pd.to_numeric(monthly["Cost"], errors="coerce").fillna(0)
                            .groupby(monthly["YearMonth"]).sum().reset_index())
            monthly_down = (pd.to_numeric(monthly["Downtime (Days)"], errors="coerce").fillna(0)
                            .groupby(monthly["YearMonth"]).sum().reset_index())
            cA, cB = st.columns(2)
            with cA:
                st.caption("Monthly Cost")
                if not monthly_cost.empty:
                    st.line_chart(monthly_cost.set_index("YearMonth"))
                else:
                    st.write("—")
            with cB:
                st.caption("Monthly Downtime (Days)")
                if not monthly_down.empty:
                    st.line_chart(monthly_down.set_index("YearMonth"))
                else:
                    st.write("—")
            st.caption("Most Recent 10 Entries")
            recent = unit_df.sort_values("Date_dt", ascending=False).head(10)
            recent_display = recent[[
                "Ticket ID","Date","Status","YMM","Alert Type/Issue","Description",
                "Assigned to","Downtime (Days)","Cost","Completed Date","Notes"
            ]]
            recent_display.insert(2, "Status ⬤", recent_display["Status"].map(status_chip).fillna(""))
            st.dataframe(recent_display, use_container_width=True, height=calc_table_height(len(recent_display), 10))

# ------------------ Export ------------------
st.sidebar.markdown("---")
st.sidebar.download_button(
    "Download Repairs CSV",
    data=st.session_state.df_repairs.to_csv(index=False).encode("utf-8"),
    file_name="repairs_tracker.csv",
    mime="text/csv",
)
st.sidebar.download_button(
    "Download Trucks CSV",
    data=st.session_state.df_trucks.to_csv(index=False).encode("utf-8"),
    file_name="trucks.csv",
    mime="text/csv",
)
st.sidebar.download_button(
    "Download Alert Types CSV",
    data=st.session_state.df_alerts.to_csv(index=False).encode("utf-8"),
    file_name="alerts.csv",
    mime="text/csv",
)



