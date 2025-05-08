import streamlit as st
import pandas as pd
import requests
import openai
from bs4 import BeautifulSoup
import re
from serpapi import GoogleSearch
import time

# ------------------ CONFIG ------------------
st.set_page_config(page_title="Panel Extractor", layout="wide")
st.title("🎤 Panel Extractor")
st.caption("Extract speaker names, titles, organizations, and emails from a URL or agenda text.")
# --------------------------------------------

# API keys
openai_api_key = st.text_input("🔑 OpenAI API Key", type="password")
serpapi_api_key = st.text_input("🌍 SerpAPI Key (for web search fallback)", type="password")

# Input type selection
input_method = st.radio("Choose input method:", ["Paste agenda text", "Provide a webpage URL"])
text_input = ""

# Web scraping or text pasting
if input_method == "Paste agenda text":
    agenda_text = st.text_area("📋 Paste agenda or panel text here:", height=300)
    if agenda_text:
        text_input = agenda_text
elif input_method == "Provide a webpage URL":
    url = st.text_input("🌐 Paste the agenda page URL:")
    if url:
        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            text_input = soup.get_text(separator="\n", strip=True)
            st.success("✅ Page scraped successfully.")
        except Exception as e:
            st.error(f"Error fetching the page: {e}")

# Extract emails from the raw text using regex
def extract_emails_from_text(text):
    return list(set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)))

# GPT to extract structured contact info
def extract_speakers_with_gpt(text, openai_api_key):
    openai.api_key = openai_api_key
    prompt = f"""
Extract all speaker details from the following text. Return a list of JSON objects with keys:
'name', 'title', 'organization'. Do not include people who are not clearly named.

Text:
\"\"\"
{text}
\"\"\"
"""
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You extract structured contact info from text."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=1000
    )
    try:
        return eval(response['choices'][0]['message']['content'])
    except Exception:
        return []

# SerpAPI to search for emails
def search_for_email(name, org, serpapi_key):
    query = f"{name} {org} email"
    params = {
        "q": query,
        "api_key": serpapi_key,
        "engine": "google",
        "num": 3
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    snippets = []
    for result in results.get("organic_results", []):
        snippet = result.get("snippet") or result.get("title") or ""
        snippets.append(snippet)
    return " ".join(snippets)

# GPT to extract email from snippet
def extract_email_from_snippets(snippet_text, name, org, openai_api_key):
    openai.api_key = openai_api_key
    prompt = f"""
From this snippet, extract an email address associated with {name} at {org}, if present.
If no email is found, return "null".

Snippet:
\"\"\"
{snippet_text}
\"\"\"
"""
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=100
    )
    return response['choices'][0]['message']['content'].strip().replace('"', '')

# Button to trigger the process
if st.button("🔍 Extract Panel Info") and text_input and openai_api_key:
    with st.spinner("Analyzing text with GPT..."):
        speakers = extract_speakers_with_gpt(text_input, openai_api_key)

    emails_in_text = extract_emails_from_text(text_input)
    st.info(f"📧 Found {len(emails_in_text)} emails directly in text.")

    results = []
    for speaker in speakers:
        name = speaker.get("name", "")
        title = speaker.get("title", "")
        org = speaker.get("organization", "")
        email = ""

        # Match email if available directly in text
        for e in emails_in_text:
            if name.split(" ")[-1].lower() in e.lower():
                email = e
                break

        # If not found, search online
        if not email and serpapi_api_key:
            st.write(f"🌐 Searching for: {name} ({org})...")
            try:
                snippet = search_for_email(name, org, serpapi_api_key)
                email = extract_email_from_snippets(snippet, name, org, openai_api_key)
                if email == "null" or not "@" in email:
                    email = ""
            except Exception as e:
                st.warning(f"Search failed for {name}: {e}")
            time.sleep(1.5)  # avoid rate-limiting

        results.append({
            "Name": name,
            "Title": title,
            "Organization": org,
            "Email": email
        })

    df = pd.DataFrame(results)
    st.success(f"✅ Extracted {len(df)} panelists.")
    st.dataframe(df)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download CSV", csv, "panel_contacts.csv", "text/csv")