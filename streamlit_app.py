import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import re
import json
import csv
import io
from datetime import datetime
from openai import OpenAI

# ==============================================================================
#  PAGE CONFIG
# ==============================================================================
st.set_page_config(
    page_title="XRIG Configurator AI",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==============================================================================
#  SECRETS & CREDENTIALS
# ==============================================================================

def get_openai_client():
    api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def get_gspread_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


# ==============================================================================
#  GOOGLE SHEETS CONFIG
# ==============================================================================
CONFIG_SHEET_NAME = "Copy of Testing - Spec Config V8"
CONFIG_WORKSHEET_NAME = "Sheet1"


# ==============================================================================
#  DATA LOADING (cached)
# ==============================================================================

@st.cache_data(ttl=300, show_spinner="Syncing builds from Google Sheets...")
def load_all_builds():
    """Fetch and index all PC builds from the configurator Google Sheet."""
    gc = get_gspread_client()
    sh = gc.open(CONFIG_SHEET_NAME)
    worksheet = sh.worksheet(CONFIG_WORKSHEET_NAME)
    data = worksheet.get_all_values()

    all_builds = []
    for r, row in enumerate(data):
        for c, cell_value in enumerate(row):
            if cell_value.strip() == "Processor":
                try:
                    def get_d(off, _r=r, _c=c, _data=data):
                        if _r + off < len(_data):
                            name = _data[_r + off][_c + 1]
                            raw_price = _data[_r + off][_c + 2]
                            clean_price_str = re.sub(r"[^\d]", "", raw_price)
                            return name, clean_price_str
                        return "", ""

                    p_cpu, pr_cpu = get_d(0)
                    p_mobo, pr_mobo = get_d(1)
                    p_ram, pr_ram = get_d(2)
                    p_ssd, pr_ssd = get_d(3)
                    p_store1, pr_store1 = get_d(4)
                    p_case, pr_case = get_d(5)
                    p_fans, pr_fans = get_d(6)
                    p_wifi, pr_wifi = get_d(7)
                    p_gpu, pr_gpu = get_d(8)
                    p_cooler, pr_cooler = get_d(9)
                    p_psu, pr_psu = get_d(10)
                    p_extra, pr_extra = get_d(11)
                    p_plate, pr_plate = get_d(12)
                    p_paste, pr_paste = get_d(13)

                    quote_id = data[r - 1][c + 1] if r > 0 else "Unknown"
                    customer_name = data[r - 2][c + 1] if r > 1 else "N/A"
                    date_val = data[r - 3][c + 1] if r > 2 else ""
                    profit_pct = data[r + 16][c] if r + 16 < len(data) else "N/A"

                    if r + 16 < len(data):
                        raw_price = data[r + 16][c + 1]
                        clean_price = re.sub(r"[^\d]", "", raw_price)
                        if clean_price:
                            all_builds.append(
                                {
                                    "price": int(clean_price),
                                    "parts": {
                                        "cpu": p_cpu, "mobo": p_mobo, "ram": p_ram,
                                        "ssd": p_ssd, "storage1": p_store1, "case": p_case,
                                        "fans": p_fans, "wifi": p_wifi, "gpu": p_gpu,
                                        "cooler": p_cooler, "psu": p_psu, "extra": p_extra,
                                        "plate": p_plate, "paste": p_paste,
                                    },
                                    "prices": {
                                        "cpu": pr_cpu, "mobo": pr_mobo, "ram": pr_ram,
                                        "ssd": pr_ssd, "storage1": pr_store1, "case": pr_case,
                                        "fans": pr_fans, "wifi": pr_wifi, "gpu": pr_gpu,
                                        "cooler": pr_cooler, "psu": pr_psu, "extra": pr_extra,
                                        "plate": pr_plate, "paste": pr_paste,
                                    },
                                    "meta": {
                                        "quote_id": quote_id,
                                        "customer": customer_name,
                                        "date": date_val,
                                        "profit": profit_pct,
                                    },
                                }
                            )
                except IndexError:
                    continue
    all_builds.reverse()
    return all_builds


# ==============================================================================
#  SEARCH / FILTER LOGIC
# ==============================================================================

def search_builds(builds, filters):
    """Filter builds by budget, components, quote ID, client, dates."""
    results = []
    seen = set()
    for b in builds:
        meta = b["meta"]

        # Quote ID
        qid = filters.get("quote_id", "").strip().lower()
        if qid and qid not in meta.get("quote_id", "").lower():
            continue

        # Client
        client = filters.get("client", "").strip().lower()
        if client and client not in (meta.get("customer") or "").lower():
            continue

        # Date range
        date_from = filters.get("date_from", "").strip()
        date_to = filters.get("date_to", "").strip()
        if date_from or date_to:
            try:
                b_date = datetime.strptime(meta.get("date", ""), "%Y-%m-%d")
                if date_from and b_date < datetime.strptime(date_from, "%Y-%m-%d"):
                    continue
                if date_to and b_date > datetime.strptime(date_to, "%Y-%m-%d"):
                    continue
            except ValueError:
                pass

        # Budget
        min_b = filters.get("min_budget", 0)
        max_b = filters.get("max_budget", 99_99_999)
        if not (min_b <= b["price"] <= max_b):
            continue

        # Component filters
        valid = True
        component_keys = [
            "cpu", "mobo", "ram", "ssd", "storage1", "case",
            "fans", "wifi", "gpu", "cooler", "psu", "extra", "plate", "paste",
        ]
        for key in component_keys:
            search_val = filters.get(key, "").strip().lower()
            exclude_val = filters.get(f"{key}_exclude", "").strip().lower()
            part_name = b["parts"].get(key, "").lower()

            if search_val and search_val not in part_name:
                valid = False
                break
            if exclude_val:
                exclusions = [x.strip() for x in exclude_val.split(",") if x.strip()]
                if any(ex in part_name for ex in exclusions):
                    valid = False
                    break
        if not valid:
            continue

        # Unique filter
        if filters.get("unique_only"):
            sig = "".join(b["parts"][k].strip().lower() for k in b["parts"])
            if sig in seen:
                continue
            seen.add(sig)

        results.append(b)
    return results


# ==============================================================================
#  AI CHATBOT LOGIC
# ==============================================================================

def get_ai_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "find_builds",
                "description": (
                    "Find previously quoted PC builds from the internal database within a "
                    "given budget range, and matching specific component keywords. "
                    "A 'lakh' or 'L' is 100,000 INR."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_budget": {"type": "integer", "description": "Maximum budget in INR"},
                        "min_budget": {"type": "integer", "description": "Minimum budget in INR, can be 0"},
                        "cpu": {"type": "string"}, "mobo": {"type": "string"},
                        "ram": {"type": "string"}, "ssd": {"type": "string"},
                        "storage1": {"type": "string"}, "case": {"type": "string"},
                        "fans": {"type": "string"}, "wifi": {"type": "string"},
                        "gpu": {"type": "string"}, "cooler": {"type": "string"},
                        "psu": {"type": "string"},
                        "quote_id": {"type": "string"}, "client": {"type": "string"},
                        "exact_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "date_from": {"type": "string"}, "date_to": {"type": "string"},
                    },
                    "required": ["max_budget"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_uploaded_file",
                "description": "Search the user-uploaded .txt or .csv price list for component names and prices.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Keyword to search in uploaded file"},
                    },
                    "required": ["query"],
                },
            },
        },
    ]


