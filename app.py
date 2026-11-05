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
Scan websites for broken internal links, analyze backend XML blueprints, or upload a custom bulk URL list.
Identify HTTP errors, redirects, connection failures, and extract anchor texts natively.
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
# URL VALIDATION & SECURITY
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
# VERIFY SINGLE URL STATUS
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

        # Retry with GET if HEAD is blocked or unsupported
        if response.status_code in [403, 405, 501]:
            response.close()

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

        # Analyze HTTP status
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

        elif status == 429:
            analysis = "Rate Limited"

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
# EXTRACT INTERNAL LINKS (HOMEPAGE CRAWL)
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
            full_url, _ = urldefrag(full_url)
            parsed = urlparse(full_url)

            if parsed.scheme not in ["http", "https"] or not parsed.hostname:
                continue

            if parsed.hostname.lower() != base_domain:
                continue

            clean_url = full_url

            if clean_url not in internal_links:
                anchor_text = a_tag.get_text(separator=" ", strip=True)
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
# XML SITEMAP CRAWLER ENGINE
# ==========================================


def get_sitemap_urls(sitemap_url, visited=None):
    """Fetch XML sitemap or sitemap index and extract URLs."""

    if visited is None:
        visited = set()

    if sitemap_url in visited:
        return []

    if len(visited) >= 100:
        return []

    visited.add(sitemap_url)

    if not is_valid_url(sitemap_url):
        return []

    try:
        response = requests.get(
            sitemap_url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        response.raise_for_status()

        # Use Python's built-in XML parser
        root = ET.fromstring(response.content)

        urls = []

        # Handle XML namespaces automatically
        for element in root:

            tag = element.tag.split("}")[-1].lower()

            if tag == "sitemap":
                # Sitemap index
                for child in element:

                    if child.tag.split("}")[-1].lower() == "loc":

                        nested_sitemap = child.text.strip()

                        urls.extend(
                            get_sitemap_urls(
                                nested_sitemap,
                                visited
                            )
                        )

            elif tag == "url":
                # Standard URL sitemap
                for child in element:

                    if child.tag.split("}")[-1].lower() == "loc":

                        page_url = child.text.strip()

                        if is_valid_url(page_url):
                            urls.append(page_url)

        response.close()

        return list(set(urls))

    except ET.ParseError as e:
        st.warning(
            f"Invalid XML sitemap ({sitemap_url}): {e}"
        )
        return []

    except requests.exceptions.RequestException as e:
        st.warning(
            f"Could not access sitemap ({sitemap_url}): {e}"
        )
        return []

    except Exception as e:
        st.warning(
            f"Sitemap processing error ({sitemap_url}): {e}"
        )
        return []

# ==========================================
# RESULTS DISPLAY METRICS
# ==========================================

def display_results(df, filename):
    if df.empty:
        st.warning("No results available.")
        return

    total = len(df)
    working_mask = df["Analysis"].isin(["Working", "Redirect"])
    working = working_mask.sum()
    broken = total - working

    col1, col2, col3 = st.columns(3)
    col1.metric("🔍 Total Unique Links Checked", total)
    col2.metric("✅ Clean / Active Links", working)
    col3.metric("🚨 Broken / Actionable Issues", broken, delta=int(broken), delta_color="inverse")

    st.write("---")
    
    with st.expander("🚨 View Broken Links & Server Failures Only", expanded=True):
        broken_df = df[~working_mask]
        if not broken_df.empty:
            st.dataframe(broken_df, use_container_width=True)
        else:
            st.success("🎉 Excellent! Zero broken links discovered on this workspace layout.")

    with st.expander("📋 View Complete Audit Dataset Report"):
        st.dataframe(df, use_container_width=True)

    csv_data = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Complete Audit Report (CSV)",
        data=csv_data,
        file_name=filename,
        mime="text/csv",
        key=f"dl_{filename}"
    )

# ==========================================
# MAIN INTERFACE ROUTER
# ==========================================

def main():
    tab1, tab2, tab3 = st.tabs([
        "🕵️ Crawl Website Homepage",
        "🗺️ Audit via XML Sitemap",
        "📂 Bulk URL List Upload"
    ])

    with tab1:
        st.subheader("Extract & Audit Web Page Interactive Links")
        target_site = st.text_input("Target URL Pathway:", placeholder="https://example.com", key="crawl_input")

        if st.button("Run Live Link Scan", key="crawl_btn"):
            if target_site:
                with st.spinner("Extracting active HTML link elements..."):
                    discovered_manifest = get_internal_links(target_site)

                if discovered_manifest:
                    st.info(f"Discovered {len(discovered_manifest)} unique paths on page. Commencing status validation...")
                    manifest_df = pd.DataFrame(discovered_manifest)
                    status_df = bulk_check_urls(manifest_df["URL"].tolist())

                    if not status_df.empty:
                        final_merged_df = pd.merge(manifest_df, status_df, on="URL", how="left")
                        ordered_cols = ["URL", "Status Code", "Analysis", "Anchor Text", "Source Page", "Final URL"]
                        final_merged_df = final_merged_df[[c for c in ordered_cols if c in final_merged_df.columns]]
                        display_results(final_merged_df, "homepage_seo_audit_report.csv")
                else:
                    st.warning("Analysis halted: No crawlable anchor nodes found inside layout code.")
            else:
                st.error("Missing Parameter: Please input an absolute web address path.")

    with tab2:
        st.subheader("Deep Audit via Backend XML Blueprint")
        st.markdown("Extracts and verifies every URL indexed across your entire site structure.")
        sitemap_input = st.text_input("Enter Sitemap URL Pathway:", placeholder="https://example.com", key="sitemap_input")

        if st.button("Extract & Validate Sitemap Matrix", key="sitemap_btn"):
            if sitemap_input:
                with st.spinner("Parsing nested XML sitemap directories..."):
                    sitemap_urls = get_sitemap_urls(sitemap_input)

                if sitemap_urls:
                    st.success(f"Discovered {len(sitemap_urls)} total production paths inside sitemap registry architecture!")
                    sitemap_results_df = bulk_check_urls(sitemap_urls)
                    display_results(sitemap_results_df, "full_sitemap_seo_report.csv")
                else:
                    st.warning("Crawl complete: Zero operational address URLs discovered inside target block.")
            else:
                st.error("Missing Parameter: Please provide a valid XML sitemap index link.")

    with tab3:
        st.subheader("Upload Custom Execution Sheet Matrix")
        uploaded_file = st.file_uploader("Upload files (.txt or .csv format):", type=["txt", "csv"], key="bulk_uploader")

        if uploaded_file is not None:
            input_urls = []
            filename_clean = uploaded_file.name.lower()

            try:
                if filename_clean.endswith('.csv'):
                    raw_df = pd.read_csv(uploaded_file)
                    if not raw_df.empty:
                        input_urls = raw_df.iloc[:, 0].dropna().astype(str).tolist()
                else:
                    input_urls = [line.decode("utf-8").strip() for line in uploaded_file if line.strip()]
            except Exception as err:
                st.error(f"File configuration engine failure: {err}")

            if input_urls:
                st.success(f"Verified: Loaded {len(input_urls)} unique testing paths from payload.")
                if st.button("Run Bulk Link Validation", key="bulk_run_btn"):
                    bulk_output_df = bulk_check_urls(input_urls)
                    display_results(bulk_output_df, "bulk_seo_link_report.csv")
            else:
                st.warning("The submission package doesn't hold verifiable URL matrices.")

if __name__ == "__main__":
    main()
