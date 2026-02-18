"""
Streamlit entry point — Store Visit Analyzer UI (Tool A: Data Consolidation).

Wires together the full processing pipeline with a 6-step user flow:
  1. Sidebar settings (exchange rate)
  2. File upload (raw Excel files)
  3. Per-file metadata form (Country, City, Retailer, Store Name, Format)
  4. Per-file processing with progress bar
  5. Merge + overlap resolution dialog
  6. Results display (summary metrics, data preview, quality report)
  7. Download formatted Excel

Contains NO business logic — only calls processing modules and displays results.

See docs/PRD.md Section 4 for the UI mockup and user flow.
"""

import logging
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from config.filename_config import COUNTRIES, COUNTRY_RETAILERS, STORE_FORMATS
from processing.file_reader import read_excel_file
from processing.filename_parser import parse_filename
from processing.column_mapper import map_columns
from processing.normalizer import normalize, FlaggedItem
from processing.numeric_converter import convert_numerics
from processing.price_calculator import calculate_prices, COUNTRY_CURRENCY_MAP
from processing.llm_cleaner import clean_with_llm
from processing.merger import merge_dataframes, apply_overlap_decisions
from processing.quality_checker import check_quality
from utils.excel_formatter import format_and_save

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Page configuration
# ═══════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Store Visit Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ═══════════════════════════════════════════════════════════════════════════
# Password protection (runs FIRST, before any content)
# ═══════════════════════════════════════════════════════════════════════════

def check_password() -> bool:
    """
    Password protection gate.
    
    Returns True if user is authenticated or if no password is set (local dev).
    Returns False and shows login form if authentication is required but not completed.
    
    This function MUST be called at the very top of the app to protect all content.
    """
    # Get password from secrets (None if not set = local dev mode, no protection)
    correct_password = st.secrets.get("APP_PASSWORD", None)
    
    # If no password is configured, skip protection (local development)
    if correct_password is None:
        return True
    
    # Check if user is already authenticated
    if st.session_state.get("authenticated", False):
        return True
    
    # Show login form
    st.title("🔒 Store Visit Analyzer")
    st.markdown("### Please enter the password to access the application")
    
    # Create a form for better UX
    with st.form("login_form"):
        password_input = st.text_input(
            "Password",
            type="password",
            placeholder="Enter password",
            help="Contact your administrator if you don't have the password"
        )
        submit_button = st.form_submit_button("Login", use_container_width=True)
    
    # Check password when form is submitted
    if submit_button:
        if password_input == correct_password:
            st.session_state.authenticated = True
            st.success("✅ Authentication successful! Loading application...")
            st.rerun()
        else:
            st.error("❌ Incorrect password. Please try again.")
            return False
    
    # If we reach here, user hasn't logged in yet
    st.info("👆 Enter the password above to continue")
    return False


# ═══════════════════════════════════════════════════════════════════════════
# AUTHENTICATION GATE - Must pass before any content loads
# ═══════════════════════════════════════════════════════════════════════════

if not check_password():
    st.stop()  # Prevent any content from loading