def handle_tool_call(tool_call, builds, uploaded_data):
    """Execute a tool call and return the result string."""
    args = json.loads(tool_call.function.arguments)
    name = tool_call.function.name

    if name == "find_builds":
        max_budget = args.get("max_budget", 9999999)
        min_budget = args.get("min_budget", 0)
        filters = {"min_budget": min_budget, "max_budget": max_budget}

        # Component filters
        for k in ["cpu", "mobo", "ram", "ssd", "storage1", "case", "fans", "wifi", "gpu", "cooler", "psu"]:
            if args.get(k):
                filters[k] = args[k]

        # Metadata filters
        if args.get("quote_id"):
            filters["quote_id"] = args["quote_id"]
        if args.get("client"):
            filters["client"] = args["client"]
        if args.get("exact_date"):
            filters["date_from"] = args["exact_date"]
            filters["date_to"] = args["exact_date"]
        else:
            if args.get("date_from"):
                filters["date_from"] = args["date_from"]
            if args.get("date_to"):
                filters["date_to"] = args["date_to"]

        found = search_builds(builds, filters)
        if not found:
            return "No builds found matching your constraints."

        # Store for pagination
        st.session_state["last_build_results"] = found
        batch = found[:5]
        lines = []
        for idx, b in enumerate(batch):
            parts_str = "\n".join(
                f"- **{v}** ({k})" for k, v in b["parts"].items() if v
            )
            bid = b["meta"].get("quote_id", "Unknown")
            bdate = b["meta"].get("date", "Unknown")
            lines.append(
                f"### Build Option {idx + 1} [Quote {bid}] [{bdate}] - ₹{b['price']:,}\n{parts_str}"
            )
        result = "\n\n".join(lines)
        remaining = len(found) - 5
        if remaining > 0:
            result += f"\n\n*...and {remaining} more matching builds available.*"
        return result

    elif name == "search_uploaded_file":
        query = args.get("query", "").lower()
        terms = query.split()
        found = []
        for row in uploaded_data:
            row_text = " ".join(str(v) for v in row.values()).lower()
            if all(t in row_text for t in terms):
                found.append(row)
        if not found:
            return f"No items matching '{query}' found in the uploaded file."
        lines = []
        for item in found[:10]:
            parts = " | ".join(f"{k}: {v}" for k, v in item.items() if v)
            lines.append(f"- {parts}")
        if len(found) > 10:
            lines.append(f"... and {len(found) - 10} more items.")
        return "Found in uploaded file:\n" + "\n".join(lines)

    return "Unknown tool."


