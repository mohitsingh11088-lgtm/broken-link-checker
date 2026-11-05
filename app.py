
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, urldefrag
import concurrent.futures
import ipaddress
import socket

# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="SEO Broken Link Checker",
    page_icon="🔗",
    layout="wide"
)

st.title("🔗 Professional SEO Broken Link Checker")

st.markdown("""
Scan websites for broken internal links or upload a custom bulk URL list.
Identify HTTP errors, redirects, connection failures and more.
""")

# ==========================================
# CONFIGURATION
# ==========================================

TIMEOUT = 10
MAX_WORKERS = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 "
        "Safari/537.36 SEO-Link-Checker"
    )
}


# ==========================================
# URL VALIDATION
# ==========================================

def is_valid_url(url):
    """Validate URL format and reject private or unsafe destinations."""

    try:
        parsed = urlparse(str(url).strip())

        if parsed.scheme not in ["http", "https"]:
            return False

        if not parsed.hostname:
            return False

        if parsed.username or parsed.password:
            return False

        hostname = parsed.hostname

        # Resolve hostname and reject private/reserved IP addresses.
        addresses = socket.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM
        )

        if not addresses:
            return False

        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])

            if not ip.is_global:
                return False

        return True

    except Exception:
        return False


# ==========================================
# VERIFY SINGLE URL
# ==========================================

def verify_url(url, timeout=TIMEOUT):
    """Check URL status using HEAD and GET fallback."""

    url = str(url).strip()

    if not is_valid_url(url):
        return {
            "Status Code": "Invalid URL",
            "Analysis": "Invalid or unsafe URL",
            "Final URL": url
        }

    try:
        # First attempt: HEAD request
        response = requests.head(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True
        )

        # Retry with GET when HEAD is unsupported or blocked.
        if response.status_code in [403, 405, 501]:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=timeout,
                allow_redirects=True,
                stream=True
            )

        status = response.status_code
        final_url = response.url

        response.close()

        if 200 <= status < 300:
            analysis = "Working"

        elif 300 <= status < 400:
            analysis = "Redirect"

        elif status == 404:
            analysis = "Not Found"

        elif status == 410:
            analysis = "Permanently Removed"

        elif status == 403:
            analysis = "Forbidden"

        elif status == 401:
            analysis = "Unauthorized"

        elif status >= 500:
            analysis = "Server Error"

        else:
            analysis = "Issue Found"

        return {
            "Status Code": status,
            "Analysis": analysis,
            "Final URL": final_url
        }

    except requests.exceptions.Timeout:
        return {
            "Status Code": "Timeout",
            "Analysis": "Connection Timeout",
            "Final URL": url
        }

    except requests.exceptions.SSLError:
        return {
            "Status Code": "SSL Error",
            "Analysis": "SSL Certificate Error",
            "Final URL": url
        }

    except requests.exceptions.ConnectionError:
        return {
            "Status Code": "Connection Error",
            "Analysis": "Unable to Connect",
            "Final URL": url
        }

    except requests.exceptions.RequestException:
        return {
            "Status Code": "Request Error",
            "Analysis": "Request Failed",
            "Final URL": url
        }


# ==========================================
# EXTRACT INTERNAL LINKS
# ==========================================

def get_internal_links(base_url):
    """Extract internal links and anchor text from a webpage."""

    if not is_valid_url(base_url):
        st.error("Invalid or unsafe website URL.")
        return []

    try:
        response = requests.get(
            base_url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        base_domain = urlparse(response.url).hostname.lower()

        internal_links = {}

        for a_tag in soup.find_all("a", href=True):

            href = a_tag.get("href", "").strip()

            if not href:
                continue

            full_url = urljoin(response.url, href)

            # Remove fragments
            full_url, _ = urldefrag(full_url)

            parsed = urlparse(full_url)

            if parsed.scheme not in ["http", "https"]:
                continue

            if not parsed.hostname:
                continue

            if parsed.hostname.lower() != base_domain:
                continue

            # Preserve query strings
            clean_url = full_url

            if clean_url not in internal_links:

                anchor_text = a_tag.get_text(
                    separator=" ",
                    strip=True
                )

                internal_links[clean_url] = {
                    "URL": clean_url,
                    "Anchor Text": anchor_text or "No Anchor Text",
                    "Source Page": response.url
                }

        return list(internal_links.values())

    except requests.exceptions.RequestException as e:
        st.error(f"Website connection error: {e}")
        return []

    except Exception as e:
        st.error(f"Error extracting links: {e}")
        return []


# ==========================================
# BULK URL CHECKER
# ==========================================

def bulk_check_urls(url_list, max_workers=MAX_WORKERS):

    # Clean and remove duplicates
    url_list = list(dict.fromkeys(
        str(url).strip()
        for url in url_list
        if str(url).strip()
    ))

    results = []

    if not url_list:
        return pd.DataFrame()

    progress_bar = st.progress(0)
    status_text = st.empty()

    total = len(url_list)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max_workers
    ) as executor:

        future_to_url = {
            executor.submit(verify_url, url): url
            for url in url_list
        }

        for index, future in enumerate(
            concurrent.futures.as_completed(future_to_url)
        ):

            url = future_to_url[future]

            try:
                result = future.result()

            except Exception as e:
                result = {
                    "Status Code": "Unknown",
                    "Analysis": str(e),
                    "Final URL": url
                }

            results.append({
                "URL": url,
                **result
            })

            progress = (index + 1) / total

            progress_bar.progress(progress)

            status_text.text(
                f"Processed {index + 1} of {total} URLs"
            )

    progress_bar.empty()
    status_text.empty()

    return pd.DataFrame(results)


