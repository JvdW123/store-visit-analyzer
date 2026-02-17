"""
Streamlit entry point — Store Visit Analyzer UI.

Wires together the full processing pipeline with a 7-step user flow:
  1. Sidebar settings (exchange rate)
  2. File upload (raw Excel + optional existing master)
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


# ═══════════════════════════════════════════════════════════════════════════
# Main area — Title
# ═══════════════════════════════════════════════════════════════════════════

st.title("📊 Store Visit Analyzer")
st.caption("Data Consolidation & Cleaning Tool — upload raw shelf analysis Excel files to produce a clean master dataset.")


# ═══════════════════════════════════════════════════════════════════════════
# Section 1: File Upload
# ═══════════════════════════════════════════════════════════════════════════

st.header("📁 Upload Files")

upload_col1, upload_col2 = st.columns(2)

with upload_col1:
    raw_files = st.file_uploader(
        "Raw Excel files",
        type=["xlsx"],
        accept_multiple_files=True,
        help="Drag and drop one or more raw store visit Excel files.",
    )

with upload_col2:
    existing_master_file = st.file_uploader(
        "Existing master file (optional)",
        type=["xlsx"],
        accept_multiple_files=False,
        help="Upload a previously generated master file to append new data.",
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

            # Load existing master if provided
            existing_master_df = None
            if existing_master_file is not None:
                try:
                    existing_master_df = pd.read_excel(
                        existing_master_file, sheet_name="SKU Data"
                    )
                except Exception:
                    try:
                        existing_master_df = pd.read_excel(existing_master_file)
                    except Exception as exc:
                        all_errors.append(
                            f"Could not read existing master: {exc}"
                        )

            merge_result = merge_dataframes(
                processed_dataframes,
                source_filenames,
                existing_master=existing_master_df,
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
            st.session_state["_existing_master_df"] = existing_master_df

            # If no overlaps, go straight to quality check
            if not merge_result.overlaps:
                if existing_master_df is not None and not existing_master_df.empty:
                    final_df = pd.concat(
                        [existing_master_df, merge_result.dataframe],
                        ignore_index=True,
                    )
                else:
                    final_df = merge_result.dataframe

                st.session_state["final_dataframe"] = final_df
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
        existing_master_df = st.session_state.get("_existing_master_df")
        final_df = apply_overlap_decisions(
            merge_result.dataframe, existing_master_df, decisions
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

    metric_cols = st.columns(5)
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

    # ── Data Preview ──────────────────────────────────────────────
    st.divider()
    st.header("📋 Step 3: Data Preview")

    # Build the set of flagged cells for highlighting
    flagged_cells_set: set[tuple[int, str]] = {
        (item.row_index, item.column) for item in all_flagged_items
    }

    # Limit preview to 200 rows for performance with Styler
    preview_row_limit = 200
    if len(final_df) > preview_row_limit:
        st.caption(
            f"Showing first {preview_row_limit} of {len(final_df)} rows. "
            "Download the Excel file for the full dataset."
        )
    preview_df = final_df.head(preview_row_limit)

    # Apply yellow highlighting on flagged cells via pandas Styler
    if flagged_cells_set:
        def _highlight_flagged(row: pd.Series) -> list[str]:
            """Return CSS styles for a row — yellow for flagged cells."""
            styles = []
            for col in row.index:
                if (row.name, col) in flagged_cells_set:
                    styles.append("background-color: #FFFF00")
                else:
                    styles.append("")
            return styles

        styled_preview = preview_df.style.apply(_highlight_flagged, axis=1)
        st.dataframe(styled_preview, use_container_width=True, hide_index=True)
    else:
        st.dataframe(preview_df, use_container_width=True, hide_index=True)

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
                flagged_cells=flagged_cells_set,
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