def run_chat(user_message, builds, uploaded_data):
    """Send a message through OpenAI with tool support, return assistant reply."""
    client = get_openai_client()
    if client is None:
        return "OpenAI API key not configured. Add it to Streamlit secrets."

    today_str = datetime.now().strftime("%Y-%m-%d")
    has_upload = len(uploaded_data) > 0
    upload_note = (
        " A user-uploaded price file is available. When the user asks about prices, "
        "also search the uploaded file using the `search_uploaded_file` tool."
        if has_upload
        else ""
    )

    system_msg = (
        f"You are a helpful PC builder assistant called Configurator AI. "
        f"The current date is {today_str}. Help the user find PC builds within their budget "
        f"from the Google Sheets database. NEVER hallucinate specs. "
        f"When presenting a build, clearly list components, Quote ID, and total price. "
        f"Use markdown formatting.{upload_note}"
    )

    messages = [{"role": "system", "content": system_msg}]
    for msg in st.session_state.get("chat_history", [])[-20:]:
        if msg["role"] in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=get_ai_tools(),
        tool_choice="auto",
    )

    response_message = response.choices[0].message

    if response_message.tool_calls:
        messages.append(response_message)
        for tc in response_message.tool_calls:
            result = handle_tool_call(tc, builds, uploaded_data)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": result,
                }
            )
        second = client.chat.completions.create(model="gpt-4o", messages=messages)
        return second.choices[0].message.content

    return response_message.content


# ==============================================================================
#  FILE UPLOAD PARSING
# ==============================================================================

def parse_uploaded_file(uploaded_file):
    """Parse a .txt or .csv file into a list of dicts."""
    filename = uploaded_file.name.lower()
    raw = uploaded_file.getvalue().decode("utf-8", errors="replace")
    rows = []

    if filename.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(raw))
        for row in reader:
            rows.append({k.strip(): v.strip() for k, v in row.items() if k})
    else:
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        if len(lines) >= 2:
            delim = "\t" if "\t" in lines[0] else ("," if "," in lines[0] else None)
            if delim:
                reader = csv.DictReader(io.StringIO(raw), delimiter=delim)
                for row in reader:
                    rows.append({k.strip(): v.strip() for k, v in row.items() if k})
            else:
                for line in lines:
                    rows.append({"line": line})
        else:
            for line in lines:
                rows.append({"line": line})
    return rows


# ==============================================================================
#  STREAMLIT UI
# ==============================================================================

def render_build_card(build, index=0):
    """Render a single build as a Streamlit card."""
    meta = build["meta"]
    parts = build["parts"]
    prices = build["prices"]

    with st.container():
        col1, col2, col3 = st.columns([2, 4, 2])
        with col1:
            st.markdown(f"**Quote:** `{meta.get('quote_id', 'N/A')}`")
            st.markdown(f"**Client:** {meta.get('customer', 'N/A')}")
        with col2:
            st.markdown(f"**Date:** {meta.get('date', 'N/A')}")
        with col3:
            st.metric("Total Price", f"₹{build['price']:,}")

        labels = {
            "cpu": "Processor", "mobo": "Motherboard", "ram": "RAM",
            "ssd": "SSD", "storage1": "Storage", "case": "Case",
            "fans": "Fans", "wifi": "WiFi", "gpu": "GPU",
            "cooler": "Cooler", "psu": "PSU", "extra": "Extra",
            "plate": "Plate", "paste": "Paste",
        }

        cols = st.columns(2)
        for i, (key, label) in enumerate(labels.items()):
            part_name = parts.get(key, "")
            price_val = prices.get(key, "")
            if part_name:
                with cols[i % 2]:
                    price_display = f" — ₹{int(price_val):,}" if price_val and price_val.isdigit() and int(price_val) > 0 else ""
                    st.markdown(f"**{label}:** {part_name}{price_display}")

        st.divider()