# ═══════════════════════════════════════════════════════════════════════════
# Exchange rate helper
# ═══════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def _fetch_exchange_rate(base: str = "GBP", target: str = "EUR") -> float:
    """
    Fetch the live exchange rate from the Frankfurter API (ECB data).

    Falls back to 1.17 if the request fails for any reason.

    Args:
        base: Source currency code (e.g. "GBP").
        target: Target currency code (e.g. "EUR").

    Returns:
        Exchange rate as a float.
    """
    try:
        response = requests.get(
            "https://api.frankfurter.app/latest",
            params={"from": base, "to": target},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()["rates"][target]
    except Exception:
        return 1.17


# ═══════════════════════════════════════════════════════════════════════════
# Session state initialisation
# ═══════════════════════════════════════════════════════════════════════════

def _init_session_state() -> None:
    """Ensure all required session state keys exist with sensible defaults."""
    defaults: dict = {
        "metadata_confirmed": False,
        "processing_complete": False,
        "file_metadata": [],
        "processed_dataframes": [],
        "all_flagged_items": [],
        "all_changes_log": [],
        "all_errors": [],
        "merge_result": None,
        "overlap_decisions": {},
        "overlap_decisions_applied": False,
        "final_dataframe": None,
        "quality_report": None,
        "source_files_info": [],
        "llm_resolved_count": 0,
        "llm_skipped": False,
        "llm_failed_batches": 0,
        "llm_total_batches": 0,
        "total_llm_cost": 0.0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_session_state()


# ═══════════════════════════════════════════════════════════════════════════
# Sidebar — Settings
# ═══════════════════════════════════════════════════════════════════════════

st.sidebar.title("⚙️ Settings")

# API key from Streamlit secrets (not from a UI input field)
api_key = st.secrets.get("ANTHROPIC_API_KEY", None)
if api_key == "your-key-here":
    api_key = None

st.sidebar.divider()

# Exchange rate: GBP → EUR (the only non-trivial conversion).
# EUR-country files use rate 1.0 automatically during processing.
default_gbp_rate = _fetch_exchange_rate(base="GBP", target="EUR")

exchange_rate_gbp_eur = st.sidebar.number_input(
    "Exchange Rate GBP → EUR",
    min_value=0.01,
    max_value=100.0,
    value=default_gbp_rate,
    step=0.01,
    format="%.4f",
    help="Rate fetched from ECB. Edit to override.",
)

st.sidebar.divider()
if not api_key:
    st.sidebar.info(
        "No API key configured. The tool will still process files — "
        "ambiguous items will be flagged instead of LLM-resolved. "
        "Set ANTHROPIC_API_KEY in .streamlit/secrets.toml to enable LLM cleaning."
    )

st.sidebar.divider()
show_dev_tools = st.sidebar.checkbox(
    "🛠️ Developer Tools",
    value=False,
    help="Show accuracy testing tools for comparing against ground truth"
)


# ═══════════════════════════════════════════════════════════════════════════
# Main area — Title
# ═══════════════════════════════════════════════════════════════════════════

st.title("📊 Store Visit Analyzer")
st.caption("Data Consolidation & Cleaning Tool — upload raw shelf analysis Excel files to produce a clean, consolidated master dataset.")


# ═══════════════════════════════════════════════════════════════════════════
# Section 1: File Upload
# ═══════════════════════════════════════════════════════════════════════════

st.header("📁 Upload Files")

raw_files = st.file_uploader(
    "Raw Excel files",
    type=["xlsx"],
    accept_multiple_files=True,
    help="Drag and drop one or more raw store visit Excel files.",
)

# Reset downstream state when the uploaded files change
if raw_files != st.session_state.get("_prev_raw_files"):
    st.session_state["_prev_raw_files"] = raw_files
    st.session_state["metadata_confirmed"] = False
    st.session_state["processing_complete"] = False
    st.session_state["overlap_decisions_applied"] = False
    st.session_state["final_dataframe"] = None


# ═══════════════════════════════════════════════════════════════════════════
# Section 2: Per-File Metadata Form
# ═══════════════════════════════════════════════════════════════════════════

if raw_files:
    st.divider()
    st.header("📋 Step 1: Confirm File Metadata")
    st.caption(
        "Review the auto-parsed metadata below. "
        "Edit any incorrect values before processing."
    )

    # Parse filenames once for auto-fill defaults
    parsed_results: list[dict] = []
    for uploaded_file in raw_files:
        parse_result = parse_filename(uploaded_file.name)
        parsed_results.append({
            "filename": uploaded_file.name,
            "retailer": parse_result.retailer or "",
            "city": parse_result.city or "",
            "store_format": parse_result.store_format or "",
            "confidence": parse_result.confidence,
        })

    # Column headers
    hdr_cols = st.columns([2, 1, 1, 1.5, 1.5, 1])
    hdr_cols[0].markdown("**File**")
    hdr_cols[1].markdown("**Country**")
    hdr_cols[2].markdown("**City**")
    hdr_cols[3].markdown("**Retailer**")
    hdr_cols[4].markdown("**Store Name**")
    hdr_cols[5].markdown("**Store Format**")

    low_confidence_count = 0

    for idx, parsed in enumerate(parsed_results):
        row_cols = st.columns([2, 1, 1, 1.5, 1.5, 1])

        # ── Filename (read-only) ─────────────────────────────────
        row_cols[0].text(parsed["filename"])
        if parsed["confidence"] < 80:
            low_confidence_count += 1

        # ── Country dropdown ─────────────────────────────────────
        default_country_idx = 0  # "United Kingdom"
        file_country = row_cols[1].selectbox(
            "Country",
            options=COUNTRIES,
            index=default_country_idx,
            key=f"meta_{idx}_country",
            label_visibility="collapsed",
        )

        # ── City (free text, auto-filled from parser) ────────────
        file_city = row_cols[2].text_input(
            "City",
            value=parsed["city"],
            key=f"meta_{idx}_city",
            label_visibility="collapsed",
        )

        # ── Retailer dropdown (country-dependent) ────────────────
        retailer_options = COUNTRY_RETAILERS.get(file_country, [])

        # Try to match the auto-parsed retailer to a dropdown option
        parsed_retailer = parsed["retailer"]
        default_retailer_idx = 0
        if parsed_retailer:
            try:
                default_retailer_idx = retailer_options.index(parsed_retailer)
            except ValueError:
                default_retailer_idx = 0

        file_retailer = row_cols[3].selectbox(
            "Retailer",
            options=retailer_options,
            index=default_retailer_idx,
            key=f"meta_{idx}_retailer",
            label_visibility="collapsed",
        )

        # If "Other" selected, show custom retailer text input
        if file_retailer == "Other":
            file_retailer = st.text_input(
                "Custom Retailer Name",
                value="",
                key=f"meta_{idx}_retailer_custom",
            )

        # ── Store Name (free text, auto-filled) ──────────────────
        default_store_name = (
            f"{file_retailer} {file_city}"
            if file_retailer and file_city
            else ""
        )
        file_store_name = row_cols[4].text_input(
            "Store Name",
            value=default_store_name,
            key=f"meta_{idx}_store_name",
            label_visibility="collapsed",
        )

        # ── Store Format dropdown ────────────────────────────────
        format_options = [""] + STORE_FORMATS
        file_store_format = row_cols[5].selectbox(
            "Store Format",
            options=format_options,
            index=0,
            key=f"meta_{idx}_format",
            label_visibility="collapsed",
        )

        # If "Other" selected, show custom format text input
        if file_store_format == "Other":
            file_store_format = st.text_input(
                "Custom Store Format",
                value="",
                key=f"meta_{idx}_format_custom",
            )

    # Warn about low-confidence parses
    if low_confidence_count > 0:
        st.warning(
            f"{low_confidence_count} file(s) have low parsing confidence. "
            "Please verify all fields carefully."
        )

    # Confirm & Process button
    if st.button("Confirm & Process ▶", type="primary", use_container_width=True):
        # Collect metadata from session state widgets
        collected_metadata: list[dict] = []
        missing_retailer = 0
        missing_city = 0

        for idx, parsed in enumerate(parsed_results):
            meta_country = st.session_state.get(f"meta_{idx}_country", "United Kingdom")
            meta_city = st.session_state.get(f"meta_{idx}_city", "")
            meta_retailer = st.session_state.get(f"meta_{idx}_retailer", "")
            meta_store_name = st.session_state.get(f"meta_{idx}_store_name", "")
            meta_format = st.session_state.get(f"meta_{idx}_format", "")

            # Resolve "Other" custom values
            if meta_retailer == "Other":
                meta_retailer = st.session_state.get(f"meta_{idx}_retailer_custom", "")
            if meta_format == "Other":
                meta_format = st.session_state.get(f"meta_{idx}_format_custom", "")

            if not meta_retailer:
                missing_retailer += 1
            if not meta_city:
                missing_city += 1

            collected_metadata.append({
                "File": parsed["filename"],
                "Country": meta_country,
                "City": meta_city,
                "Retailer": meta_retailer,
                "Store Name": meta_store_name,
                "Store Format": meta_format,
            })

        if missing_retailer > 0 or missing_city > 0:
            st.error(
                "Retailer and City are required for all files. "
                f"Missing: {missing_retailer} retailer(s), {missing_city} city/cities."
            )
        else:
            st.session_state["file_metadata"] = collected_metadata
            st.session_state["metadata_confirmed"] = True
            st.session_state["processing_complete"] = False
            st.session_state["overlap_decisions_applied"] = False
            st.session_state["final_dataframe"] = None
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# Section 3: Processing Pipeline
# ═══════════════════════════════════════════════════════════════════════════

if (
    raw_files
    and st.session_state["metadata_confirmed"]
    and not st.session_state["processing_complete"]
):
    st.divider()
    st.header("⚙️ Processing")

    file_metadata = st.session_state["file_metadata"]
    total_files = len(raw_files)

    progress_bar = st.progress(0, text="Starting pipeline...")
    status_container = st.empty()

    processed_dataframes: list[pd.DataFrame] = []
    source_filenames: list[str] = []
    all_flagged_items: list[FlaggedItem] = []
    all_changes_log: list[dict] = []
    all_errors: list[str] = []
    source_files_info: list[dict] = []
    llm_resolved_count = 0
    llm_skipped = False

    # Write uploaded files to a temp directory so file_reader can use Paths
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)

        for file_idx, (uploaded_file, meta) in enumerate(
            zip(raw_files, file_metadata)
        ):
            filename = meta["File"]
            progress_fraction = (file_idx + 1) / total_files
            progress_bar.progress(
                progress_fraction,
                text=f"Processing {filename} ({file_idx + 1}/{total_files})...",
            )

            try:
                # Save uploaded file to temp directory
                file_path = temp_dir_path / filename
                file_path.write_bytes(uploaded_file.getvalue())

                # ── Step 1: Read Excel file ───────────────────────
                with status_container.container():
                    st.text(f"Reading {filename}...")
                read_result = read_excel_file(file_path)

                if read_result.errors:
                    for error in read_result.errors:
                        all_errors.append(f"{filename}: {error}")
                    if read_result.raw_dataframe.empty:
                        st.warning(f"Skipping {filename} — could not read data.")
                        continue

                dataframe = read_result.raw_dataframe

                # ── Step 2: Map columns to master schema ──────────
                with status_container.container():
                    st.text(f"Mapping columns for {filename}...")
                mapping_result = map_columns(dataframe.columns.tolist())
                rename_map = {
                    raw: master
                    for raw, master in mapping_result.mapping.items()
                    if master is not None
                }
                dataframe = dataframe.rename(columns=rename_map)

                # Drop internal columns that start with "_"
                internal_cols = [c for c in dataframe.columns if c.startswith("_")]
                dataframe = dataframe.drop(columns=internal_cols, errors="ignore")

                # ── Step 3: Inject per-file metadata ────────────────
                file_country = meta["Country"]
                file_currency = COUNTRY_CURRENCY_MAP.get(file_country, "EUR")

                dataframe["Retailer"] = meta["Retailer"]
                dataframe["City"] = meta["City"]
                dataframe["Country"] = file_country
                dataframe["Store Name"] = meta.get("Store Name") or None
                dataframe["Store Format"] = meta.get("Store Format") or None

                if "Product Name" not in dataframe.columns:
                    dataframe["Product Name"] = None
                if "Flavor" not in dataframe.columns:
                    dataframe["Flavor"] = None
                if "Juice Extraction Method" not in dataframe.columns:
                    dataframe["Juice Extraction Method"] = None

                # ── Step 4: Normalize categorical values ──────────
                with status_container.container():
                    st.text(f"Normalizing {filename}...")
                norm_result = normalize(dataframe)
                dataframe = norm_result.dataframe
                all_flagged_items.extend(norm_result.flagged_items)
                all_changes_log.extend(norm_result.changes_log)

                # ── Step 5: Convert numeric columns ───────────────
                with status_container.container():
                    st.text(f"Converting numerics for {filename}...")
                numeric_result = convert_numerics(dataframe)
                dataframe = numeric_result.dataframe
                for err in numeric_result.errors:
                    all_errors.append(
                        f"{filename} row {err['row']}: {err['column']} — {err['error']}"
                    )

                # ── Step 6: Calculate prices ──────────────────────
                with status_container.container():
                    st.text(f"Calculating prices for {filename}...")

                # Build the exchange rates dict for this file's currency
                file_exchange_rates = {"EUR": 1.0, "GBP": exchange_rate_gbp_eur}
                price_result = calculate_prices(
                    dataframe,
                    exchange_rates=file_exchange_rates,
                    country=file_country,
                )
                dataframe = price_result.dataframe
                for err in price_result.errors:
                    all_errors.append(
                        f"{filename} row {err['row']}: {err['column']} — {err['error']}"
                    )

                # ── Step 7: LLM cleaning (optional) ──────────────
                file_flagged = [
                    item for item in norm_result.flagged_items
                ]
                if file_flagged and api_key:
                    with status_container.container():
                        st.text(f"Running LLM cleaning for {filename}...")
                    with st.spinner(f"Calling Claude API for {filename}..."):
                        llm_result = clean_with_llm(
                            dataframe, file_flagged, api_key
                        )
                    dataframe = llm_result.dataframe
                    llm_resolved_count += len(llm_result.resolved_items)
                    llm_skipped = llm_result.skipped
                    
                    # Accumulate token usage, cost, and batch stats
                    st.session_state["total_llm_cost"] += llm_result.api_cost_estimate
                    st.session_state["total_input_tokens"] += llm_result.input_tokens
                    st.session_state["total_output_tokens"] += llm_result.output_tokens
                    st.session_state["llm_failed_batches"] += llm_result.failed_batches
                    st.session_state["llm_total_batches"] += llm_result.total_batches

                    # Remove resolved items from the flagged list
                    resolved_keys = {
                        (item["row_index"], item["column"])
                        for item in llm_result.resolved_items
                    }
                    all_flagged_items = [
                        item for item in all_flagged_items
                        if (item.row_index, item.column) not in resolved_keys
                    ]
                elif file_flagged and not api_key:
                    llm_skipped = True

                processed_dataframes.append(dataframe)
                source_filenames.append(filename)

                source_files_info.append({
                    "filename": filename,
                    "country": meta["Country"],
                    "retailer": meta["Retailer"],
                    "city": meta["City"],
                    "store_name": meta.get("Store Name", ""),
                    "store_format": meta.get("Store Format", ""),
                    "row_count": len(dataframe),
                    "date_processed": datetime.now().strftime("%Y-%m-%d %H:%M"),
                })

            except Exception as exc:
                error_msg = f"Error processing {filename}: {exc}"
                logger.error(error_msg, exc_info=True)
                all_errors.append(error_msg)
                st.error(error_msg)
                continue

        # ── Merge all processed files ─────────────────────────
        if processed_dataframes:
            progress_bar.progress(1.0, text="Merging files...")
            with status_container.container():
                st.text("Merging all processed files...")

            # Merge all processed dataframes
            merge_result = merge_dataframes(
                processed_dataframes,
                source_filenames,
            )

            # Save results to session state
            st.session_state["processed_dataframes"] = processed_dataframes
            st.session_state["all_flagged_items"] = all_flagged_items
            st.session_state["all_changes_log"] = all_changes_log
            st.session_state["all_errors"] = all_errors
            st.session_state["merge_result"] = merge_result
            st.session_state["source_files_info"] = source_files_info
            st.session_state["llm_resolved_count"] = llm_resolved_count
            st.session_state["llm_skipped"] = llm_skipped

            # If no overlaps, go straight to quality check
            if not merge_result.overlaps:
                st.session_state["final_dataframe"] = merge_result.dataframe
                st.session_state["overlap_decisions_applied"] = True

            st.session_state["processing_complete"] = True
            status_container.empty()
            progress_bar.progress(1.0, text="Processing complete!")
            st.rerun()

        else:
            st.error("No files could be processed successfully.")


# ═══════════════════════════════════════════════════════════════════════════
# Section 4: Overlap Resolution
# ═══════════════════════════════════════════════════════════════════════════

if (
    st.session_state["processing_complete"]
    and st.session_state.get("merge_result") is not None
    and st.session_state["merge_result"].overlaps
    and not st.session_state["overlap_decisions_applied"]
):
    st.divider()
    st.header("⚠️ Store Overlaps Detected")
    st.caption(
        "The following stores already exist in your master file. "
        "Choose whether to replace them with the new data or skip."
    )

    merge_result = st.session_state["merge_result"]
    decisions: dict[str, str] = {}

    for overlap in merge_result.overlaps:
        store_label = f"{overlap.retailer} {overlap.city}"
        if overlap.store_format:
            store_label += f" ({overlap.store_format})"
        store_key = (
            f"{overlap.retailer}|{overlap.city}|{overlap.store_format or ''}"
        )

        col_info, col_choice = st.columns([3, 1])
        with col_info:
            st.write(
                f"**{store_label}** — "
                f"{overlap.existing_row_count} existing rows, "
                f"{overlap.new_row_count} new rows"
            )
        with col_choice:
            choice = st.radio(
                "Action",
                options=["Replace", "Skip"],
                key=f"overlap_{store_key}",
                horizontal=True,
                label_visibility="collapsed",
            )
            decisions[store_key] = choice.lower()

    if st.button("Apply Decisions", type="primary", use_container_width=True):
        final_df = apply_overlap_decisions(
            merge_result.dataframe, None, decisions
        )
        st.session_state["final_dataframe"] = final_df
        st.session_state["overlap_decisions"] = decisions
        st.session_state["overlap_decisions_applied"] = True
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# Section 5: Quality Check + Results
# ═══════════════════════════════════════════════════════════════════════════

if (
    st.session_state["processing_complete"]
    and st.session_state["overlap_decisions_applied"]
    and st.session_state["final_dataframe"] is not None
):
    final_df = st.session_state["final_dataframe"]
    all_flagged_items = st.session_state["all_flagged_items"]
    all_changes_log = st.session_state["all_changes_log"]
    all_errors = st.session_state["all_errors"]
    source_files_info = st.session_state["source_files_info"]
    merge_result = st.session_state["merge_result"]
    llm_resolved_count = st.session_state["llm_resolved_count"]
    llm_skipped = st.session_state["llm_skipped"]

    # Run quality check if not done yet
    if st.session_state["quality_report"] is None:
        flagged_as_dicts = [
            {
                "row_index": item.row_index,
                "column": item.column,
                "original_value": item.original_value,
            }
            for item in all_flagged_items
        ]

        quality_report = check_quality(
            dataframe=final_df,
            normalization_log=all_changes_log,
            flagged_items=flagged_as_dicts,
            exchange_rate_used={"GBP": exchange_rate_gbp_eur, "EUR": 1.0},
            source_filenames=[info["filename"] for info in source_files_info],
            rows_per_file={
                info["filename"]: info["row_count"]
                for info in source_files_info
            },
        )
        st.session_state["quality_report"] = quality_report
    else:
        quality_report = st.session_state["quality_report"]

    # ── Processing Summary ────────────────────────────────────────
    st.divider()
    st.header("📊 Step 2: Processing Summary")

    total_skus = quality_report.total_rows
    deterministic_count = len(all_changes_log)
    flagged_count = len(all_flagged_items)

    # Compute percentages (guard against zero total)
    total_items = deterministic_count + llm_resolved_count + flagged_count
    if total_items > 0:
        pct_deterministic = round(deterministic_count / total_items * 100, 1)
        pct_llm = round(llm_resolved_count / total_items * 100, 1)
        pct_flagged = round(flagged_count / total_items * 100, 1)
    else:
        pct_deterministic = pct_llm = pct_flagged = 0.0

    metric_cols = st.columns(6)
    with metric_cols[0]:
        st.metric("Files Processed", len(source_files_info))
    with metric_cols[1]:
        st.metric("Total SKUs", total_skus)
    with metric_cols[2]:
        st.metric("Cleaned (Deterministic)", f"{deterministic_count} ({pct_deterministic}%)")
    with metric_cols[3]:
        st.metric("Cleaned (LLM)", f"{llm_resolved_count} ({pct_llm}%)")
    with metric_cols[4]:
        st.metric("Flagged for Review", f"{flagged_count} ({pct_flagged}%)")
    with metric_cols[5]:
        total_cost = st.session_state.get("total_llm_cost", 0.0)
        total_in = st.session_state.get("total_input_tokens", 0)
        total_out = st.session_state.get("total_output_tokens", 0)
        st.metric(
            "LLM Cost",
            f"${total_cost:.3f}",
            delta=f"{total_in:,} in / {total_out:,} out tokens"
        )

    llm_failed = st.session_state.get("llm_failed_batches", 0)
    llm_total = st.session_state.get("llm_total_batches", 0)
    if llm_failed > 0:
        st.warning(
            f"{llm_failed} of {llm_total} LLM batches failed to parse. "
            f"Some items may not have been normalized by the LLM. "
            f"Check the console log for details."
        )

    if llm_skipped and not api_key:
        st.info(
            "No API key configured. Ambiguous items are flagged for manual review "
            "instead of LLM-resolved. Set ANTHROPIC_API_KEY in "
            ".streamlit/secrets.toml to enable automatic resolution."
        )

    if merge_result and merge_result.duplicate_rows_removed > 0:
        st.info(
            f"{merge_result.duplicate_rows_removed} exact duplicate rows were removed."
        )

    if all_errors:
        with st.expander(f"⚠️ Processing Warnings & Errors ({len(all_errors)})"):
            for error_msg in all_errors:
                st.text(error_msg)

    # Expandable details
    with st.expander("View Details"):
        st.subheader("Null Counts by Column")
        null_data = {
            "Column": list(quality_report.null_counts.keys()),
            "Null Count": list(quality_report.null_counts.values()),
            "Null %": [
                f"{v}%" for v in quality_report.null_percentages.values()
            ],
        }
        st.dataframe(
            pd.DataFrame(null_data),
            use_container_width=True,
            hide_index=True,
        )

        if all_changes_log:
            st.subheader("Normalization Log (first 50)")
            log_preview = all_changes_log[:50]
            st.dataframe(
                pd.DataFrame(log_preview),
                use_container_width=True,
                hide_index=True,
            )

    # Quality status badge
    if quality_report.is_clean:
        st.success("✅ Data passed all quality checks.")
    else:
        issue_count = (
            len(quality_report.invalid_categoricals)
            + len(quality_report.invalid_numerics)
            + len(quality_report.missing_required)
        )
        st.warning(
            f"⚠️ {issue_count} quality issue(s) found. "
            "Review the Data Quality Report sheet in the downloaded Excel."
        )

    # ── Data Error Check ─────────────────────────────────────────
    st.divider()
    st.header("📋 Step 3: Data Error Check")

    # Build the dict of flagged cells with reasons for highlighting
    flagged_cells_dict: dict[tuple[int, str], str] = {
        (item.row_index, item.column): item.reason for item in all_flagged_items
    }

    # Identify rows that have at least one flagged cell
    flagged_row_indices: set[int] = {row_idx for row_idx, _ in flagged_cells_dict.keys()}
    total_rows = len(final_df)
    flagged_row_count = len(flagged_row_indices & set(final_df.index))

    if flagged_row_count == 0:
        st.success("All data clean!")
    else:
        st.warning(
            f"{len(flagged_cells_dict)} cells flagged for review across {flagged_row_count} rows — "
            "download the Excel, fix the yellow-highlighted cells (see Issue Description column), "
            "then re-upload below."
        )

    # Expandable full data view (collapsed by default)
    with st.expander("View Full Data"):
        st.dataframe(final_df, use_container_width=True, hide_index=True)

    # ── Download Button ───────────────────────────────────────────
    st.divider()
    st.header("💾 Download")

    with st.spinner("Generating formatted Excel file..."):
        with tempfile.TemporaryDirectory() as download_temp_dir:
            output_path = Path(download_temp_dir) / "master_consolidated.xlsx"

            format_and_save(
                dataframe=final_df,
                quality_report=quality_report,
                source_files_info=source_files_info,
                flagged_cells=flagged_cells_dict,
                output_path=output_path,
            )

            excel_bytes = output_path.read_bytes()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    download_filename = f"master_consolidated_{timestamp}.xlsx"

    st.download_button(
        label="📥 Download Master Excel",
        data=excel_bytes,
        file_name=download_filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )

    st.caption(
        f"File contains {len(final_df)} SKU rows across 3 sheets: "
        "SKU Data, Data Quality Report, Source Files."
    )

    # ── Re-upload Corrected Master ────────────────────────────────
    st.divider()
    st.header("📤 Re-upload Corrected Master")
    
    corrected_file = st.file_uploader(
        "Upload corrected Excel",
        type=["xlsx"],
        key="corrected_master_upload",
        help="Upload the master file after fixing any flagged cells"
    )
    
    if corrected_file is not None:
        try:
            # Read the corrected file
            corrected_df = pd.read_excel(corrected_file, sheet_name="SKU Data")
            
            # Drop Issue Description column if present
            if "Issue Description" in corrected_df.columns:
                corrected_df = corrected_df.drop(columns=["Issue Description"])
            
            # Update session state with corrected dataframe
            st.session_state["final_dataframe"] = corrected_df
            
            st.success(f"✅ Corrected master uploaded successfully! {len(corrected_df)} rows loaded.")
            st.rerun()
            
        except Exception as exc:
            st.error(f"Error reading corrected file: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
# Developer Tools Section — Accuracy Tester
# ═══════════════════════════════════════════════════════════════════════════

if show_dev_tools:
    st.divider()
    st.header("🛠️ Developer Tools — Accuracy Tester")
    st.caption(
        "Compare the tool's output against a ground truth master file to "
        "measure accuracy and identify systematic errors."
    )
    
    col1, col2 = st.columns(2)
    with col1:
        tool_output_file = st.file_uploader(
            "Tool Output Excel",
            type=["xlsx"],
            key="accuracy_tool_output",
            help="The Excel file produced by this tool"
        )
    with col2:
        ground_truth_file = st.file_uploader(
            "Ground Truth Excel",
            type=["xlsx"],
            key="accuracy_ground_truth",
            help="Manually verified correct output"
        )
    
    if tool_output_file and ground_truth_file and st.button(
        "Run Accuracy Test",
        type="primary",
        use_container_width=True
    ):
        with st.spinner("Running comparison..."):
            # Import accuracy_tester functions
            from processing.accuracy_tester import (
                load_excel_for_comparison,
                compare_dataframes,
                prepare_llm_batch,
                COLUMNS_TO_COMPARE
            )
            from processing.llm_cleaner import analyze_differences_for_root_cause
            
            try:
                # Load files
                tool_df = load_excel_for_comparison(tool_output_file)
                truth_df = load_excel_for_comparison(ground_truth_file)
                
                # Run comparison
                result = compare_dataframes(tool_df, truth_df, COLUMNS_TO_COMPARE)
                
                # Display metrics
                st.subheader("📊 Accuracy Metrics")
                
                metric_cols = st.columns(4)
                metric_cols[0].metric(
                    "Overall Accuracy",
                    f"{result.metrics.overall_accuracy_pct:.1f}%"
                )
                metric_cols[1].metric(
                    "Cells Compared",
                    f"{result.metrics.total_cells_compared:,}"
                )
                metric_cols[2].metric(
                    "Matches",
                    f"{result.metrics.matching_cells:,}",
                    delta=f"{result.metrics.both_blank_cells:,} both blank"
                )
                metric_cols[3].metric(
                    "Differences",
                    f"{result.metrics.different_cells:,}"
                )
                
                # Per-column accuracy table
                st.subheader("Per-Column Accuracy")
                col_accuracy_df = pd.DataFrame({
                    "Column": list(result.metrics.accuracy_by_column.keys()),
                    "Accuracy %": [
                        f"{v:.1f}%" 
                        for v in result.metrics.accuracy_by_column.values()
                    ],
                    "Differences": list(result.metrics.differences_by_column.values())
                })
                st.dataframe(col_accuracy_df, use_container_width=True, hide_index=True)
                
                # Unmatched rows warnings
                if result.unmatched_tool_rows or result.unmatched_truth_rows:
                    st.warning(
                        f"{len(result.unmatched_tool_rows)} rows in tool output not in ground truth | "
                        f"{len(result.unmatched_truth_rows)} rows in ground truth not in tool output"
                    )
                
                # Root cause analysis
                if result.differences and api_key:
                    st.subheader("🔍 Root Cause Analysis")
                    with st.spinner("Analyzing differences with Claude Sonnet..."):
                        # Prepare batch for LLM
                        llm_batch = prepare_llm_batch(
                            result.differences,
                            tool_df,
                            max_differences=100
                        )
                        
                        # Call LLM for root cause analysis
                        rca_result = analyze_differences_for_root_cause(
                            llm_batch,
                            api_key
                        )
                    
                    if rca_result.error:
                        st.error(f"Root cause analysis failed: {rca_result.error}")
                    else:
                        # Display root cause summary
                        st.write("**Root Cause Summary:**")
                        
                        # Create a more readable category mapping
                        category_labels = {
                            "file_reader_error": "File Reader Error",
                            "column_mapping_error": "Column Mapping Error",
                            "normalization_rule_error": "Normalization Rule Error",
                            "llm_inference_error": "LLM Inference Error",
                            "numeric_conversion_error": "Numeric Conversion Error",
                            "price_calculation_error": "Price Calculation Error",
                            "ground_truth_error": "Ground Truth Error"
                        }
                        
                        summary_df = pd.DataFrame({
                            "Category": [
                                category_labels.get(cat, cat) 
                                for cat in rca_result.root_cause_summary.keys()
                            ],
                            "Count": list(rca_result.root_cause_summary.values())
                        })
                        st.dataframe(summary_df, use_container_width=True, hide_index=True)
                        
                        # Display fix recommendations
                        st.write("**Fix Recommendations:**")
                        recommendations = [
                            analysis.fix_recommendation
                            for analysis in rca_result.analyses
                            if analysis.fix_recommendation
                        ]
                        
                        if recommendations:
                            # Deduplicate recommendations
                            unique_recs = list(set(recommendations))
                            for rec in unique_recs:
                                st.markdown(f"- {rec}")
                        else:
                            st.info("No specific fix recommendations (all differences may be ground truth errors or require manual review)")
                        
                        st.caption(
                            f"API cost: ${rca_result.api_cost_estimate:.4f} "
                            f"({rca_result.input_tokens:,} in / {rca_result.output_tokens:,} out tokens)"
                        )
                
                elif result.differences and not api_key:
                    st.info(
                        "Configure API key in .streamlit/secrets.toml to enable "
                        "root cause analysis and fix recommendations."
                    )
                
                # Sample differences (expandable)
                if result.differences:
                    with st.expander(f"Sample Differences (first 50 of {len(result.differences)})"):
                        sample_diffs = result.differences[:50]
                        diff_df = pd.DataFrame([
                            {
                                "Row Key": f"{d.row_key.country}|{d.row_key.city}|{d.row_key.retailer}|{d.row_key.photo}",
                                "Column": d.column,
                                "Tool Value": d.tool_value,
                                "Truth Value": d.truth_value,
                                "Type": d.difference_type
                            }
                            for d in sample_diffs
                        ])
                        st.dataframe(diff_df, use_container_width=True, hide_index=True)
                else:
                    st.success("✅ Perfect match! No differences found between tool output and ground truth.")
                
                # Errors
                if result.errors:
                    with st.expander(f"⚠️ Errors ({len(result.errors)})"):
                        for error in result.errors:
                            st.text(error)
                
            except Exception as exc:
                st.error(f"Error running accuracy test: {exc}")
                logger.error("Accuracy test failed", exc_info=True)
