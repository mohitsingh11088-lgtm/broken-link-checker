import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import concurrent.futures

# Set up page configurations
st.set_page_config(
    page_title="SEO Broken Link Checker",
    page_icon="🔗",
    layout="wide"
)

st.title("🔗 Professional SEO Broken Link Checker")
st.markdown("Scan a website for broken internal links or upload a custom bulk list of URLs to verify status codes.")

# --- HELPER FUNCTIONS ---

def verify_url(url, timeout=5):
    """Checks a single URL and returns its status code and status text."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SEO-Link-Checker"
    }
    try:
        # Use HEAD request first for speed, fall back to GET if HEAD fails/blocked
        response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if response.status_code in:
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        return response.status_code, "OK" if response.status_code == 200 else "Issue Found"
    except requests.exceptions.Timeout:
        return "Timeout", "Error"
    except requests.exceptions.RequestException:
        return "Connection Error", "Error"

def get_internal_links(base_url, timeout=10):
    """Scrapes all unique internal links from a given homepage/landing page URL."""
    headers = {"User-Agent": "Mozilla/5.0 SEO-Link-Checker"}
    try:
        response = requests.get(base_url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            st.error(f"Could not access the base URL. Status Code: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        domain = urlparse(base_url).netloc
        internal_links = set()

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            full_url = urljoin(base_url, href)
            parsed_url = urlparse(full_url)
            
            # Clean and filter to ensure it belongs to the same domain
            if parsed_url.netloc == domain and parsed_url.scheme in ["http", "https"]:
                # Strip fragments/anchors
                clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                internal_links.add(clean_url)
                
        return list(internal_links)
    except Exception as e:
        st.error(f"Error parsing the website: {e}")
        return []

def bulk_check_urls(url_list, max_workers=10):
    """Checks a list of URLs concurrently using a thread pool."""
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(url_list)

    if total == 0:
        return pd.DataFrame(columns=["URL", "Status Code", "Analysis"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Map out the futures
        future_to_url = {executor.submit(verify_url, url): url for url in url_list}
        
        for index, future in enumerate(concurrent.futures.as_completed(future_to_url)):
            url = future_to_url[future]
            try:
                status_code, status_msg = future.result()
            except Exception:
                status_code, status_msg = "Unknown Error", "Error"
            
            results.append({"URL": url, "Status Code": status_code, "Analysis": status_msg})
            
            # Update Streamlit UI
            progress = (index + 1) / total
            progress_bar.progress(progress)
            status_text.text(f"Processed {index + 1} of {total} URLs...")
            
    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(results)

# --- STREAMLIT UI TABS ---

tab1, tab2 = st.tabs(["🕵️ Crawl a Website", "📂 Bulk URL List Upload"])

# TAB 1: Crawl Website
with tab1:
    st.subheader("Crawl and Check Page Links")
    target_site = st.text_input("Enter website homepage URL:", placeholder="https://example.com")
    
    if st.button("Extract & Check Links", key="crawl_btn"):
        if target_site:
            with st.spinner("Extracting internal links..."):
                discovered_urls = get_internal_links(target_site)
            
            if discovered_urls:
                st.info(f"Found {len(discovered_urls)} unique internal links. Initiating status code check...")
                df_results = bulk_check_urls(discovered_urls)
                
                # Split metrics
                broken_df = df_results[df_results["Status Code"] != 200]
                
                col1, col2 = st.columns(2)
                col1.metric("Total Links Found", len(df_results))
                col2.metric("Broken/Issue Links", len(broken_df), delta=int(len(broken_df)), delta_color="inverse")
                
                st.subheader("Full Scan Results")
                st.dataframe(df_results, use_container_width=True)
                
                # Export options
                csv = df_results.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Results CSV", csv, "seo_link_report.csv", "text/csv")
        else:
            st.warning("Please provide a valid target URL.")

# TAB 2: Bulk File Upload
with tab2:
    st.subheader("Upload Custom Extraction List")
    # FIX: Changed st.file_uploaded_file to st.file_uploader
    uploaded_file = st.file_uploader("Upload a .txt or .csv file (one URL per line)", type=["txt", "csv"])
    
    if uploaded_file is not None:
        if uploaded_file.name.endswith('.csv'):
            try:
                # Expecting a column named 'url' or simply taking the first column
                raw_df = pd.read_csv(uploaded_file)
                input_urls = raw_df.iloc[:, 0].dropna().tolist()
            except Exception as e:
                st.error(f"Error parsing CSV: {e}")
                input_urls = []
        else:
            # Handle plain TXT file
            input_urls = [line.decode("utf-8").strip() for line in uploaded_file if line.strip()]
            
        st.success(f"Successfully loaded {len(input_urls)} URLs from file.")
        
        if st.button("Run Bulk Link Validation", key="bulk_btn"):
            if input_urls:
                df_bulk_results = bulk_check_urls(input_urls)
                
                broken_bulk = df_bulk_results[df_bulk_results["Status Code"] != 200]
                
                c1, c2 = st.columns(2)
                c1.metric("Total Uploaded", len(df_bulk_results))
                c2.metric("Dead/Broken Links", len(broken_bulk), delta=int(len(broken_bulk)), delta_color="inverse")
                
                st.subheader("Bulk Validation Results")
                st.dataframe(df_bulk_results, use_container_width=True)
                
                csv_bulk = df_bulk_results.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Bulk Report CSV", csv_bulk, "bulk_seo_link_report.csv", "text/csv")