# ==========================================
# RESULTS DISPLAY
# ==========================================

def display_results(df, filename):

    if df.empty:
        st.warning("No results available.")
        return

    total = len(df)

    working = df["Analysis"].isin(
        ["Working", "Redirect"]
    ).sum()

    broken = total - working

    redirects = (
        df["Analysis"] == "Redirect"
    ).sum()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total URLs", total)

    col2.metric("Working URLs", working)

    col3.metric("Broken / Issues", broken)

    col4.metric("Redirects", redirects)

    st.subheader("Detailed Scan Results")

    # Filters
    filter_options = ["All"] + sorted(
        df["Analysis"].dropna().unique().tolist()
    )

    selected_filter = st.selectbox(
        "Filter Results",
        filter_options,
        key=f"filter_{filename}"
    )

    if selected_filter != "All":
        display_df = df[
            df["Analysis"] == selected_filter
        ]
    else:
        display_df = df

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    # Download CSV
    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="📥 Download Full CSV Report",
        data=csv,
        file_name=filename,
        mime="text/csv"
    )

    # Download broken links only
    broken_df = df[
        ~df["Analysis"].isin(["Working", "Redirect"])
    ]

    if not broken_df.empty:

        broken_csv = broken_df.to_csv(
            index=False
        ).encode("utf-8")

        st.download_button(
            label="📥 Download Broken Links Only",
            data=broken_csv,
            file_name="broken_links_report.csv",
            mime="text/csv"
        )


# ==========================================
# STREAMLIT TABS
# ==========================================

tab1, tab2 = st.tabs([
    "🕵️ Crawl a Website",
    "📂 Bulk URL Upload"
])


# ==========================================
# TAB 1: WEBSITE CRAWLER
# ==========================================

with tab1:

    st.subheader("Website Internal Link Checker")

    target_site = st.text_input(
        "Enter website homepage URL",
        placeholder="https://example.com",
        key="website_url"
    )

    if st.button(
        "🔍 Extract & Check Links",
        key="crawl_btn",
        type="primary"
    ):

        if not target_site.strip():

            st.warning("Please enter a website URL.")

        else:

            with st.spinner("Extracting internal links..."):

                discovered_links = get_internal_links(
                    target_site.strip()
                )

            if discovered_links:

                st.success(
                    f"Found {len(discovered_links)} unique internal links."
                )

                urls = [
                    item["URL"]
                    for item in discovered_links
                ]

                with st.spinner("Checking URL status codes..."):

                    df_results = bulk_check_urls(urls)

                # Attach anchor text and source page
                metadata = pd.DataFrame(discovered_links)

                df_results = df_results.merge(
                    metadata,
                    on="URL",
                    how="left"
                )

                display_results(
                    df_results,
                    "seo_link_report.csv"
                )

            else:

                st.warning(
                    "No internal links found or website could not be accessed."
                )


# ==========================================
# TAB 2: BULK URL UPLOAD
# ==========================================

with tab2:

    st.subheader("Bulk URL Validation")

    uploaded_file = st.file_uploader(
        "Upload TXT or CSV file containing URLs",
        type=["txt", "csv"]
    )

    if uploaded_file is not None:

        input_urls = []

        try:

            if uploaded_file.name.lower().endswith(".csv"):

                raw_df = pd.read_csv(uploaded_file)

                if raw_df.empty or raw_df.shape[1] == 0:
                    st.warning("The CSV file is empty.")

                else:

                    # Prefer a URL column if available
                    url_column = next(
                        (
                            col for col in raw_df.columns
                            if str(col).strip().lower() in
                            ["url", "urls", "link", "website"]
                        ),
                        raw_df.columns[0]
                    )

                    input_urls = (
                        raw_df[url_column]
                        .dropna()
                        .astype(str)
                        .str.strip()
                        .tolist()
                    )

            else:

                content = uploaded_file.getvalue().decode(
                    "utf-8-sig"
                )

                input_urls = [
                    line.strip()
                    for line in content.splitlines()
                    if line.strip()
                ]

            input_urls = list(dict.fromkeys(input_urls))

            st.success(
                f"Successfully loaded {len(input_urls)} unique URLs."
            )

        except Exception as e:

            st.error(f"File parsing error: {e}")

        if input_urls:

            with st.expander("Preview Uploaded URLs"):

                st.dataframe(
                    pd.DataFrame({"URL": input_urls}),
                    use_container_width=True
                )

            if st.button(
                "🚀 Run Bulk Link Validation",
                key="bulk_btn",
                type="primary"
            ):

                with st.spinner("Validating URLs..."):

                    df_bulk_results = bulk_check_urls(
                        input_urls
                    )

                display_results(
                    df_bulk_results,
                    "bulk_seo_link_report.csv"
                )


# ==========================================
# FOOTER
# ==========================================

st.divider()

st.caption(
    "SEO Broken Link Checker | Built with Streamlit, "
    "Python, Pandas and BeautifulSoup"
)
