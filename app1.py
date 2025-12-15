import streamlit as st
import requests
import json
import re
import hashlib
import random
import html
from typing import List, Optional
from urllib.parse import urlparse
from pydantic import BaseModel, Field
import google.generativeai as genai

# ==========================================
# 1. CONFIGURATION & KEYS
# ==========================================

GEMINI_API_KEY = "AIzaSyAANSQuZsnKiCTZplanuv4C2n5Dn1Dqtok"
SERPAPI_API_KEY = "eef3e8671c56799432de722c444f1166e80d59abac671f29aa61f3f3f2bab719"

# Fixed default limit
FIXED_RESULT_LIMIT = 30

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Search Operators
SEARCH_OPERATORS = [
    "site:udemy.com/course/", "site:coursera.org/learn/", "site:edx.org/course/",
    "site:pluralsight.com/courses/", "site:udacity.com/course/", "site:codecademy.com/learn/",
    "site:skillshare.com/classes/", "site:futurelearn.com/courses/", 
    "site:simplilearn.com/", "site:geeksforgeeks.org/courses/", "site:classcentral.com/course/"
]

# Updated Price Defaults to prevent "Unknown"
PRICE_DEFAULTS = {
    "udemy": "Paid (Check Site)",
    "coursera": "Free Audit / Paid Cert",
    "edx": "Free Audit / Paid Cert",
    "pluralsight": "Subscription (Trial)",
    "udacity": "Paid Nanodegree",
    "codecademy": "Free Basic / Pro",
    "skillshare": "Subscription",
    "futurelearn": "Free / Paid Upgrade",
    "simplilearn": "Paid Bootcamp",
    "geeksforgeeks": "Free / Paid",
    "educative": "Subscription",
    "datacamp": "Subscription",
    "linkedin": "Subscription (1 Mo Free)"
}

# ==========================================
# 2. MODELS
# ==========================================

class Offer(BaseModel):
    price_display: str 
    url: str
    provider_name: str
    provider_domain: str

class CourseMetadata(BaseModel):
    difficulty: str = Field(default="All Levels")
    duration: Optional[str] = None
    rating: Optional[float] = None

class Course(BaseModel):
    id: str
    title: str
    ai_summary: str
    metadata: CourseMetadata
    offer: Offer

class SearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[Course]

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================

def get_logo_url(domain: str) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"

def is_individual_course_page(url: str) -> bool:
    bad_patterns = ["/topic/", "/courses?", "/search", "/category/", "/articles/", "/blog/", "/tag/", "top-", "best-", "reviews", "login", "signup"]
    for pattern in bad_patterns:
        if pattern in url.lower(): return False
    return True

def generate_ai_metadata(title: str, snippet: str, link: str, query: str):
    prompt = f"""
You are an expert course analyst.
Analyze ONE specific online course.

Title: {title}
Snippet: {snippet}
Skill: {query}
URL: {link}

STRICT RULES:
- Return ONLY valid JSON.
- Summary MUST be at least 50 words describing what is taught.
- No markdown, no explanations.

JSON FORMAT:
{{
  "summary": "At least 50 words description...",
  "difficulty": "Beginner / Intermediate / Advanced / All Levels",
  "duration": "Estimated duration (e.g. 10 hours) or null"
}}
"""
    for _ in range(2):
        try:
            response = model.generate_content(prompt)
            raw = response.text.strip()
            raw = re.sub(r"```json|```", "", raw)
            raw = raw.replace("“", "\"").replace("”", "\"")
            data = json.loads(raw)
            if len(data.get("summary", "").split()) < 30: # Relaxed slightly to 30 to prevent failures
                raise ValueError
            return data
        except:
            continue

    return {
        "summary": (
            f"This course titled '{title}' covers key concepts regarding {query}. "
            f"It provides structured lessons designed to help learners master the subject matter "
            f"effectively. Ideal for those looking to improve their skills in this domain."
        ),
        "difficulty": "All Levels",
        "duration": None
    }

# ==========================================
# 4. SEARCH LOGIC (FIXED)
# ==========================================

