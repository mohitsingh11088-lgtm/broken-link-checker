import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, urldefrag
import concurrent.futures
import ipaddress
import socket
import xml.etree.ElementTree as ET
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
    """Verify URL and classify HTTP responses accurately."""

    url = str(url).strip()

    if not is_valid_url(url):
        return {
            "Status Code": "Invalid",
            "Analysis": "Invalid URL",
            "Final URL": url
        }

    try:
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

        if status is None:
            analysis = "Unknown HTTP Response"

        elif status == 200:
            analysis = "Working"

        elif 200 <= status < 300:
            analysis = "Working"

        elif status == 404:
            analysis = "Broken Link - 404"

        elif status == 410:
            analysis = "Broken Link - 410"

        elif 300 <= status < 400:
            analysis = "Redirect"

        elif status == 403:
            analysis = "Blocked - 403"

        elif status == 429:
            analysis = "Rate Limited"

        elif status >= 500:
            analysis = "Server Error"

        else:
            analysis = "Other HTTP Issue"

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
            "Analysis": "SSL Error",
            "Final URL": url
        }

    except requests.exceptions.ConnectionError:
        return {
            "Status Code": "Connection Error",
            "Analysis": "Connection Failed",
            "Final URL": url
        }

    except requests.exceptions.RequestException as e:
        return {
            "Status Code": "Request Error",
            "Analysis": str(e),
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
# EXTRACT ANCHOR TEXT FROM SITEMAP PAGES
# ==========================================

def get_page_links_for_report(page_url):

    records = []

    try:
        if not is_valid_url(page_url):
            return records

        response = requests.get(
            page_url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        response.raise_for_status()

        source_page = response.url

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        source_domain = urlparse(source_page).hostname

        for a_tag in soup.find_all("a", href=True):

            href = a_tag.get("href", "").strip()

            if not href:
                continue

            destination = urljoin(source_page, href)
            destination, _ = urldefrag(destination)

            parsed = urlparse(destination)

            if (
                parsed.scheme not in ["http", "https"]
                or not parsed.hostname
                or parsed.hostname.lower() != source_domain.lower()
            ):
                continue

            anchor_text = a_tag.get_text(
                separator=" ",
                strip=True
            )

            if not anchor_text:
                image = a_tag.find("img")

                if image:
                    anchor_text = image.get("alt", "").strip()

            if not anchor_text:
                anchor_text = "[No Anchor Text]"

            records.append({
                "URL": destination,
                "Anchor Text": anchor_text,
                "Source Page": source_page
            })

        response.close()

        return records

    except requests.exceptions.RequestException:
        return []

    except Exception:
        return []


# ==========================================
# BULK URL CHECKER ENGINE
# ==========================================

def bulk_check_urls(url_list, max_workers=MAX_WORKERS):

    # Remove duplicate URLs
    url_list = list(dict.fromkeys(
        str(url).strip()
        for url in url_list
        if str(url).strip()
    ))

    results = []

    if not url_list:
        return pd.DataFrame(
            columns=[
                "URL",
                "Status Code",
                "Analysis",
                "Final URL"
            ]
        )

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
                f"Processed {index + 1} of {total} URLs..."
            )

    progress_bar.empty()
    status_text.empty()

    return pd.DataFrame(results)


# ==========================================
# RESULTS DISPLAY METRICS
# ==========================================



def display_results(df, filename):

    if df.empty:
        st.warning("No results available.")
        return

    total = len(df)

    # ======================================
    # HTTP STATUS CODE DISTRIBUTION
    # ======================================

    st.subheader("HTTP Status Code Distribution")

    status_counts = (
        df["Status Code"]
        .fillna("Missing Status")
        .astype(str)
        .value_counts()
    )

    st.dataframe(
        status_counts.rename_axis("Status Code")
        .reset_index(name="URL Count"),
        use_container_width=True
    )

    # ======================================
    # CLASSIFY URL RESULTS
    # ======================================

    status = df["Status Code"].astype(str)

    broken_404 = df[status == "404"]
    broken_410 = df[status == "410"]

    working = df[
        df["Analysis"].isin(["Working"])
    ]

    redirects = df[
        df["Analysis"] == "Redirect"
    ]

    other_issues = df[
        ~df["Analysis"].isin(["Working", "Redirect"])
        & ~df["Status Code"].astype(str).isin(["404", "410"])
    ]

    # ======================================
    # METRICS
    # ======================================

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total URLs", total)
    col2.metric("Working URLs", len(working))
    col3.metric("404 Broken Links", len(broken_404))
    col4.metric("410 Removed URLs", len(broken_410))

    col5, col6 = st.columns(2)

    col5.metric("Redirects", len(redirects))
    col6.metric("Other Technical Issues", len(other_issues))

    st.divider()

    # ======================================
    # 404 REPORT
    # ======================================

    with st.expander("🚨 Genuine 404 Broken Links", expanded=True):

        if not broken_404.empty:
            st.dataframe(
                broken_404,
                use_container_width=True
            )
        else:
            st.success("No 404 errors detected.")

    # ======================================
    # 410 REPORT
    # ======================================

    with st.expander("🗑️ Permanently Removed URLs (410)"):

        if not broken_410.empty:
            st.dataframe(
                broken_410,
                use_container_width=True
            )
        else:
            st.info("No 410 errors detected.")

    # ======================================
    # OTHER TECHNICAL ISSUES
    # ======================================

    with st.expander("⚠️ Other HTTP Errors and Technical Issues"):

        if not other_issues.empty:
            st.dataframe(
                other_issues,
                use_container_width=True
            )
        else:
            st.success("No other technical issues detected.")

    # ======================================
    # REDIRECT REPORT
    # ======================================

    with st.expander("🔄 Redirected URLs"):

        if not redirects.empty:
            st.dataframe(
                redirects,
                use_container_width=True
            )
        else:
            st.info("No redirects detected.")

    # ======================================
    # COMPLETE REPORT
    # ======================================

    with st.expander("📋 Complete URL Audit"):

        st.dataframe(
            df,
            use_container_width=True
        )

    # ======================================
    # DOWNLOAD COMPLETE CSV
    # ======================================

    csv_data = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="📥 Download Complete SEO Audit CSV",
        data=csv_data,
        file_name=filename,
        mime="text/csv",
        key=f"download_{filename}"
    )

    # ======================================
    # DOWNLOAD 404 ONLY
    # ======================================

    if not broken_404.empty:

        csv_404 = broken_404.to_csv(
            index=False
        ).encode("utf-8")

        st.download_button(
            label="📥 Download Only 404 Broken Links",
            data=csv_404,
            file_name="404_broken_links.csv",
            mime="text/csv",
            key=f"download_404_{filename}"
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

                with st.spinner("Parsing XML sitemap..."):
                    sitemap_urls = get_sitemap_urls(sitemap_input)

                if sitemap_urls:

                    st.success(
                        f"Discovered {len(sitemap_urls)} URLs in sitemap!"
                    )

                    all_anchor_records = []

                    progress = st.progress(0)
                    status = st.empty()

                    # Extract anchor text from sitemap pages
                    for index, page_url in enumerate(sitemap_urls):

                        page_links = get_page_links_for_report(page_url)

                        all_anchor_records.extend(page_links)

                        progress.progress(
                            (index + 1) / len(sitemap_urls)
                        )

                        status.text(
                            f"Extracting anchor text: {index + 1}/{len(sitemap_urls)}"
                        )

                    progress.empty()
                    status.empty()

                    # Check sitemap URLs
                    sitemap_results_df = bulk_check_urls(sitemap_urls)

                    # Combine anchor text with URL status
                    if all_anchor_records:

                        anchor_df = pd.DataFrame(all_anchor_records)

                        final_df = anchor_df.merge(
                            sitemap_results_df,
                            on="URL",
                            how="left"
                        )

                    else:

                        final_df = sitemap_results_df

                        st.warning(
                            "No HTML anchor links were extracted."
                        )

                    display_results(
                        final_df,
                        "full_sitemap_seo_report.csv"
                    )

                else:

                    st.warning("No URLs discovered in sitemap.")

            else:

                st.error("Please provide a sitemap URL.")


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
