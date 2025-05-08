import streamlit as st
import pandas as pd
import requests
import openai
from bs4 import BeautifulSoup
import re
import time

st.set_page_config(page_title="Panel Extractor", layout="wide")
st.title("🎤 Panel Extractor")
st.caption("Paste a conference agenda or URL — extract speaker names, titles, organizations, and emails using OpenAI + SerpAPI.")

openai_api_key = st.text_input("🔑 OpenAI API Key", type="password")
serpapi_key = st.text_input("🌍 SerpAPI Key (optional, for missing email lookups)", type="password")

input_method = st.radio("Choose input method:", ["Paste agenda text", "Provide a webpage URL"])
text_input = ""

if input_method == "Paste agenda text":
    text_input = st.text_area("📋 Paste agenda text here:", height=300)

elif input_method == "Provide a webpage URL":
    url = st.text_input("🌐 Paste the URL of the agenda page:")
    if url:
        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            text_input = soup.get_text(separator="\n", strip=True)
            st.success("✅ Page scraped successfully.")
        except Exception as e:
            st.error(f"Error loading the URL: {e}")

def extract_emails_from_text(text):
    return list(set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)))

def extract_speakers_with_gpt(text, openai_key):
    openai.api_key = openai_key
    prompt = f"""
Extract all speakers from the text below and return a list of JSON objects with keys:
'name', 'title', 'organization'. Only include clearly named people.

Text:
\"\"\"
{text}
\"\"\"
"""
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You extract structured contact info from messy agenda text."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=1000
    )
    try:
        return eval(response.choices[0].message.content)
    except Exception:
        return []

def search_for_email(name, org, serpapi_key):
    query = f"{name} {org} email"
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": serpapi_key,
        "engine": "google",
        "num": 3
    }
    try:
        response = requests.get(url, params=params)
        results = response.json()
        snippets = []
        for result in results.get("organic_results", []):
            snippet = result.get("snippet") or result.get("title") or ""
            snippets.append(snippet)
        return " ".join(snippets)
    except Exception as e:
        return ""

def extract_email_from_snippets(snippet_text, name, org, openai_key):
    openai.api_key = openai_key
    prompt = f"""
From the text below, extract the email address for {name} at {org}, if found. Return "null" if not found.

Text:
\"\"\"
{snippet_text}
\"\"\"
"""
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=100
    )
    return response.choices[0].message.content.strip().replace('"', '')

if st.button("🔍 Extract Panel Info") and text_input and openai_api_key:
    with st.spinner("Analyzing text with OpenAI..."):
        speakers = extract_speakers_with_gpt(text_input, openai_api_key)

    emails_in_text = extract_emails_from_text(text_input)
    st.info(f"📧 Found {len(emails_in_text)} emails directly in text.")

    results = []
    for speaker in speakers:
        name = speaker.get("name", "")
        title = speaker.get("title", "")
        org = speaker.get("organization", "")
        email = ""

        # Try matching found emails
        for e in emails_in_text:
            if name.split(" ")[-1].lower() in e.lower():
                email = e
                break

        # Use SerpAPI + GPT if missing
        if not email and serpapi_key:
            st.write(f"🌐 Searching for: {name} ({org})...")
            snippet = search_for_email(name, org, serpapi_key)
            if snippet:
                extracted = extract_email_from_snippets(snippet, name, org, openai_api_key)
                if extracted != "null" and "@" in extracted:
                    email = extracted
            time.sleep(1.5)  # Avoid SerpAPI rate limits

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