@st.cache_data(ttl=600, show_spinner=False)
def search_individual_courses(user_query: str):
    sites_query = " OR ".join(SEARCH_OPERATORS)
    final_query = f"{user_query} ({sites_query})"
    params = {"engine": "google", "q": final_query, "api_key": SERPAPI_API_KEY, "num": 100, "hl": "en", "gl": "us"}
    
    try:
        resp = requests.get("https://serpapi.com/search", params=params)
        data = resp.json()
        raw_results = data.get("organic_results", [])
    except Exception as e:
        st.error(f"API Error: {e}")
        return None

    processed_courses = []
    seen_urls = set()
    provider_counts = {}
    max_per_provider = max(3, int(FIXED_RESULT_LIMIT / 4))

    for item in raw_results:
        link = item.get("link", "")
        if not is_individual_course_page(link) or link in seen_urls: continue
        seen_urls.add(link)

        # --- 1. Identify Provider & Key ---
        domain = urlparse(link).netloc.lower()
        provider_name = "Unknown"
        provider_key = "unknown"

        if "udemy" in domain: provider_name, provider_key = "Udemy", "udemy"
        elif "coursera" in domain: provider_name, provider_key = "Coursera", "coursera"
        elif "edx" in domain: provider_name, provider_key = "EdX", "edx"
        elif "pluralsight" in domain: provider_name, provider_key = "Pluralsight", "pluralsight"
        elif "udacity" in domain: provider_name, provider_key = "Udacity", "udacity"
        elif "geeksforgeeks" in domain: provider_name, provider_key = "GeeksForGeeks", "geeksforgeeks"
        elif "simplilearn" in domain: provider_name, provider_key = "Simplilearn", "simplilearn"
        elif "codecademy" in domain: provider_name, provider_key = "Codecademy", "codecademy"
        elif "skillshare" in domain: provider_name, provider_key = "Skillshare", "skillshare"
        elif "futurelearn" in domain: provider_name, provider_key = "FutureLearn", "futurelearn"
        else:
            # Fallback formatting
            parts = domain.replace("www.", "").split('.')
            if parts:
                provider_name = parts[0].capitalize()
                provider_key = parts[0]

        # Limit results per provider
        if provider_counts.get(provider_name, 0) >= max_per_provider: continue
        provider_counts[provider_name] = provider_counts.get(provider_name, 0) + 1

        title = item.get("title", "Unknown Course")
        
        # --- 2. Extract Metadata ---
        ai_data = generate_ai_metadata(title, item.get("snippet", ""), link, user_query)
        rich = item.get("rich_snippet", {}).get("top", {}).get("detected_extensions", {})
        rating = rich.get("rating") or item.get("rating")

        # --- 3. PRICE FIX LOGIC ---
        # Priority 1: Exact price from Google (e.g. "$12.99")
        # Priority 2: Hardcoded Default (e.g. "Free Audit")
        # Priority 3: Generic Fallback
        
        detected_price = rich.get("price")
        
        if detected_price and any(char.isdigit() for char in str(detected_price)):
             # Keep detected price if it looks like a number
            final_price = detected_price
        elif provider_key in PRICE_DEFAULTS:
            final_price = PRICE_DEFAULTS[provider_key]
        else:
            final_price = "View Details" # Generic fallback, never "Unknown"

        course = Course(
            id=hashlib.md5(link.encode()).hexdigest(),
            title=title, 
            ai_summary=ai_data.get("summary", ""),
            metadata=CourseMetadata(
                difficulty=ai_data.get("difficulty", "All Levels"), 
                duration=ai_data.get("duration"), 
                rating=float(rating) if rating else None
            ),
            offer=Offer(
                price_display=final_price, 
                url=link, 
                provider_name=provider_name, 
                provider_domain=domain
            )
        )
        processed_courses.append(course)

    random.shuffle(processed_courses)
    # Sort by rating if available, pushing None to bottom
    processed_courses.sort(key=lambda x: x.metadata.rating if x.metadata.rating else 0, reverse=True)
    
    return SearchResponse(
        query=user_query, 
        total_results=len(processed_courses[:FIXED_RESULT_LIMIT]), 
        results=processed_courses[:FIXED_RESULT_LIMIT]
    ).dict()

# ==========================================
# 5. UI
# ==========================================

st.set_page_config(page_title="AI Course Finder", page_icon="🎓", layout="wide")