def main():
    # ------- SIDEBAR -------
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/workstation.png", width=60)
        st.title("XRIG Configurator AI")
        st.caption("PC Build Finder & AI Chat")

        page = st.radio(
            "Navigate",
            ["🤖 AI Chat", "🔍 Build Search"],
            label_visibility="collapsed",
        )

        st.divider()

        # File upload
        uploaded_file = st.file_uploader(
            "Upload Price List (.csv / .txt)", type=["csv", "txt"]
        )
        if uploaded_file:
            st.session_state["uploaded_data"] = parse_uploaded_file(uploaded_file)
            st.success(f"Loaded {len(st.session_state['uploaded_data'])} rows")

        st.divider()
        if st.button("🔄 Refresh Data", use_container_width=True):
            load_all_builds.clear()
            st.rerun()

    # ------- LOAD DATA -------
    try:
        builds = load_all_builds()
    except Exception as e:
        builds = []
        st.error(f"Failed to load builds: {e}")

    uploaded_data = st.session_state.get("uploaded_data", [])

    # ========================
    # PAGE: AI CHAT
    # ========================
    if page == "🤖 AI Chat":
        st.header("🤖 Configurator AI Chat")
        st.caption(
            "Ask me about PC builds, budgets, component prices — I'll search the database for you."
        )

        # Init chat history
        if "chat_history" not in st.session_state:
            st.session_state["chat_history"] = [
                {
                    "role": "assistant",
                    "content": (
                        "Hello! I'm your AI Configurator Assistant. Tell me your budget "
                        "or requirements, and I'll find the perfect PC build for you. "
                        'For example: *"Make a build within 1.5L"*'
                    ),
                }
            ]

        # Render chat messages
        for msg in st.session_state["chat_history"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Chat input
        if prompt := st.chat_input("Type your query..."):
            st.session_state["chat_history"].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    reply = run_chat(prompt, builds, uploaded_data)
                st.markdown(reply)

            st.session_state["chat_history"].append(
                {"role": "assistant", "content": reply}
            )

        # New chat button
        col1, col2 = st.columns([6, 1])
        with col2:
            if st.button("New Chat"):
                st.session_state["chat_history"] = [
                    {
                        "role": "assistant",
                        "content": "Chat cleared! How can I help you?",
                    }
                ]
                st.rerun()

    # ========================
    # PAGE: BUILD SEARCH
    # ========================
    elif page == "🔍 Build Search":
        st.header("🔍 PC Build Search")

        with st.expander("Filters", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                min_budget = st.number_input("Min Budget (₹)", value=0, step=10000)
            with col2:
                max_budget = st.number_input("Max Budget (₹)", value=200000, step=10000)
            with col3:
                quote_id = st.text_input("Quote ID")
            with col4:
                client_name = st.text_input("Client Name")

            col_d1, col_d2, col_d3 = st.columns([1, 1, 1])
            with col_d1:
                date_from = st.date_input("From Date", value=None)
            with col_d2:
                date_to = st.date_input("To Date", value=None)
            with col_d3:
                unique_only = st.checkbox("Unique Builds Only")

            st.subheader("Component Filters")
            component_labels = {
                "cpu": "CPU", "mobo": "Motherboard", "ram": "RAM",
                "ssd": "SSD", "gpu": "GPU", "cooler": "Cooler",
                "case": "Case", "psu": "PSU",
            }
            component_filters = {}
            cols = st.columns(4)
            for i, (key, label) in enumerate(component_labels.items()):
                with cols[i % 4]:
                    component_filters[key] = st.text_input(f"{label}", key=f"filter_{key}")

        btn_col1, btn_col2 = st.columns([4, 1])
        with btn_col2:
            if st.button("✖ Clear Filters", use_container_width=True):
                for key in ["filter_cpu", "filter_mobo", "filter_ram", "filter_ssd",
                            "filter_gpu", "filter_cooler", "filter_case", "filter_psu"]:
                    st.session_state[key] = ""
                st.session_state["search_results"] = []
                st.rerun()
        with btn_col1:
            search_clicked = st.button("🔍 Search Builds", type="primary", use_container_width=True)
        if search_clicked:
            filters = {
                "min_budget": min_budget,
                "max_budget": max_budget,
                "quote_id": quote_id,
                "client": client_name,
                "date_from": str(date_from) if date_from else "",
                "date_to": str(date_to) if date_to else "",
                "unique_only": unique_only,
            }
            filters.update(component_filters)

            results = search_builds(builds, filters)
            st.session_state["search_results"] = results

        results = st.session_state.get("search_results", [])
        if results:
            st.success(f"Found **{len(results)}** matching builds")

            # Pagination
            per_page = 5
            total_pages = max(1, (len(results) + per_page - 1) // per_page)
            page_num = st.number_input(
                "Page", min_value=1, max_value=total_pages, value=1, step=1
            )
            start = (page_num - 1) * per_page
            end = start + per_page

            for idx, build in enumerate(results[start:end], start=start + 1):
                with st.container(border=True):
                    render_build_card(build, idx)


if __name__ == "__main__":
    main()