st.markdown("""
<style>
    /* Card Container */
    .course-card {
        padding: 20px;
        border-radius: 12px;
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        margin-bottom: 20px;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        position: relative;
        overflow: hidden;
    }
    
    .course-card:hover {
        transform: translateY(-8px);
        box-shadow: 0 12px 24px rgba(0,0,0,0.15);
        border-color: #D32F2F;
    }

    .course-card a {
        text-decoration: none !important;
        color: inherit !important;
        display: flex;
        flex-direction: column;
        height: 100%;
    }

    .provider-wrapper {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
    }
    .provider-tag {
        font-weight: bold;
        color: #555;
        font-size: 0.9em;
    }
    .card-title-text {
        margin: 0 0 10px 0;
        font-size: 1.1em;
        line-height: 1.4;
        font-weight: 700;
        color: #111;
    }
    .card-summary-text {
        font-size: 0.9em;
        color: #666;
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 4;
        -webkit-box-orient: vertical;
        margin-bottom: 15px;
        flex-grow: 1;
    }
    .card-footer {
        margin-top: auto;
        padding-top: 15px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-top: 1px solid #f0f0f0;
    }
    .price-badge {
        background-color: #e8f5e9;
        color: #2e7d32;
        padding: 5px 10px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 0.85em;
    }
    .view-text {
        color: #D32F2F;
        font-weight: 600;
        font-size: 0.9em;
    }

    /* Dark Mode Support */
    @media (prefers-color-scheme: dark) {
        .course-card { background-color: #262730; border-color: #41424b; }
        .provider-tag { color: #ddd; }
        .card-title-text { color: #fff; }
        .card-summary-text { color: #ccc; }
        .price-badge { background-color: #1e3a29; color: #81c784; }
    }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("📖 Guide")
    st.markdown("""
    **Algorithm:**
    - Deep searches `site:udemy.com`, `site:coursera.org`, etc.
    - Limits **max 3-4 courses per provider** for variety.
    
    **How to use:**
    1. Enter skill (e.g. 'Java').
    2. Click Find Courses.
    """)
    st.info("Supported: Udemy, Coursera, EdX, Pluralsight, Udacity, GeeksForGeeks, Simplilearn & more.")

c1, c2 = st.columns([3, 1])
with c1:
    st.title("🎓 SKILL SCOUT AI")
    st.markdown("Finds **individual course pages**, not generic lists.")
with c2:
    st.write("")
    view_mode = st.radio("View:", ["List ☰", "Grid ⊞"], horizontal=True)

query = st.text_input("What skill do you want to learn?", placeholder="e.g. Docker, React Native")

if st.button("Find Courses", type="primary"):
    if not query:
        st.warning("Please enter a topic.")
    else:
        with st.spinner(f"🔍 Searching courses for '{query}'..."):
            data = search_individual_courses(query)
            
            if not data or data['total_results'] == 0:
                st.error("No specific course pages found.")
            else:
                st.success(f"Found {data['total_results']} courses.")
                results = data['results']

                if "Grid" in view_mode:
                    cols = st.columns(3)
                    for i, course in enumerate(results):
                        with cols[i % 3]:
                            logo = get_logo_url(course['offer']['provider_domain'])
                            safe_title = html.escape(course['title'])
                            safe_summary = html.escape(course['ai_summary'])
                            
                            html_content = f"""
<div class="course-card">
    <a href="{course['offer']['url']}" target="_blank">
        <div class="provider-wrapper">
            <img src="{logo}" width="32" style="border-radius:4px;">
            <span class="provider-tag">{course['offer']['provider_name']}</span>
        </div>
        <div class="card-title-text">{safe_title}</div>
        <div class="card-summary-text">{safe_summary}</div>
        <div class="card-footer">
            <span class="price-badge">{course['offer']['price_display']}</span>
            <span class="view-text">View Course &rarr;</span>
        </div>
    </a>
</div>
"""
                            st.markdown(html_content, unsafe_allow_html=True)
                            st.write("") 

                else:
                    for course in results:
                        with st.container():
                            c1, c2, c3 = st.columns([1, 4, 1.5])
                            with c1:
                                logo = get_logo_url(course['offer']['provider_domain'])
                                st.image(logo, width=50)
                                st.caption(course['offer']['provider_name'])
                            with c2:
                                st.markdown(f"### [{course['title']}]({course['offer']['url']})")
                                st.write(course['ai_summary'])
                                metas = []
                                if course['metadata']['rating']: metas.append(f"⭐ {course['metadata']['rating']}")
                                if course['metadata']['difficulty']: metas.append(f"📊 {course['metadata']['difficulty']}")
                                if course['metadata']['duration']: metas.append(f"⏱️ {course['metadata']['duration']}")
                                st.markdown(" | ".join(metas))
                            with c3:
                                st.markdown(f"#### {course['offer']['price_display']}")
                                st.link_button("Go to Course", course['offer']['url'], use_container_width=True)
                            st.divider()